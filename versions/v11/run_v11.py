"""
run_v11.py — 두 arm 을 나란히 돌린다
=====================================

    raw → extract → sanitize_edited → validate_edited + v11 검사

## v10 러너와 다른 점

    arm        mirror / proposal 을 CSV 에 기록한다. 비교는 **arm 끼리만**
    라우터     R군은 문서를 안 받고 JSON 을 낸다 — 채점 경로가 다르다
    무변경     want_change 케이스는 원본 그대로면 실패

## 실행

    python run_v11.py --self-check                      # 호출 없이 검증만
    LLM_PROVIDER=mock python run_v11.py --repeats 1     # 0원, 배선 확인
    python run_v11.py --plan                            # ★ 호출 수·비용만 계산

    BEDROCK_MODEL=gemma LLM_PROVIDER=bedrock RUNNER=OO \
      python run_v11.py --arm mirror   --repeats 2
    python run_v11.py --arm proposal --groups R         # 라우터만 (제일 쌈)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cases_v11 as CS      # noqa: E402
import checks_v11 as C      # noqa: E402
import prompts_v11 as P     # noqa: E402
import provider as PV       # noqa: E402
import templates_v11 as T   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, "result_csv")
RAW_DIR = os.path.join(HERE, "raw_v11")

MAX_RETRY = int(os.environ.get("MAX_RETRY", "3"))
MAX_ATTEMPT = MAX_RETRY + 1       # 백엔드 RetryService 와 같다

FIELDS = [
    "runner", "provider", "model", "arm", "group", "prompt_id", "template",
    "block", "repeat_no", "attempt", "ok", "model_fails", "pipeline_fails",
    "sanitize_damaged", "input_tokens", "output_tokens", "wall_ms",
    "truncated", "note",
]


# ── 채점 · HTML ───────────────────────────────────────────────────
def score(case, html):
    """정화 전/후 어느 쪽이든 같은 규칙으로 본다."""
    fails = C.validate_edited(case.target, case.before, html)

    if case.want_text and case.want_text not in (html or ""):
        fails.append(("request_not_applied", f"'{case.want_text}' 이(가) 없습니다."))

    # ★ 항목 수는 must 가 아니라 **템플릿 선택자**로 센다.
    #   must 는 "ul li, .benefit-card" 로 둘 다 받으므로, must 로 세면
    #   모델이 .benefit-card 를 <li> 로 바꿔도 개수가 맞아 통과한다.
    if case.expect_items is not None:
        n = T.item_count(html, case.block)
        if n != case.expect_items:
            sel = T.ITEM_SELECTOR[case.block]
            fails.append((f"item_count_{n}_want_{case.expect_items}",
                          f"항목이 {case.expect_items}개여야 합니다. "
                          f"기존 항목과 같은 구조({sel})로 만드세요."))

    if case.check_invented:
        fails += C.check_items_preserved(case.before, html, case.block,
                                         source=case.target.source)
    # ── v11 추가
    if case.want_change:
        fails += C.check_text_changed(case.before, html)
    if case.check_values:
        fails += C.check_values_intact(case.before, html, case.allow_new_values)
    return fails


# ── 채점 · 라우터 ─────────────────────────────────────────────────
_NULLISH = {None, "", "null", "None", "없음"}


def _parse_router(raw: str):
    """모델 출력에서 JSON 을 뽑는다. 백엔드 LlmSmokeTest 와 같은 방식."""
    t = (raw or "").replace("```json", "").replace("```", "")
    s, e = t.find("{"), t.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError:
        return None


def _ops_of(obj, arm):
    """arm 별로 ops 리스트를 평평하게 만든다 → [(op, target, content)]"""
    if obj is None:
        return None
    if arm == P.MIRROR:
        if "op" not in obj:
            return None
        return [(obj.get("op"), obj.get("target"), None)]
    ops = obj.get("ops")
    if not isinstance(ops, list):
        return None
    return [(o.get("op"), o.get("target"), o.get("content"))
            for o in ops if isinstance(o, dict)]


def score_router(case, raw, arm):
    got = _ops_of(_parse_router(raw), arm)
    if got is None:
        return [("unparseable", "JSON 을 못 읽었습니다. JSON 하나만 출력하세요.")]

    fails = []
    want = case.expect

    # ★ MIRROR 는 복합 요청을 담을 자리가 없다. 모델 탓이 아니라 **스키마 탓**이고,
    #   그게 v11 이 재려는 것이다. 코드 이름으로 구분해서 나중에 섞이지 않게 한다.
    if arm == P.MIRROR and case.multi:
        return [("schema_cannot_express",
                 f"요청에 동작이 {len(want)}개인데 스키마가 1개만 담습니다.")]

    if len(got) != len(want):
        fails.append((f"ops_{len(got)}_want_{len(want)}",
                      f"동작이 {len(want)}개여야 합니다."))

    for i, (wop, wtgt, wcontent) in enumerate(want):
        if i >= len(got):
            break
        gop, gtgt, gcontent = got[i]
        if case.check_op and gop != wop:
            fails.append((f"op_{i+1}_{gop}_want_{wop}", f"{i+1}번째 동작이 틀렸습니다."))
        if gtgt != wtgt:
            fails.append((f"target_{i+1}_{gtgt}_want_{wtgt}",
                          f"{i+1}번째 영역이 틀렸습니다."))
        if arm != P.PROPOSAL:
            continue
        # ★★ 여기가 되묻기의 전제다
        has = gcontent not in _NULLISH
        if wcontent and not has:
            fails.append((f"content_{i+1}_missing",
                          f"{i+1}번째: 사용자가 말한 내용을 content 에 옮기세요."))
        if not wcontent and has:
            fails.append((f"content_{i+1}_invented",
                          f"{i+1}번째: 사용자가 내용을 안 말했는데 content 를 "
                          f"지어냈습니다({str(gcontent)[:30]}). null 로 두세요."))
    return fails


# ── 실행 ──────────────────────────────────────────────────────────
def run_case(client, case, arm, repeat_no, seed, raw_dir):
    rows, user, system = [], case.user, case.system(arm)
    router = case.kind == "router"
    # 라우터는 재시도하지 않는다 — 서버가 정답을 모르므로 피드백 근거가 없다.
    # (v8 에서 피드백이 답을 흘려 아무 모델이나 통과시킨 전례가 있다)
    max_attempt = 1 if router else MAX_ATTEMPT

    for attempt in range(1, max_attempt + 1):
        try:
            resp = client.chat(system, user,
                               mode="router" if router else "html", seed=seed)
        except Exception as ex:                       # noqa: BLE001
            rows.append(dict(attempt=attempt, ok=0,
                             model_fails=f"call_error:{type(ex).__name__}",
                             pipeline_fails="", sanitize_damaged=0,
                             input_tokens=0, output_tokens=0, wall_ms=0, truncated=0))
            print(f"      ✗ 호출 실패: {ex}")
            break

        raw = resp.content
        _save_raw(raw_dir, case, arm, repeat_no, attempt, raw)

        if router:
            model_f = score_router(case, raw, arm)
            pipe_f = []
        else:
            html = C.extract(raw)
            model_f = score(case, html)                   # 정화 전 — 모델 탓
            after = score(case, C.sanitize_edited(html))   # 정화 후 — 실제 서비스
            before_codes = {c for c, _ in model_f}
            pipe_f = [(c, m) for c, m in after if c not in before_codes]

        ok = 1 if (not model_f and not pipe_f) else 0
        rows.append(dict(
            attempt=attempt, ok=ok,
            model_fails="|".join(c for c, _ in model_f),
            pipeline_fails="|".join(c for c, _ in pipe_f),
            sanitize_damaged=1 if pipe_f else 0,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            wall_ms=resp.wall_ms, truncated=1 if resp.truncated else 0))

        if ok:
            break
        if pipe_f and not model_f:
            print(f"      ⚠ 정화 손상 (모델 탓 아님): {[c for c, _ in pipe_f]}")
            break
        if attempt < max_attempt:
            msgs = "\n".join(f"- {m}" for _, m in model_f)
            user = f"{case.user}\n\n앞의 출력에 문제가 있었다. 고쳐서 다시 출력해라:\n{msgs}"
    return rows


def _save_raw(raw_dir, case, arm, repeat_no, attempt, raw):
    os.makedirs(raw_dir, exist_ok=True)
    name = f"{arm}_{case.group}_{case.pid}_r{repeat_no}_a{attempt}.txt"
    with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as f:
        f.write(raw or "")


def pick(args):
    picked = {c.strip().upper() for c in args.cases.split(",") if c.strip()}
    wanted = [g.strip().upper() for g in args.groups.split(",") if g.strip()]
    if picked:
        unknown = picked - set(CS.BY_PID)
        if unknown:
            raise SystemExit(f"그런 케이스가 없습니다: {sorted(unknown)}\n"
                             f"있는 것: {', '.join(sorted(CS.BY_PID))}")
        return [c for c in CS.ALL if c.pid in picked]
    out = [c for c in CS.ALL if not wanted or c.group in wanted]
    if not out:
        raise SystemExit("돌릴 케이스가 없습니다 (군: D, P, H, V, R)")
    return out


def plan(cases, arms, repeats):
    """★ 호출 없이 호출 수·비용만 낸다. 돌리기 전에 항상 이걸 먼저 본다."""
    html = [c for c in cases if c.kind == "html"]
    router = [c for c in cases if c.kind == "router"]
    print(f"\n  arm {len(arms)}종 × 반복 {repeats}회")
    print(f"    HTML   {len(html)}케이스 → 최소 {len(html)*len(arms)*repeats}호출 "
          f"(재시도로 최대 ×{MAX_ATTEMPT})")
    print(f"    라우터 {len(router)}케이스 → {len(router)*len(arms)*repeats}호출 (재시도 없음)")

    # v10 실측 평균 토큰 (gemma 기준). 라우터는 v8 실측.
    HTML_IN, HTML_OUT = 1100, 700
    RT_IN, RT_OUT = 220, 40
    for key in ("gemma", "haiku"):
        p = PV.price_of(PV.BEDROCK_MODELS[key][0])
        n_h = len(html) * len(arms) * repeats
        n_r = len(router) * len(arms) * repeats
        lo = ((n_h * HTML_IN + n_r * RT_IN) / 1e6 * p[0]
              + (n_h * HTML_OUT + n_r * RT_OUT) / 1e6 * p[1])
        print(f"    {key:7} 전부 1차 통과 시 약 {lo*1400:,.0f}원 · "
              f"전부 {MAX_ATTEMPT}회 재시도 시 약 {lo*MAX_ATTEMPT*1400:,.0f}원")
    print("\n  ※ 실제는 두 값 사이입니다. v10 실측은 gemma 27케이스에 57원이었습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="", help="D,P,H,V,R 중 골라서 (기본 전부)")
    ap.add_argument("--cases", default="", help="개별 케이스만 (예: D1,R2)")
    ap.add_argument("--arm", default=P.MIRROR,
                    help="mirror | proposal | both (기본 mirror)")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--plan", action="store_true", help="호출 없이 비용만 계산")
    args = ap.parse_args()

    if args.self_check:
        CS.self_check()
        C.self_check()
        PV.self_check()
        print("\n  --self-check: LLM 호출 없이 검증만 하고 끝냅니다.")
        return

    arms = list(P.ARMS) if args.arm == "both" else [args.arm]
    for a in arms:
        if a not in P.ARMS:
            raise SystemExit(f"모르는 arm: {a} (mirror | proposal | both)")
    cases = pick(args)

    if args.plan:
        plan(cases, arms, args.repeats)
        return

    client = PV.make_client(args.provider)
    runner = os.environ.get("RUNNER", "미지정")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(RAW_DIR, stamp)

    print(f"\n  provider : {client.provider_name()}")
    print(f"  runner   : {runner}   arm: {', '.join(arms)}")
    plan(cases, arms, args.repeats)
    print()

    rows = []
    for arm in arms:
        print(f"  ═══ arm: {arm} ═══")
        for case in cases:
            for repeat_no in range(1, args.repeats + 1):
                t0 = time.time()
                attempts = run_case(client, case, arm, repeat_no,
                                    41 + repeat_no, raw_dir)
                final = attempts[-1]
                parts = []
                if final["model_fails"]:
                    parts.append(f"모델:{final['model_fails']}")
                if final["pipeline_fails"]:
                    parts.append(f"⚠정화:{final['pipeline_fails']}")
                where = (T.NAMES[case.tpl] + "/" + case.block
                         if case.kind == "html" else "라우터")
                print(f"    {'✓' if final['ok'] else '✗'} {case.pid} r{repeat_no} "
                      f"[{where}] ({len(attempts)}회, {time.time()-t0:.1f}s) "
                      f"{'  '.join(parts)}")
                for a in attempts:
                    rows.append(dict(
                        runner=runner, provider=client.provider_name(),
                        model=getattr(client, "model", client.provider_name()),
                        arm=arm, group=case.group, prompt_id=case.pid,
                        template=T.NAMES[case.tpl] if case.kind == "html" else "",
                        block=getattr(case, "block", ""),
                        repeat_no=repeat_no, note=case.note, **a))

    os.makedirs(CSV_DIR, exist_ok=True)
    path = os.path.join(CSV_DIR, f"results_v11_{runner}_{stamp}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

    summarize(rows)
    print(f"\n  CSV : {path}")
    print(f"  원문: {raw_dir}")


LABELS = {"D": "디자인 파괴", "P": "보존", "H": "준 것만",
          "V": "값 변조", "R": "라우터"}


def summarize(rows):
    first = [r for r in rows if r["attempt"] == 1]
    for arm in sorted({r["arm"] for r in rows}):
        print(f"\n  ── arm: {arm} · 1차 통과 ──")
        t = defaultdict(lambda: [0, 0])
        for r in (x for x in first if x["arm"] == arm):
            t[r["group"]][0] += r["ok"]
            t[r["group"]][1] += 1
        for g in ("D", "P", "H", "V", "R"):
            if g in t:
                print(f"    {g} {LABELS[g]:10} {t[g][0]}/{t[g][1]}")
        tot = [x for x in first if x["arm"] == arm]
        print(f"    합계 {sum(x['ok'] for x in tot)}/{len(tot)}")

    codes = defaultdict(int)
    for r in rows:
        for c in (r["model_fails"] + "|" + r["pipeline_fails"]).split("|"):
            if c:
                codes[c] += 1
    if codes:
        print("\n  ── 실패 유형 ──")
        for c, n in sorted(codes.items(), key=lambda x: -x[1])[:12]:
            print(f"      {c:46} {n}")

    trunc = sum(r["truncated"] for r in rows)
    if trunc:
        print(f"\n  ⚠ 출력 캡에 걸림 {trunc}건 "
              f"— benefits 는 원본만 811토큰, 라우터 캡은 256")

    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    print(f"\n  토큰: 입력 {tin:,} · 출력 {tout:,}")
    price = PV.price_of(rows[0]["model"]) if rows else None
    if price:
        usd = tin / 1e6 * price[0] + tout / 1e6 * price[1]
        print(f"  비용: ${usd:.5f}  (약 {usd*1400:,.0f}원)")


if __name__ == "__main__":
    main()
