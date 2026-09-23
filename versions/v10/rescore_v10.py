"""
rescore_v10.py
====================================================================

## 무엇이 어긋났나

백엔드 `Slots.classMap()` 은 **이름표 붙은 요소**(root·slot·id)의 class 만
대조한다. 그 주석이 이유를 직접 적어놨다 —

    "이 문구 강조해줘" → span.highlight 가 늘어난다.
     전체를 묶으면 이 둘이 영원히 실패한다."

v10 의 `class_lost` 는 전체 집합을 본다. 즉 **백엔드가 의식적으로 거부한
정책**으로 채점한 것이다. P2 실패 12건이 전부 `class_lost_highlight` 다.

`href_lost` · `hook_lost` 는 백엔드에 아예 없다. 이건 거부된 게 아니라
**아직 안 정한 것**이라 버리지 않고 따로 집계한다.

반대로 v10 에 **없는** 것도 있다 — 백엔드 `checkPreserved` 의
`id_lost_` / `id_invented_`. 여기서 채워 넣는다.

## 세 단

    T1 백엔드 게이트   백엔드 validateEdited 가 실제로 내는 코드
    T2 요청 이행       시킨 대로 했나 — 백엔드엔 검사가 없지만 우리가 재는 본질
    T3 관측            백엔드에 없는 추가 검사. 점수에 넣지 않고 따로 센다

    통과 = T1 · T2 둘 다 없음

## 1차만 센다

재시도 2~4회차는 **당시 오탐이 섞인 피드백**을 받고 나온 출력이다.
D2 가 그걸 그대로 보여준다 — 시도1 은 깨끗이 통과했는데, 틀린 지적을
받은 시도2·3 에서 훅이 전멸했다. 그 경로는 지금 규칙으로 다시 매겨도
"오염된 입력에 대한 응답" 이라 의미가 없다. v4 에서 겪은 것과 같다.

## 실행

    python rescore_v10.py
    python rescore_v10.py --all-attempts    # 재시도까지 (참고용)
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cases_v10 as CS      # noqa: E402
import checks_v10 as C      # noqa: E402
import templates_v10 as T   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw_v10")
CSV_DIR = os.path.join(HERE, "result_csv")

RAW_NAME = re.compile(r"^(?P<group>[DPH])_(?P<pid>\w+?)_r(?P<rep>\d+)_a(?P<att>\d+)\.txt$")

# ── 단 구분 ───────────────────────────────────────────────────────
#
# T3 = 백엔드에 없는 검사. 접두사로 가른다.
#   class_lost_  ★ 백엔드가 **거부**했다 (classMap 주석 참고)
#   href_lost    아직 안 정함
#   hook_lost_   아직 안 정함 (data-behavior 로 갈 자리)
T3_PREFIX = ("class_lost_", "href_lost", "hook_lost_")

# T2 = 요청을 이행했나. 백엔드엔 검사가 없지만 모델 적합성의 본질이다.
T2_PREFIX = ("request_not_applied", "item_count_", "value_lost_")


def tier(code: str) -> str:
    if code.startswith(T3_PREFIX):
        return "T3"
    if code.startswith(T2_PREFIX):
        return "T2"
    return "T1"


def ids_in(soup) -> set:
    return {el["id"] for el in soup.select("[id]") if el.get("id", "").strip()}


def backend_score(case, html: str) -> list:
    """백엔드 develop 규칙 + 벤치마크 요청-이행 검사.

    `checks_v10.validate_edited` 에서 T3 를 걷어내고, 백엔드엔 있는데
    v10 에 빠져 있던 id 대조를 더한다.
    """
    fails = [(c, m) for c, m in C.validate_edited(case.target, case.before, html)
             if tier(c) != "T3"]

    # ★ 백엔드 checkPreserved 에는 있는데 v10 validate_edited 에 없던 것
    was, now = ids_in(C._soup(case.before)), ids_in(C._soup(html))
    for k in sorted(was - now):
        fails.append((f"id_lost_{k}", f'id="{k}" 가 없어졌습니다.'))
    for k in sorted(now - was):
        fails.append((f"id_invented_{k}", f'id="{k}" 를 새로 만들지 마세요.'))

    # T2 — run_v10.score() 와 같은 규칙
    if case.want_text and case.want_text not in (html or ""):
        fails.append(("request_not_applied", f"'{case.want_text}' 이(가) 없습니다."))
    if case.expect_items is not None:
        n = T.item_count(html, case.block)
        if n != case.expect_items:
            fails.append((f"item_count_{n}_want_{case.expect_items}",
                          f"항목이 {case.expect_items}개여야 합니다."))
    if case.check_invented:
        fails += C.check_items_preserved(case.before, html, case.block,
                                         source=case.target.source)
    return fails


def observed(case, html: str) -> list:
    """T3 — 점수에는 안 넣고 따로 세는 것."""
    return [(c, m) for c, m in C.validate_edited(case.target, case.before, html)
            if tier(c) == "T3"]


def model_of(stamp: str) -> str:
    hits = glob.glob(os.path.join(CSV_DIR, f"results_v10_*_{stamp}.csv"))
    if not hits:
        return stamp
    with open(hits[0], encoding="utf-8") as f:
        row = next(csv.DictReader(f), None)
    return row["model"] if row else stamp


SHORT = {
    "google.gemma-3-27b-it": "gemma",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "haiku",
    "openai.gpt-oss-120b-1:0": "oss120",
    "qwen.qwen3-coder-30b-a3b-v1:0": "qwen",
}

BY_PID = {c.pid: c for c in CS.CASES}
LABELS = {"D": "디자인 파괴", "P": "보존", "H": "준 것만"}


def rescore_dir(stamp: str, all_attempts: bool):
    model = model_of(stamp)
    name = SHORT.get(model, model)
    print(f"\n═══════════ {name} ═══════════")

    rows = []
    for path in sorted(glob.glob(os.path.join(RAW_DIR, stamp, "*.txt"))):
        m = RAW_NAME.match(os.path.basename(path))
        if not m:
            print(f"  ⚠ 이름 규칙에 안 맞는 파일: {os.path.basename(path)}")
            continue
        att = int(m["att"])
        if not all_attempts and att != 1:
            continue
        case = BY_PID.get(m["pid"])
        if case is None:
            print(f"  ⚠ 없는 케이스: {m['pid']}")
            continue

        raw = open(path, encoding="utf-8").read()
        html = C.sanitize_edited(C.extract(raw))
        fails = backend_score(case, html)
        obs = observed(case, html)
        rows.append(dict(case=case, rep=int(m["rep"]), att=att,
                         fails=fails, obs=obs, ok=not fails))
    if not rows:
        print("  (원문 없음)")
        return None

    for r in sorted(rows, key=lambda r: (r["case"].pid, r["rep"], r["att"])):
        c = r["case"]
        mark = "✓" if r["ok"] else "✗"
        tail = "|".join(k for k, _ in r["fails"])
        note = "|".join(sorted({k for k, _ in r["obs"]}))
        line = (f"    {mark} {c.pid} r{r['rep']}"
                + (f" a{r['att']}" if all_attempts else "")
                + f" [{T.NAMES[c.tpl]}/{c.block}] {tail}")
        print(line + (f"   ·관측: {note}" if note else ""))

    first = [r for r in rows if r["att"] == 1]
    per_group = defaultdict(lambda: [0, 0])
    for r in first:
        per_group[r["case"].group][0] += r["ok"]
        per_group[r["case"].group][1] += 1
    print()
    for g in ("D", "P", "H"):
        if g in per_group:
            a, b = per_group[g]
            print(f"    {g} {LABELS[g]:10} {a}/{b}")
    passed = sum(r["ok"] for r in first)
    print(f"    ── 1차 통과: {passed}/{len(first)}")

    codes = defaultdict(int)
    for r in rows:
        for k, _ in r["fails"]:
            codes[k] += 1
    if codes:
        print("  ── 남은 실패 ──")
        for k, n in sorted(codes.items(), key=lambda x: -x[1]):
            print(f"      [{tier(k)}] {k:40} {n}")

    obs_codes = defaultdict(int)
    for r in rows:
        for k, _ in r["obs"]:
            obs_codes[k] += 1
    if obs_codes:
        print("  ── 관측(점수 밖, 백엔드에 없는 검사) ──")
        for k, n in sorted(obs_codes.items(), key=lambda x: -x[1]):
            print(f"      {k:40} {n}")

    return name, passed, len(first), dict(per_group)


def null_probe():
    """★ 「아무것도 안 하고 원본을 그대로 돌려줬다」 면 통과하는 케이스는?

    통과율을 읽기 전에 반드시 봐야 하는 숫자다. 여기 걸리는 케이스는
    **망가뜨렸는지만** 보고 **시킨 일을 했는지는 안 본다.**
    그 케이스의 ✓ 는 "잘했다" 가 아니라 "안 부쉈다" 는 뜻이다.
    """
    free = [c.pid for c in CS.CASES if not backend_score(c, c.before)]
    print("\n  ── 무변경 통과 검사 ──")
    print(f"    원본을 그대로 돌려줘도 통과하는 케이스: "
          f"{', '.join(free) if free else '없음'} ({len(free)}/{len(CS.CASES)})")
    if free:
        print("    → 이 케이스의 ✓ 는 '잘했다' 가 아니라 '안 부쉈다' 는 뜻이다.")
    return free


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-attempts", action="store_true",
                    help="재시도까지 본다 (피드백이 오염돼 있어 참고용)")
    args = ap.parse_args()

    stamps = sorted(d for d in os.listdir(RAW_DIR)
                    if os.path.isdir(os.path.join(RAW_DIR, d)))
    print(f"원문 {len(stamps)}회분 · 호출 0회 · 비용 0원")
    if args.all_attempts:
        print("⚠ 재시도 경로는 당시 오탐 피드백을 받고 나온 출력입니다.")

    out = [r for r in (rescore_dir(s, args.all_attempts) for s in stamps) if r]

    print("\n\n═══ 요약 (1차 통과, 백엔드 develop 규칙) ═══")
    print(f"  {'모델':10} {'D':>5} {'P':>5} {'H':>5}   합계")
    for name, passed, total, per_group in out:
        cols = "".join(
            f"{per_group[g][0]}/{per_group[g][1]:<3}".rjust(6) if g in per_group
            else "    — " for g in ("D", "P", "H"))
        print(f"  {name:10}{cols}   {passed}/{total}")

    null_probe()


if __name__ == "__main__":
    main()
