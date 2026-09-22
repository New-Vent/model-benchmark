"""
aggregate.py — `docs/bedrock/v2-pipeline.md` §27/§29 형식의 요약표 생성
====================================================================
results/{json,html}/*.json 을 전부 읽어 평균 점수·Validation Pass Rate를
계산하고 마크다운 표로 남긴다. run_judge.py가 실행 끝에 자동으로 부른다.
"""

import json
import statistics as stats
import sys
from collections import Counter
from pathlib import Path

# run_judge.py와 동일한 이유 — 일부 Windows 콘솔(cp949)이 이 파일의 "—" 등을
# 인코딩 못 해서 print()에서 죽는다. 이 파일은 단독 실행(python aggregate.py)도
# 되므로 여기서도 방어한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
BEDROCK_ROOT = HERE.parent

SCORE_FIELDS = [
    "requirement_accuracy", "content_accuracy", "schema_compliance_semantic",
    "modification_accuracy", "behavior_correctness",
]

# ══════════════════════════════════════════════════════════════════
#  실패 유형 분포 — docs/reports/v1_v1-v7/v-summary.md 의 "실패 유형 분포"/
#  "소프트 실패" 표와 같은 형식. run_judge.py가 채운 model_fails/pipeline_fails/
#  soft_fails 를 그대로 집계한다.
#
#  ★ 왜 정규화(normalize)가 필요한가 — v-summary.md의 실패 코드(lost_hero,
#    no_ops 등)는 전부 고정 어휘라 그대로 세도 표가 깔끔했다. 이 프로젝트의
#    코드 몇 개(unknown_action_*, disallowed_endpoint_* 등)는 모델이 낸
#    임의 문자열을 코드에 그대로 붙인다(예: unknown_action_eval,
#    unknown_action_execute-script) — 그대로 세면 "같은 종류의 실패"가
#    행마다 쪼개져 분포표가 무의미해진다. 그래서 이런 접두사는 `*`로 묶는다.
# ══════════════════════════════════════════════════════════════════
_DYNAMIC_SUFFIX_PREFIXES = (
    "unknown_action_", "unknown_method_", "disallowed_endpoint_", "external_url_",
    "unknown_variant_", "wrote_server_section_", "duplicate_id_",
    "missing_section_id_", "bad_section_", "unknown_component_type_",
    "bad_component_in_", "target_not_found_", "touched_server_section_",
    "parent_not_found_", "unknown_operation_", "missing_target_",
)


def _normalize_fail(code: str) -> str:
    for prefix in _DYNAMIC_SUFFIX_PREFIXES:
        if code.startswith(prefix):
            return prefix + "*"
    return code


def failure_distribution(fmt: str, results: list, field: str = "hard_fails") -> list:
    """[(유형, 건수, 비율%), ...] — 건수 내림차순. `field`를 "soft_fails"로
    주면 소프트 실패 분포(v-summary.md의 "소프트 실패" 표와 동일)가 나온다."""
    counter = Counter()
    for r in results:
        codes = r.get(fmt, {}).get(field)
        if codes is None:  # hard_fails 필드가 없는 옛 결과는 model_fails로 대체
            codes = r.get(fmt, {}).get("model_fails", []) if field == "hard_fails" else []
        counter.update(_normalize_fail(c) for c in codes)
    total = len(results)
    return [(code, n, round(n / total * 100, 1) if total else 0.0)
            for code, n in counter.most_common()]


