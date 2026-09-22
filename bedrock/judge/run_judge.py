"""
run_judge.py — 독립적인 Bedrock LLM-as-a-Judge 실행 스크립트
====================================================================
`docs/bedrock/v2-pipeline.md` §10~§11, §26의 이중 평가 구조를 그대로 구현한다.

    LLM Output (outputs/{json,html}/<id>.*  — 이미 다른 곳에서 만들어진 것)
        |
        +-- Deterministic Validator (deterministic_html.py / _json.py) --> Pass/Fail
        |
        +-- Bedrock Judge (bedrock_client.py, rubric.py)               --> 0~5점
        |
        v
    results/{json,html}/<id>.json   (§30 형식)

★ "독립적"이라는 뜻 (요청에 대한 설계 근거)
    1) base/, versions/v8/ 등 다른 벤치마크 코드를 import 하지 않는다 —
       이 폴더만 있어도 실행된다(judge/ 안의 4개 모듈 + 표준 라이브러리 +
       boto3, bs4).
    2) 생성(Generator)을 하지 않는다 — 이미 만들어진 모델 출력을
       outputs/ 에서 읽기만 한다(BYO Model Response, §11). 로컬 Qwen이든
       versions/v8이 Bedrock으로 만든 결과든 상관없다.
    3) 특정 실행기(run_v8.py 등)에 얹혀살지 않는다 — 이 파일 하나로
       처음부터 끝까지(결정론적 검증 -> Judge 호출 -> 결과 저장 -> 집계)
       돈다.

사용법:
    # 0) 네트워크 호출 없이 배선만 확인
    python run_judge.py --self-check

    # 1) outputs/html/TC-GEN-001.html 같은 파일을 이미 만들어 뒀다면
    export BEDROCK_REGION=us-east-1
    export BEDROCK_JUDGE_MODEL=sonnet        # 별칭 또는 실제 모델 ID
    python run_judge.py --dataset generation --format html

    # 2) 비용 없이 파이프라인 배선만 (Judge 응답은 dry_run 표시로 채움)
    python run_judge.py --dataset generation --format html --dry-run

    # 3) JSON 방식(Page Schema) — 주의: 백엔드에 구현되어 있지 않다.
    #    outputs/json/*.json 은 project-architect.md (JSON 파트) 스펙대로
    #    직접 만들거나, 그 스펙으로 프롬프트한 모델 출력이어야 한다.
    python run_judge.py --dataset generation --format json

    # 4) 수정(edit) — before 상태가 필요하므로 datasets/edit.jsonl 사용
    python run_judge.py --dataset edit --format html

    # 5) Behavior — data-behavior/Component.behavior 시나리오
    python run_judge.py --dataset behavior --format html
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 일부 Windows 콘솔(cp949)은 이 파일의 한글 docstring/주석에 섞인 "—" 같은
# 문자를 인코딩하지 못해 print()/--help 에서 UnicodeEncodeError로 죽는다.
# 로직과 무관한 콘솔 인코딩 문제이므로 여기서 한 번에 방어한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import bedrock_client as BC
import deterministic_html as DH
import deterministic_json as DJ
import rubric as RB

HERE = Path(__file__).resolve().parent
BEDROCK_ROOT = HERE.parent


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _find_outputs(fmt: str, case_id: str) -> list:
    """이 케이스에 대해 있는 출력 파일을 전부 찾는다 — (model_label, path).

    `generate_html_outputs.py`가 만드는 `<id>__<모델별칭>.html` 형태를
    모두 잡아내서, **모델을 몇 개 돌렸든 자동으로 전부 채점 대상이 된다**
    (별도 --model 플래그가 필요 없다). 옛 방식(`<id>.html` 단일 파일,
    수동으로 하나만 넣어둔 경우)도 model_label="unspecified"로 계속 읽는다.
    """
    ext = "json" if fmt == "json" else "html"
    out_dir = BEDROCK_ROOT / "outputs" / fmt
    found = []
    for p in sorted(out_dir.glob(f"{case_id}__*.{ext}")):
        model_label = p.stem.split("__", 1)[1]
        found.append((model_label, p))
    bare = out_dir / f"{case_id}.{ext}"
    if bare.exists():
        found.append(("unspecified", bare))
    return found


def _result_path(fmt: str, case_id: str, model_label: str) -> Path:
    suffix = "" if model_label == "unspecified" else f"__{model_label}"
    return BEDROCK_ROOT / "results" / fmt / f"{case_id}{suffix}.json"


# ══════════════════════════════════════════════════════════════════
#  Deterministic 단계
# ══════════════════════════════════════════════════════════════════

def run_deterministic(fmt: str, category: str, case: dict, raw_output: str) -> dict:
    """반환 필드:
        model_fails / pipeline_fails  — base/checks.py 이식(§도구 그대로): 정화 전에도
            실패하면 model_fails, 정화 후에만 생기면 pipeline_fails
        hard_fails / soft_fails       — base/engine.py의 hard/soft 분리(SOFT_FAILS
            = code_fence·extra_text). **이 분류는 고정 규칙이지 LLM 판단이 아니다**
        validation                    — all_ok (하드+소프트 실패 0건, 완전 통과)
        hard_ok                       — 소프트 실패는 무시하고 하드 실패만 0건인가
        spec_only
    """
    if fmt == "html":
        html = DH.extract(raw_output)
        fmt_fails = DH.format_fails(raw_output, html)  # code_fence·extra_text — 모델 탓
        keep_slots = category == "edit"
        cleaned = DH.sanitize(html, keep_slots=keep_slots)
        if category == "generation":
            fails_raw = DH.validate_generated(html)
            fails_clean = DH.validate_generated(cleaned)
        elif category == "edit":
            before = case["before"]["html"]
            fails_raw = DH.validate_edited(case["target"], before, html)
            fails_clean = DH.validate_edited(case["target"], before, cleaned)
        else:  # behavior
            fails_raw, fails_clean = [], []
            for b in DH.behaviors_in(html):
                bf = DH.validate_behavior(b)
                fails_raw += bf
                fails_clean += bf
            if not DH.behaviors_in(html):
                fails_raw.append("no_behavior_found")
                fails_clean.append("no_behavior_found")
        model_fails = fmt_fails + fails_raw            # 정화 전에도 실패 -> 모델 탓
        pipeline_fails = [f for f in fails_clean if f not in fails_raw]  # 정화가 만든 실패
        hard_model, soft_model = DH.split_fails(model_fails)
        hard_pipeline, soft_pipeline = DH.split_fails(pipeline_fails)
        return {
            "model_fails": model_fails,
            "pipeline_fails": pipeline_fails,
            "hard_fails": hard_model + hard_pipeline,
            "soft_fails": soft_model + soft_pipeline,
            "sanitize_damaged": bool(pipeline_fails),
            "validation": not (model_fails + pipeline_fails),
            "hard_ok": not (hard_model + hard_pipeline),
            "spec_only": (category == "behavior" and not DH.BEHAVIOR_IMPLEMENTED_IN_BACKEND),
        }

    if fmt == "json":
        extracted = DJ.extract_json_text(raw_output)
        fmt_fails = DJ.format_fails(raw_output, extracted)
        if category == "generation":
            fails, _parsed = DJ.validate_schema(raw_output)
        elif category == "edit":
            before_schema = case["before"]["json"]
            fails, _cmd = DJ.validate_modification(raw_output, before_schema)
        else:  # behavior — component.behavior 는 Page Schema 안에 내장되므로
               # generation과 동일하게 schema를 파싱한 뒤 behavior 필드만 본다
            fails, parsed = DJ.validate_schema(raw_output)
            if parsed:
                for _sec, comp in DJ._walk_components(parsed):
                    b = comp.get("behavior")
                    if b:
                        fails += DH.validate_behavior(json.dumps(b, ensure_ascii=False))
        model_fails = fmt_fails + fails
        hard, soft = DJ.split_fails(model_fails)
        return {
            "model_fails": model_fails, "pipeline_fails": [],
            "hard_fails": hard, "soft_fails": soft,
            "sanitize_damaged": False,
            "validation": not model_fails,
            "hard_ok": not hard,
            "spec_only": True,  # JSON 경로 전체가 spec-only (모듈 docstring 참고)
        }

    raise ValueError(f"모르는 format: {fmt}")


# ══════════════════════════════════════════════════════════════════
#  Judge 단계
# ══════════════════════════════════════════════════════════════════

def run_judge_call(client, fmt: str, category: str, case: dict,
                    raw_output: str, deterministic: dict) -> dict:
    system = RB.system_for(fmt, category)
    before_text = None
    if category == "edit":
        before_text = json.dumps(case["before"][fmt], ensure_ascii=False) \
            if fmt == "json" else case["before"]["html"]
    user = RB.build_user_prompt(
        prompt=case.get("prompt", ""),
        requirements=case.get("requirements") or case.get("expected"),
        output_text=raw_output,
        before=before_text,
        deterministic_summary=deterministic["model_fails"] + deterministic["pipeline_fails"],
    )
    resp = client.judge(system, user)
    scores = RB.parse_judge_json(resp.content)
    scores["_judge_meta"] = {
        "provider": client.provider_name(),
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "wall_ms": resp.wall_ms,
        "truncated": resp.truncated,
    }
    return scores


# ══════════════════════════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════════════════════════

def run_one(client, fmt: str, category: str, case: dict) -> list:
    """이 케이스에 대해 발견된 **모델별 출력 전부**를 채점한다.
    반환: 결과 dict 목록(모델 수만큼, 0개일 수도 있음)."""
    case_id = case["id"]
    variants = _find_outputs(fmt, case_id)
    if not variants:
        ext = "json" if fmt == "json" else "html"
        print(f"  [skip] {case_id}: outputs/{fmt}/{case_id}__<모델>.{ext} 가 없습니다 "
              f"(먼저 모델 출력을 이 경로에 저장하세요. BYO Model Response, §11)")
        return []

    results = []
    for model_label, out_path in variants:
        raw_output = out_path.read_text(encoding="utf-8")
        deterministic = run_deterministic(fmt, category, case, raw_output)
        try:
            judge_scores = run_judge_call(client, fmt, category, case, raw_output, deterministic)
        except Exception as e:
            # ★ Judge 호출 하나가 실패했다고 나머지 케이스/모델까지 전부
            #   날리지 않는다 — 이미 끝난 것들은 disk에 남고, 이 건만
            #   error로 기록한 뒤 다음으로 넘어간다(방금 sonnet의
            #   temperature 오류로 --dataset edit 전체가 죽었던 것과 같은
            #   상황을 재발시키지 않기 위함).
            print(f"  [error] {case_id} ({model_label}): {type(e).__name__}: {e}")
            error_result = {
                "testCaseId": case_id, "model": model_label, "format": fmt,
                "category": category, "error": f"{type(e).__name__}: {e}",
            }
            error_path = _result_path(fmt, case_id, model_label)
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(json.dumps(error_result, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            results.append(error_result)
            continue

        result = {
            "testCaseId": case_id,
            "model": model_label,
            "format": fmt,
            "category": category,
            fmt: {
                **{k: v for k, v in judge_scores.items() if k != "_judge_meta"},
                "validation": deterministic["validation"],
                "hard_ok": deterministic["hard_ok"],
                "model_fails": deterministic["model_fails"],
                "pipeline_fails": deterministic["pipeline_fails"],
                "hard_fails": deterministic["hard_fails"],
                "soft_fails": deterministic["soft_fails"],
                "sanitize_damaged": deterministic["sanitize_damaged"],
                "spec_only": deterministic["spec_only"],
            },
            "judge_meta": judge_scores.get("_judge_meta", {}),
        }
        result_path = _result_path(fmt, case_id, model_label)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        tag = "spec-only" if deterministic["spec_only"] else "verified-against-backend"
        soft_note = f", soft={deterministic['soft_fails']}" if deterministic["soft_fails"] else ""
        print(f"  [ok] {case_id} ({model_label}) -> {result_path.name}  "
              f"(all_ok={deterministic['validation']}, hard_ok={deterministic['hard_ok']}"
              f"{soft_note}, {tag})")
        results.append(result)
    return results


def _self_check_error_isolation():
    """Judge 호출 하나가 죽어도 run_one이 예외를 밖으로 던지지 않고
    error 결과를 기록한 뒤 계속 진행하는지 확인한다(네트워크 호출 없음)."""
    import tempfile

    class _BoomClient:
        def provider_name(self):
            return "boom-stub"

        def judge(self, system, user):
            raise RuntimeError("`temperature` is deprecated for this model.")

    with tempfile.TemporaryDirectory() as tmp:
        global BEDROCK_ROOT
        original_root = BEDROCK_ROOT
        BEDROCK_ROOT = Path(tmp)
        try:
            out_dir = BEDROCK_ROOT / "outputs" / "html"
            out_dir.mkdir(parents=True)
            (out_dir / "TC-FAKE__stub.html").write_text(
                '<section data-block="hero"><h1>t</h1><p>s</p></section>'
                '<section data-block="benefits"><ul><li>a</li><li>b</li></ul></section>'
                '<section data-block="cta"><a href="#">x</a></section>',
                encoding="utf-8")
            case = {"id": "TC-FAKE", "prompt": "테스트"}
            results = run_one(_BoomClient(), "html", "generation", case)
            assert len(results) == 1 and "error" in results[0], results
            saved = json.loads((BEDROCK_ROOT / "results" / "html" / "TC-FAKE__stub.json")
                                .read_text(encoding="utf-8"))
            assert "error" in saved
        finally:
            BEDROCK_ROOT = original_root
    print("  [run_judge] error 격리 self_check 통과")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["generation", "edit", "behavior"])
    ap.add_argument("--format", choices=["json", "html"])
    ap.add_argument("--judge-model", default=None, help="별칭(sonnet/haiku/gemma) 또는 모델 ID")
    ap.add_argument("--region", default=None)
    ap.add_argument("--profile", default=None,
                     help="이 컴퓨터의 기본 AWS 자격증명이 내 계정이 아닐 때, "
                          "~/.aws/credentials에 등록된 내 프로필 이름을 지정한다"
                          "(BEDROCK_PROFILE 환경변수로도 설정 가능)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Bedrock 호출 없이 결정론적 검증 + 배선만 확인(0원)")
    ap.add_argument("--limit", type=int, default=None, help="비용 절약용, 앞에서 N개만")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        DH.self_check()
        DJ.self_check()
        RB.self_check()
        BC.self_check()
        _self_check_error_isolation()
        print("[run_judge] 전체 self_check 통과 (Bedrock 호출 없음)")
        return

    if not args.dataset or not args.format:
        ap.error("--dataset 과 --format 은 --self-check 없이는 필수입니다")

    dataset_path = BEDROCK_ROOT / "datasets" / f"{args.dataset}.jsonl"
    cases = _load_jsonl(dataset_path)
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        print(f"[run_judge] {dataset_path} 에 케이스가 없습니다.")
        return

    client = BC.make_judge_client(dry_run=args.dry_run, model=args.judge_model,
                                   region=args.region, profile=args.profile)
    print(f"[run_judge] dataset={args.dataset} format={args.format} "
          f"judge={client.provider_name()} cases={len(cases)}")

    results = []
    for case in cases:
        results.extend(run_one(client, args.format, args.dataset, case))

    models_seen = sorted({r["model"] for r in results})
    print(f"\n[run_judge] 케이스 {len(cases)}개 x 모델 {len(models_seen) or '?'}종 "
          f"= {len(results)}건 완료 ({', '.join(models_seen) or '없음'}) -> "
          f"results/{args.format}/ 에 저장됨")

    import aggregate
    aggregate.write_summary(args.format, results)


if __name__ == "__main__":
    main()
