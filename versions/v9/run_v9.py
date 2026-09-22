"""
run_v9.py — v8 독립 러너
=========================

백엔드 파이프라인과 **같은 순서**로 돌리고, 그 결과를 채점한다.

    raw → extract() → sanitize() → validate()

v1~v7 은 sanitize 가 없었다. 그래서 "모델은 맞게 냈는데 정화가 망가뜨린" 실패를
영영 못 봤다. v8 은 **정화 전과 후를 둘 다 채점**해서 책임을 가른다.

    model_fails     정화 전에도 실패  → 모델 탓
    pipeline_fails  정화 후에만 실패  → 정화 탓 (모델을 바꿔도 안 고쳐진다)

이 구분이 v8 의 존재 이유다. 모델 비교를 하면서 정화 버그를 모델 탓으로
돌리면 엉뚱한 모델을 고르게 된다.

## 실행

    LLM_PROVIDER=mock   python run_v9.py                 # 0원, 배선 확인
    LLM_PROVIDER=mock   python run_v9.py --self-check    # 호출 없이 검증만
    LLM_PROVIDER=bedrock BEDROCK_MODEL=... python run_v9.py --groups R
    LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b python run_v9.py

## 비용

    --repeats 3 (기본)  G 2 · E 4 · R 8 = 14케이스 × 3 = 42호출
    --groups R 만 하면  8 × 3 = 24호출, 전부 ROUTER 캡(256)이라 아주 싸다

    가장 위험한 축(R)이 가장 싼 축이다. 거기부터 돌릴 것.
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

import cases_v9 as CS       # noqa: E402
import checks_v9 as C       # noqa: E402
import provider as PV       # noqa: E402
import registry_v9 as R     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, "result_csv")
RAW_DIR = os.path.join(HERE, "raw_v9")

# 백엔드 LlmProps.maxRetry 기본값과 같다.
#
# ★ v8 에서 틀렸던 것 — RetryService 는 `attempt <= maxRetry + 1` 로 돈다.
#   즉 **최초 1회 + 재시도 3회 = 최대 4회**다("기본값이면 최대 4회다" 주석).
#   v8 은 총 3회만 돌려서 서비스보다 한 번 덜 줬다.
MAX_RETRY = int(os.environ.get("MAX_RETRY", "3"))
MAX_ATTEMPT = MAX_RETRY + 1

FIELDS = [
    "runner", "provider", "model", "group", "prompt_id", "repeat_no", "attempt",
    "ok", "model_fails", "pipeline_fails", "sanitize_damaged",
    "input_tokens", "output_tokens", "wall_ms", "truncated", "note",
]


# ── 라우터 판정 ───────────────────────────────────────────────────
def _parse_router(text):
    """모델 출력에서 {"op":..,"target":..} 를 뽑는다."""
    t = (text or "").replace("```json", "").replace("```", "").strip()
    s, e = t.find("{"), t.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError:
        return None


def score_router(case, raw):
    obj = _parse_router(raw)
    if obj is None:
        return [("unparseable", "JSON 하나만 출력하세요.")]
    fails = []
    op = (obj.get("op") or "").upper()
    target = obj.get("target")
    if op != case.want_op:
        fails.append((f"op_{op or 'none'}_want_{case.want_op}",
                      f'동작이 "{case.want_op}" 여야 합니다.'))
    if (target or None) != case.want_target:
        fails.append((f"target_{target or 'none'}_want_{case.want_target}",
                      f'대상이 "{case.want_target}" 여야 합니다.'))
    return fails


# ── HTML 판정 ─────────────────────────────────────────────────────
def clean_for(case, html):
    """백엔드 `HtmlPolicy` 대응 — 생성과 수정의 정화 규칙이 **반대**다.

        생성  sanitizeGenerated  data-slot 을 지운다
        수정  sanitizeEdited     data-slot 을 남긴다

    한쪽 규칙을 양쪽에 쓰면 "제목 한 번 고쳤을 뿐인데 그 이벤트는 기간을
    영원히 못 채우는" 사고가 난다(백엔드 HtmlPolicy 주석). v8 이 정확히
    그 상태였고, 그래서 E1·E2·C1 을 아예 못 돌렸다.
    """
    return C.sanitize_generated(html) if case.group == "G" else C.sanitize_edited(html)


def score_html(case, html):
    """정화 전/후 어느 쪽이든 같은 규칙으로 본다."""
    if case.group == "G":
        fails = C.validate_generated(html)
    else:
        fails = C.validate_edited(case.target, case.before, html)

    if case.want_text and case.want_text not in (html or ""):
        fails.append(("request_not_applied", f"'{case.want_text}' 이(가) 없습니다."))

    if case.expect_items is not None and case.target and case.target.must:
        el = C._soup(html).select_one(case.target.selector())
        n = len(el.select(case.target.must)) if el else 0
        if n != case.expect_items:
            fails.append((f"item_count_{n}_want_{case.expect_items}",
                          f"항목이 {case.expect_items}개여야 합니다."))
    return fails


def run_case(client, case, repeat_no, seed, raw_dir):
    """재시도 루프 — 백엔드 RetryService 와 같은 모양.

    되먹임은 실패 '메시지'를 준다. 코드가 아니라 사람 말이어야 모델이 고친다.
    """
    rows = []
    user = case.user

    # ★ 라우터는 재시도하지 않는다 — 실서비스와 맞추기 위해서다.
    #
    #   서버는 정답을 모른다. 사용자가 "버튼 문구 바꿔줘" 라고 했을 때 그게
    #   EDIT 인지 STYLE 인지 판정할 수단이 없으니, 틀린 분류는 그대로
    #   실행된다. 되먹임을 줄 근거 자체가 없다.
    #
    #   그런데 벤치마크는 정답(want_op)을 안다. 그래서 되먹임을 주면
    #   '동작이 "EDIT" 여야 합니다' 처럼 **답을 그대로 알려주게** 된다 —
    #   실측으로 qwen3-coder 가 1차 STYLE 오답 → 2차 즉시 정답이었다.
    #   그 상태로는 어떤 모델이든 최종 100% 가 나와서 비교가 무의미하다.
    #
    #   HTML 군(G·E·C)은 다르다. "hero 영역이 없습니다" 는 서버가 실제로
    #   판정할 수 있는 사실이고, 백엔드 RetryService 가 하는 일 그대로다.
    max_attempt = 1 if case.mode == "router" else MAX_ATTEMPT

    for attempt in range(1, max_attempt + 1):
        try:
            resp = client.chat(case.system, user, mode=case.mode, seed=seed)
        except Exception as ex:                      # noqa: BLE001
            rows.append(dict(attempt=attempt, ok=0, model_fails=f"call_error:{type(ex).__name__}",
                             pipeline_fails="", sanitize_damaged=0,
                             input_tokens=0, output_tokens=0, wall_ms=0, truncated=0))
            print(f"      ✗ 호출 실패: {ex}")
            break

        raw = resp.content
        _save_raw(raw_dir, case, repeat_no, attempt, raw)

        if case.mode == "router":
            model_f = score_router(case, raw)
            pipe_f = []
        else:
            html = C.extract(raw)
            model_f = score_html(case, html)              # 정화 전 — 모델 탓
            after = score_html(case, clean_for(case, html))   # 정화 후 — 실제 서비스
            before_codes = {c for c, _ in model_f}
            pipe_f = [(c, m) for c, m in after if c not in before_codes]

        # ★ 정화 손상은 모델이 따로 틀렸든 말든 손상이다.
        #   "모델도 틀렸을 때만 안 센다"로 두면 정화 버그가 모델 실패에 가려진다
        #   (실제로 그렇게 짰다가 slot_lost 가 통째로 안 보였다).
        damaged = 1 if pipe_f else 0
        ok = 1 if (not model_f and not pipe_f) else 0

        rows.append(dict(
            attempt=attempt, ok=ok,
            model_fails="|".join(c for c, _ in model_f),
            pipeline_fails="|".join(c for c, _ in pipe_f),
            sanitize_damaged=damaged,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            wall_ms=resp.wall_ms, truncated=1 if resp.truncated else 0,
        ))

        if ok:
            break
        if pipe_f and not model_f:
            # 정화가 망가뜨린 것은 모델에게 되먹여도 못 고친다 — 재시도 낭비
            print(f"      ⚠ 정화 손상 (모델 탓 아님): {[c for c, _ in pipe_f]}")
            break
        if attempt < max_attempt:
            msgs = "\n".join(f"- {m}" for _, m in model_f)
            user = f"{case.user}\n\n앞의 출력에 문제가 있었다. 고쳐서 다시 출력해라:\n{msgs}"
    return rows


def run_chain_case(client, cc, repeat_no, seed, raw_dir):
    """누적 수정 — 백엔드 실사용 흐름 그대로.

        doc → 그 블록만 꺼내서 edit 프롬프트 → sanitize → merge → doc'

    ★ 전체 문서를 모델에 넘기지 않는다(부분 재생성). 백엔드가 확정한 방식이다.
    ★ 한 턴이 실패해도 멈추지 않고 이어간다 — "앞 턴이 망가진 채로 계속
      고치면 어떻게 되는가"가 이 군이 보려는 것이기 때문이다.
    """
    doc = CS.START_DOC
    rows = []
    applied = []          # 지금까지 성공한 want_text — 끝까지 살아있어야 한다

    for idx, turn in enumerate(cc.turns, 1):
        b = R.of(turn.block_key)
        before = C.block_html(doc, b)
        system = cc.system_for(turn)
        user = f"{turn.user}\n\n{before}"
        pid = f"{cc.pid}-T{idx}"

        try:
            resp = client.chat(system, user, mode="html", seed=seed)
        except Exception as ex:                       # noqa: BLE001
            rows.append(dict(prompt_id=pid, attempt=1, ok=0,
                             model_fails=f"call_error:{type(ex).__name__}",
                             pipeline_fails="", sanitize_damaged=0,
                             input_tokens=0, output_tokens=0, wall_ms=0, truncated=0))
            print(f"      ✗ {pid} 호출 실패: {ex}")
            break

        raw = resp.content
        _save_raw(raw_dir, cc, repeat_no, idx, raw, suffix=f"T{idx}")

        html = C.extract(raw)
        shim = _TurnCase(b, before, turn)
        model_f = score_html(shim, html)
        clean = C.sanitize_edited(html)   # C군은 전부 수정 경로
        after_f = score_html(shim, clean)
        before_codes = {c for c, _ in model_f}
        pipe_f = [(c, m) for c, m in after_f if c not in before_codes]

        # 서버는 정화한 결과를 병합한다 — 손상도 같이 문서에 남는다
        doc = C.merge(doc, b, clean)

        # ★ 누적 검사 — 이 턴이 앞 턴들의 결과를 무너뜨리지 않았나
        acc = []
        for old in applied:
            if old not in doc:
                acc.append((f"lost_earlier_edit", f"앞 턴의 '{old}' 가 사라졌습니다."))
        for code, msg in C.validate_generated(doc):
            acc.append((f"doc_{code}", msg))

        if turn.want_text and turn.want_text in doc:
            applied.append(turn.want_text)

        ok = 1 if (not model_f and not pipe_f and not acc) else 0
        rows.append(dict(
            prompt_id=pid, attempt=1, ok=ok,
            model_fails="|".join(c for c, _ in model_f),
            pipeline_fails="|".join(c for c, _ in pipe_f + acc),
            sanitize_damaged=1 if pipe_f else 0,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            wall_ms=resp.wall_ms, truncated=1 if resp.truncated else 0))

        mark = "✓" if ok else "✗"
        parts = []
        if model_f:
            parts.append(f"모델:{'|'.join(c for c, _ in model_f)}")
        if pipe_f:
            parts.append(f"⚠정화:{'|'.join(c for c, _ in pipe_f)}")
        if acc:
            parts.append(f"⚠누적:{'|'.join(c for c, _ in acc)}")
        print(f"      {mark} {pid} ({turn.block_key}) {'  '.join(parts)}")

    _save_raw(raw_dir, cc, repeat_no, 99, doc, suffix="FINAL_DOC")
    return rows


class _TurnCase:
    """score_html() 이 기대하는 모양으로 턴을 감싼다."""

    def __init__(self, block, before, turn):
        self.group = "C"
        self.target = block
        self.before = before
        self.want_text = turn.want_text
        self.expect_items = turn.expect_items


def _save_raw(raw_dir, case, repeat_no, attempt, raw, suffix=""):
    os.makedirs(raw_dir, exist_ok=True)
    tail = suffix or f"a{attempt}"
    name = f"{case.group}_{case.pid}_r{repeat_no}_{tail}.txt"
    with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as f:
        f.write(raw or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="", help="G,E,R,C 중 골라서 (기본 전부)")
    ap.add_argument("--cases", default="",
                    help="개별 케이스만 (예: E3,E4,C2). --groups 보다 우선한다")
    ap.add_argument("--skip-slot-cases", action="store_true",
                    help="슬롯 케이스(E1·E2·C1)를 뺀다 — v8 조건 재현용. "
                         "v9 에서는 이 케이스들이 오히려 핵심이라 평소엔 쓰지 않는다. "
                         "v8 결과와 같은 조건으로 비교하고 싶을 때만 쓴다.")
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

    wanted = [g.strip().upper() for g in args.groups.split(",") if g.strip()]
    picked = {c.strip().upper() for c in args.cases.split(",") if c.strip()}

    if picked:
        known = {c.pid for c in CS.CASES} | {c.pid for c in CS.CHAIN_CASES}
        unknown = picked - known
        if unknown:
            raise SystemExit(f"그런 케이스가 없습니다: {sorted(unknown)}\n"
                             f"있는 것: {', '.join(sorted(known))}")
        cases = [c for c in CS.CASES if c.pid in picked]
        chains = [c for c in CS.CHAIN_CASES if c.pid in picked]
    else:
        cases = [c for c in CS.CASES if not wanted or c.group in wanted]
        chains = [c for c in CS.CHAIN_CASES if not wanted or "C" in wanted]

    if args.skip_slot_cases:
        before = len(cases) + len(chains)
        cases = [c for c in cases if not CS.uses_slots(c)]
        chains = [c for c in chains if not CS.uses_slots(c)]
        dropped = before - len(cases) - len(chains)
        if dropped:
            print(f"  --skip-slot-cases: {dropped}개 제외 "
                  f"(v8 조건 재현 — 평소엔 쓰지 마세요)")

    if not cases and not chains:
        raise SystemExit(f"돌릴 케이스가 없습니다 (군: G, E, R, C)")

    client = PV.make_client(args.provider)
    runner = os.environ.get("RUNNER", "미지정")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(RAW_DIR, f"{stamp}")

    n_calls = (len(cases) + sum(len(c.turns) for c in chains)) * args.repeats
    print(f"\n  provider : {client.provider_name()}")
    print(f"  runner   : {runner}")
    print(f"  케이스   : 단일 {len(cases)}개 + 누적 {len(chains)}개"
          f"({sum(len(c.turns) for c in chains)}턴) × {args.repeats}회"
          f" = 최소 {n_calls}호출 (최대 {MAX_ATTEMPT}회 시도)")
    print()

    rows = []
    for case in cases:
        for repeat_no in range(1, args.repeats + 1):
            seed = 41 + repeat_no
            t0 = time.time()
            attempts = run_case(client, case, repeat_no, seed, raw_dir)
            final = attempts[-1]
            mark = "✓" if final["ok"] else "✗"
            parts = []
            if final["model_fails"]:
                parts.append(f"모델:{final['model_fails']}")
            if final["pipeline_fails"]:
                parts.append(f"⚠정화:{final['pipeline_fails']}")
            print(f"    {mark} {case.pid} r{repeat_no} "
                  f"({len(attempts)}회 시도, {time.time() - t0:.1f}s) {'  '.join(parts)}")
            for a in attempts:
                rows.append(dict(
                    runner=runner, provider=client.provider_name(),
                    model=getattr(client, "model", client.provider_name()),
                    group=case.group, prompt_id=case.pid, repeat_no=repeat_no,
                    note=case.note, **a))

    for cc in chains:
        for repeat_no in range(1, args.repeats + 1):
            print(f"    · {cc.pid} r{repeat_no} — {cc.note}")
            for a in run_chain_case(client, cc, repeat_no, 41 + repeat_no, raw_dir):
                rows.append(dict(
                    runner=runner, provider=client.provider_name(),
                    model=getattr(client, "model", client.provider_name()),
                    group="C", repeat_no=repeat_no, note=cc.note, **a))

    os.makedirs(CSV_DIR, exist_ok=True)
    path = os.path.join(CSV_DIR, f"results_v9_{runner}_{stamp}.csv")
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
        key = (r["group"], r["prompt_id"], r["repeat_no"])
        by_case[key] = by_case.get(key, 0) or r["ok"]

    print("\n  ── 군별 최종 통과 (재시도 포함) ──")
    tally = defaultdict(lambda: [0, 0])
    for (g, _, _), ok in by_case.items():
        tally[g][0] += ok
        tally[g][1] += 1
    for g in ("G", "E", "R", "C"):
        if g in tally:
            hit, tot = tally[g]
            print(f"    {g} : {hit}/{tot}")

    first = [r for r in rows if r["attempt"] == 1]
    if first:
        print(f"    1차 통과: {sum(r['ok'] for r in first)}/{len(first)}"
              f"   ← Bedrock 에서는 이게 곧 비용이다")

    damaged = [r for r in rows if r["sanitize_damaged"]]
    if damaged:
        codes = defaultdict(int)
        for r in damaged:
            for c in r["pipeline_fails"].split("|"):
                if c:
                    codes[c] += 1
        print(f"\n  ⚠ 정화가 망가뜨린 출력 {len(damaged)}건 — 모델을 바꿔도 안 고쳐집니다")
        for c, n in sorted(codes.items(), key=lambda x: -x[1]):
            print(f"      {c} : {n}")

    # ── 응답시간
    #
    # ★ v1~v7 과 읽는 법이 다르다.
    #   로컬은 기기 성능·발열이 섞여서 `runner` 안에서만 비교할 수 있었다
    #   (methodology.md §7). Bedrock 은 관리형이라 그 축이 사라져서
    #   **모델 간 직접 비교가 처음으로 가능하다.**
    #   다만 네트워크 왕복(서울→us-east-1)과 시간대별 부하가 섞이므로,
    #   한두 번 값으로 단정하지 말 것.
    timed = [r for r in rows if r["wall_ms"]]
    if timed:
        print("\n  ── 응답시간 ──")
        by_g = defaultdict(list)
        for r in timed:
            by_g[r["group"]].append(r)
        for g in ("G", "E", "R", "C"):
            if g not in by_g:
                continue
            ms = [r["wall_ms"] for r in by_g[g]]
            outs = sum(r["output_tokens"] for r in by_g[g])
            secs = sum(ms) / 1000
            tps = f"{outs / secs:.0f} tok/s" if secs else "-"
            print(f"    {g} : 평균 {sum(ms) / len(ms) / 1000:5.2f}s  "
                  f"최대 {max(ms) / 1000:5.2f}s  ({len(ms)}회, {tps})")
        allms = [r["wall_ms"] for r in timed]
        print(f"    전체: 평균 {sum(allms) / len(allms) / 1000:5.2f}s  "
              f"합 {sum(allms) / 1000:.1f}s")

    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    print(f"\n  토큰: 입력 {tin:,} · 출력 {tout:,}")

    model_id = rows[0]["model"] if rows else ""
    price = PV.price_of(model_id)
    if price:
        usd = tin / 1e6 * price[0] + tout / 1e6 * price[1]
        print(f"  비용: ${usd:.5f}  (약 {usd * 1400:,.0f}원, 1달러 1,400원 기준)")
    else:
        print(f'  비용: awk -v i=<입력단가> -v o=<출력단가> '
              f"'BEGIN{{printf \"%.5f USD\\n\", {tin}/1e6*i + {tout}/1e6*o}}'")


if __name__ == "__main__":
    main()