def load_results(fmt: str) -> list:
    d = BEDROCK_ROOT / "results" / fmt
    out = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def summarize(fmt: str, results: list) -> dict:
    n = len(results)
    metrics = {}
    for field in SCORE_FIELDS:
        vals = [r[fmt].get(field) for r in results
                if isinstance(r.get(fmt, {}).get(field), (int, float))]
        metrics[field] = round(stats.mean(vals), 2) if vals else None

    validation_pass = sum(1 for r in results if r.get(fmt, {}).get("validation"))
    # ★ hard_ok 필드가 없는 옛 결과 파일(이 필드를 추가하기 전에 만들어진 것)은
    #   validation 값으로 대체한다 — 그때는 soft/hard를 안 나눴으므로 validation이
    #   곧 hard_ok였다(base/checks.py 도입 전 v1 초기와 같은 상태).
    hard_ok_pass = sum(
        1 for r in results
        if r.get(fmt, {}).get("hard_ok", r.get(fmt, {}).get("validation"))
    )
    soft_only = sum(  # hard_ok인데 soft_fails가 남아 있는 경우 — "완전 통과는 아니지만 실사용엔 무해"
        1 for r in results
        if r.get(fmt, {}).get("hard_ok") and r.get(fmt, {}).get("soft_fails")
    )
    sanitize_damaged = sum(1 for r in results if r.get(fmt, {}).get("sanitize_damaged"))
    parse_fail = sum(
        1 for r in results
        if any(f in ("no_json", "bad_json", "no_html", "unparseable_html")
               for f in r.get(fmt, {}).get("model_fails", []))
    )
    spec_only = any(r.get(fmt, {}).get("spec_only") for r in results)

    return {
        "n": n,
        "metrics": metrics,
        "validation_pass_rate": round(validation_pass / n * 100, 1) if n else None,
        "hard_ok_pass_rate": round(hard_ok_pass / n * 100, 1) if n else None,
        "soft_only_count": soft_only,
        "sanitization_violation_rate": round(sanitize_damaged / n * 100, 1) if n else None,
        "parse_success_rate": round((n - parse_fail) / n * 100, 1) if n else None,
        "spec_only": spec_only,
    }


def by_model(fmt: str, results: list) -> dict:
    """모델 별칭별로 결과를 나눠 각각 summarize() 한다 — `versions/v8`의
    "모델 × 군" 비교와 같은 축. `run_judge.py`가 파일명(`<id>__<모델>.json`)
    에서 뽑은 `result["model"]`을 그대로 키로 쓴다."""
    groups: dict[str, list] = {}
    for r in results:
        groups.setdefault(r.get("model", "unspecified"), []).append(r)
    return {model: summarize(fmt, rs) for model, rs in sorted(groups.items())}


def to_markdown(fmt: str, summary: dict, model_summaries: dict | None = None,
                 results: list | None = None) -> str:
    results = results or []
    lines = [f"## {fmt.upper()} 방식 — n={summary['n']} (전체 합계)"]
    if summary["spec_only"]:
        lines.append("\n> ⚠ **spec-only** — 이 결과의 일부/전부는 실제 백엔드 구현이 없는 "
                     "규격(문서 근거만 있음)을 기준으로 채점되었습니다. "
                     "`deterministic_html.py`/`deterministic_json.py`의 모듈 docstring 참고.\n")
    lines.append("| Metric | 값 |")
    lines.append("| --- | ---: |")
    for field, val in summary["metrics"].items():
        if val is not None:
            lines.append(f"| {field} | {val} |")
    lines.append(f"| Validation Pass Rate (all_ok — 하드+소프트 0건) | "
                 f"{summary['validation_pass_rate']}% |")
    lines.append(f"| Hard-Fail Pass Rate (hard_ok — code_fence 등 소프트는 무시) | "
                 f"{summary['hard_ok_pass_rate']}% |")
    if summary["soft_only_count"]:
        lines.append(f"| ↳ 그중 소프트 실패만 남은 건 (code_fence/extra_text) | "
                     f"{summary['soft_only_count']}건 |")
    lines.append(f"| Sanitization Violation Rate | {summary['sanitization_violation_rate']}% |")
    lines.append(f"| Parse Success Rate | {summary['parse_success_rate']}% |")

    if model_summaries and len(model_summaries) > 1:
        lines.append(f"\n### 모델 {len(model_summaries)}종 비교 (`versions/v8`와 같은 축)")
        score_fields = [f for f in SCORE_FIELDS
                        if any(s["metrics"].get(f) is not None for s in model_summaries.values())]
        header = ["모델", "n", "all_ok", "hard_ok"] + score_fields
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for model, s in model_summaries.items():
            row = [model, str(s["n"]), f"{s['validation_pass_rate']}%", f"{s['hard_ok_pass_rate']}%"]
            row += [str(s["metrics"].get(f, "-")) for f in score_fields]
            lines.append("| " + " | ".join(row) + " |")

    hard_dist = failure_distribution(fmt, results, "hard_fails")
    if hard_dist:
        lines.append(f"\n### 실패 유형 분포 (전체 {summary['n']}건 중, "
                     f"`docs/reports/v1_v1-v7/v-summary.md`와 같은 형식)")
        lines.append("| 유형 | 건수 | 비율 |")
        lines.append("| --- | --- | --- |")
        for code, n, pct in hard_dist:
            lines.append(f"| {code} | {n} | {pct}% |")

    soft_dist = failure_distribution(fmt, results, "soft_fails")
    if soft_dist:
        lines.append(f"\n#### 소프트 실패 (§4-1 — hard_ok 판정에는 반영 안 됨)")
        lines.append("| 유형 | 건수 | 비율 |")
        lines.append("| --- | --- | --- |")
        for code, n, pct in soft_dist:
            lines.append(f"| {code} | {n} | {pct}% |")

    return "\n".join(lines)


