"""
run_v10.py — 실제 템플릿 수정 러너
===================================

v8·v9 러너에서 **체인·라우터·생성 경로를 뺐다.** v10 은 전부 수정이라
구조가 단순하다.

    raw → extract() → sanitize_edited() → validate_edited() + v10 검사

## v10 이 v9 러너와 다른 점

    항목 수      must 가 아니라 **템플릿 선택자**로 센다 (아래 ★)
    환각         check_invented — 요청에 없던 낱말이 생겼나
    class        이름표 있는 요소(변경) + 전체 집합(유실) 둘 다
    훅           data-demo-msg 같은 호스트 JS 선언이 지워졌나

## 실행

    python run_v10.py --self-check                     # 호출 없이 검증만
    LLM_PROVIDER=mock python run_v10.py --repeats 1    # 0원, 배선 확인
    BEDROCK_MODEL=gemma LLM_PROVIDER=bedrock RUNNER=OO python run_v10.py
    python run_v10.py --groups D                       # 디자인 파괴만
    python run_v10.py --cases D1,H1
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cases_v10 as CS      # noqa: E402
import checks_v10 as C      # noqa: E402
import provider as PV       # noqa: E402
import templates_v10 as T   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, "result_csv")
RAW_DIR = os.path.join(HERE, "raw_v10")

# 백엔드 RetryService 와 같다 — 최초 1회 + 재시도 maxRetry 회
MAX_RETRY = int(os.environ.get("MAX_RETRY", "3"))
MAX_ATTEMPT = MAX_RETRY + 1

FIELDS = [
    "runner", "provider", "model", "group", "prompt_id", "template", "block",
    "repeat_no", "attempt", "ok", "model_fails", "pipeline_fails",
    "sanitize_damaged", "input_tokens", "output_tokens", "wall_ms",
    "truncated", "note",
]


def score(case, html):
    """정화 전/후 어느 쪽이든 같은 규칙으로 본다."""
    fails = C.validate_edited(case.target, case.before, html)

    if case.want_text and case.want_text not in (html or ""):
        fails.append(("request_not_applied", f"'{case.want_text}' 이(가) 없습니다."))

    # ★ 항목 수는 must 가 아니라 **템플릿 선택자**로 센다.
    #   must 는 `"ul li, .benefit-card"` 로 둘 다 받으므로, must 로 세면
    #   모델이 .benefit-card 를 <li> 로 바꿔도 개수가 맞아 통과한다.
    #   그 구멍이 v10 이 잡으려는 것이라 여기서는 공통 클래스로만 센다.
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
    return fails


def run_case(client, case, repeat_no, seed, raw_dir):
    rows, user = [], case.user

    for attempt in range(1, MAX_ATTEMPT + 1):
        try:
            resp = client.chat(case.system, user, mode="html", seed=seed)
        except Exception as ex:                       # noqa: BLE001
            rows.append(dict(attempt=attempt, ok=0,
                             model_fails=f"call_error:{type(ex).__name__}",
                             pipeline_fails="", sanitize_damaged=0,
                             input_tokens=0, output_tokens=0, wall_ms=0, truncated=0))
            print(f"      ✗ 호출 실패: {ex}")
            break

        raw = resp.content
        _save_raw(raw_dir, case, repeat_no, attempt, raw)

        html = C.extract(raw)
        model_f = score(case, html)                       # 정화 전 — 모델 탓
        after = score(case, C.sanitize_edited(html))      # 정화 후 — 실제 서비스
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
        if attempt < MAX_ATTEMPT:
            msgs = "\n".join(f"- {m}" for _, m in model_f)
            user = f"{case.user}\n\n앞의 출력에 문제가 있었다. 고쳐서 다시 출력해라:\n{msgs}"
    return rows


def _save_raw(raw_dir, case, repeat_no, attempt, raw):
    os.makedirs(raw_dir, exist_ok=True)
    name = f"{case.group}_{case.pid}_r{repeat_no}_a{attempt}.txt"
    with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as f:
        f.write(raw or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="", help="D,P,H 중 골라서 (기본 전부)")
    ap.add_argument("--cases", default="", help="개별 케이스만 (예: D1,H1)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        CS.self_check()
        C.self_check()
        PV.self_check()
        print("\n  --self-check: LLM 호출 없이 검증만 하고 끝냅니다.")
        return

    picked = {c.strip().upper() for c in args.cases.split(",") if c.strip()}
    wanted = [g.strip().upper() for g in args.groups.split(",") if g.strip()]
    if picked:
        known = {c.pid for c in CS.CASES}
        if picked - known:
            raise SystemExit(f"그런 케이스가 없습니다: {sorted(picked - known)}\n"
                             f"있는 것: {', '.join(sorted(known))}")
        cases = [c for c in CS.CASES if c.pid in picked]
    else:
        cases = [c for c in CS.CASES if not wanted or c.group in wanted]
    if not cases:
        raise SystemExit("돌릴 케이스가 없습니다 (군: D, P, H)")

    client = PV.make_client(args.provider)
    runner = os.environ.get("RUNNER", "미지정")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(RAW_DIR, stamp)

    print(f"\n  provider : {client.provider_name()}")
    print(f"  runner   : {runner}")
    print(f"  케이스   : {len(cases)}개 × {args.repeats}회 "
          f"= 최소 {len(cases) * args.repeats}호출 (최대 {MAX_ATTEMPT}회 시도)")
    print()

    rows = []
    for case in cases:
        for repeat_no in range(1, args.repeats + 1):
            t0 = time.time()
            attempts = run_case(client, case, repeat_no, 41 + repeat_no, raw_dir)
            final = attempts[-1]
            mark = "✓" if final["ok"] else "✗"
            parts = []
            if final["model_fails"]:
                parts.append(f"모델:{final['model_fails']}")
            if final["pipeline_fails"]:
                parts.append(f"⚠정화:{final['pipeline_fails']}")
            print(f"    {mark} {case.pid} r{repeat_no} [{T.NAMES[case.tpl]}/{case.block}] "
                  f"({len(attempts)}회, {time.time() - t0:.1f}s) {'  '.join(parts)}")
            for a in attempts:
                rows.append(dict(
                    runner=runner, provider=client.provider_name(),
                    model=getattr(client, "model", client.provider_name()),
                    group=case.group, prompt_id=case.pid,
                    template=T.NAMES[case.tpl], block=case.block,
                    repeat_no=repeat_no, note=case.note, **a))

    os.makedirs(CSV_DIR, exist_ok=True)
    path = os.path.join(CSV_DIR, f"results_v10_{runner}_{stamp}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

    summarize(rows)
    print(f"\n  CSV : {path}")
    print(f"  원문: {raw_dir}")


def summarize(rows):
    by_case = {}
    for r in rows:
        by_case[(r["group"], r["prompt_id"], r["repeat_no"])] = \
            by_case.get((r["group"], r["prompt_id"], r["repeat_no"]), 0) or r["ok"]

    print("\n  ── 군별 최종 통과 ──")
    t = defaultdict(lambda: [0, 0])
    for (g, _, _), ok in by_case.items():
        t[g][0] += ok
        t[g][1] += 1
    labels = {"D": "디자인 파괴", "P": "보존", "H": "준 것만"}
    for g in ("D", "P", "H"):
        if g in t:
            print(f"    {g} {labels[g]:10} {t[g][0]}/{t[g][1]}")

    first = [r for r in rows if r["attempt"] == 1]
    if first:
        print(f"    1차 통과: {sum(r['ok'] for r in first)}/{len(first)}")

    codes = defaultdict(int)
    for r in rows:
        for c in (r["model_fails"] + "|" + r["pipeline_fails"]).split("|"):
            if c:
                codes[c] += 1
    if codes:
        print("\n  ── 실패 유형 ──")
        for c, n in sorted(codes.items(), key=lambda x: -x[1])[:10]:
            print(f"      {c:44} {n}")

    trunc = sum(r["truncated"] for r in rows)
    if trunc:
        print(f"\n  ⚠ 출력 캡에 걸림 {trunc}건 — benefits 는 원본만 811토큰(캡의 53%)")

    timed = [r for r in rows if r["wall_ms"]]
    if timed:
        ms = [r["wall_ms"] for r in timed]
        print(f"\n  응답시간 평균 {sum(ms) / len(ms) / 1000:.2f}s  최대 {max(ms) / 1000:.2f}s")

    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    print(f"  토큰: 입력 {tin:,} · 출력 {tout:,}")
    price = PV.price_of(rows[0]["model"]) if rows else None
    if price:
        usd = tin / 1e6 * price[0] + tout / 1e6 * price[1]
        print(f"  비용: ${usd:.5f}  (약 {usd * 1400:,.0f}원)")


if __name__ == "__main__":
    main()