def write_summary(fmt: str, results: list | None = None) -> Path:
    results = results if results is not None else load_results(fmt)
    summary = summarize(fmt, results)
    model_summaries = by_model(fmt, results)
    md = to_markdown(fmt, summary, model_summaries, results)
    out_path = BEDROCK_ROOT / "results" / f"summary_{fmt}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\n{md}\n\n[aggregate] -> {out_path}")
    return out_path


def self_check():
    fake = [
        {"model": "gemma", "html": {"requirement_accuracy": 5, "content_accuracy": 4,
                   "validation": True, "hard_ok": True, "sanitize_damaged": False,
                   "model_fails": [], "soft_fails": [], "spec_only": False}},
        {"model": "haiku", "html": {"requirement_accuracy": 3, "content_accuracy": 3,
                   "validation": False, "hard_ok": False, "sanitize_damaged": True,
                   "model_fails": ["lost_hero"], "soft_fails": [], "spec_only": False}},
        # ★ hard_ok인데 soft만 남은 경우 — code_fence를 감쌌지만 내용은 멀쩡함
        {"model": "gemma", "html": {"requirement_accuracy": 4, "content_accuracy": 4,
                   "validation": False, "hard_ok": True, "sanitize_damaged": False,
                   "model_fails": ["code_fence"], "soft_fails": ["code_fence"], "spec_only": False}},
    ]
    s = summarize("html", fake)
    assert s["n"] == 3
    assert s["metrics"]["requirement_accuracy"] == 4.0
    assert s["validation_pass_rate"] == round(1 / 3 * 100, 1)   # gemma#1만 all_ok
    assert s["hard_ok_pass_rate"] == round(2 / 3 * 100, 1)      # gemma#1·gemma#2(soft만)
    assert s["soft_only_count"] == 1
    assert s["sanitization_violation_rate"] == round(1 / 3 * 100, 1)
    md = to_markdown("html", s, results=fake)
    assert "requirement_accuracy" in md and "Hard-Fail Pass Rate" in md
    assert "lost_hero" in md and "실패 유형 분포" in md
    assert "code_fence" in md and "소프트 실패" in md

    hard_dist = failure_distribution("html", fake, "hard_fails")
    assert ("lost_hero", 1, round(1 / 3 * 100, 1)) in hard_dist
    soft_dist = failure_distribution("html", fake, "soft_fails")
    assert ("code_fence", 1, round(1 / 3 * 100, 1)) in soft_dist

    # 동적 접미사가 붙는 코드는 *로 뭉쳐야 한다 (v-summary.md 형식이 깨지지 않게)
    dynamic = [
        {"model": "x", "html": {"hard_fails": ["unknown_action_eval"], "soft_fails": []}},
        {"model": "x", "html": {"hard_fails": ["unknown_action_execute-script"], "soft_fails": []}},
    ]
    dyn_dist = failure_distribution("html", dynamic, "hard_fails")
    assert dyn_dist == [("unknown_action_*", 2, 100.0)], dyn_dist

    per_model = by_model("html", fake)
    assert set(per_model) == {"gemma", "haiku"}
    assert per_model["gemma"]["hard_ok_pass_rate"] == 100.0  # 둘 다 hard_ok
    assert per_model["gemma"]["validation_pass_rate"] == 50.0  # 하나는 soft로 all_ok 실패
    assert per_model["haiku"]["hard_ok_pass_rate"] == 0.0
    md = to_markdown("html", s, per_model)
    assert "gemma" in md and "haiku" in md and "모델 2종 비교" in md and "hard_ok" in md

    # 옛 결과(soft/hard 분리 이전, hard_ok 필드 없음) 하위 호환 — validation으로 대체
    legacy = [{"model": "old", "html": {"validation": True, "model_fails": [], "spec_only": False}}]
    s_legacy = summarize("html", legacy)
    assert s_legacy["hard_ok_pass_rate"] == 100.0

    print("  [aggregate] self_check 통과")


if __name__ == "__main__":
    self_check()
