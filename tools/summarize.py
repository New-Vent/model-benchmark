#!/usr/bin/env python3
"""results CSV -> 분석용 마크다운 표.

버전 하나의 결과를 읽어서 비교표를 뽑습니다. 출력은 마크다운이라
그대로 versions/<버전>/analysis/findings.md 에 붙여넣을 수 있습니다.

실행
    python tools/summarize.py versions/v1                 # 버전 폴더 (result_csv 전체)
    python tools/summarize.py path/to/results_xxx.csv       # 단일 CSV
    python tools/summarize.py versions/v1 > /tmp/out.md

비교 축
    모델 x 군      어느 모델이 어느 군에서 강한가
    라우터 동작별   동작은 맞히고 대상을 틀리는가
    실패 유형      무엇 때문에 떨어지는가
    회차별 속도     발열로 느려졌는가
    runner x 모델   기기별 시간 (절대 비교 금지, runner 안에서만)
"""
import csv
import glob
import os
import sys
from collections import defaultdict

KNOWN_OPS = ["REWRITE_ALL", "GENERATE", "DELETE", "STYLE", "MOVE", "EDIT", "ADD", "ASK"]
GROUP_ORDER = ["D", "E", "JS", "N", "S", "C", "R", "J", "K", "CHAIN"]


def load_rows(target):
    """CSV 파일 하나 또는 폴더(하위 results_*.csv 전부)를 읽는다."""
    if os.path.isdir(target):
        paths = sorted(glob.glob(os.path.join(target, "**", "results_*.csv"), recursive=True))
    else:
        paths = [target]
    if not paths:
        sys.exit(f"CSV를 찾을 수 없습니다: {target}")

    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            rows.extend(csv.DictReader(f))
    return rows, paths


def as_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def as_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def models_in(rows):
    seen = []
    for r in rows:
        m = r.get("model", "")
        if m and m not in seen:
            seen.append(m)
    return seen


def table(headers, body):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for line in body:
        out.append("| " + " | ".join(str(c) for c in line) + " |")
    return "\n".join(out)


# ── 1. 모델 x 군 통과율 ────────────────────────────────────────────
def section_pass_rate(rows):
    models = models_in(rows)
    groups = [g for g in GROUP_ORDER if any(r["group"] == g for r in rows)]

    first = defaultdict(lambda: [0, 0])      # (model, group) -> [통과, 전체]
    final = defaultdict(dict)                # (model, group) -> {(pid, repeat): 성공여부}

    for r in rows:
        key = (r["model"], r["group"])
        if as_int(r["attempt"]) == 1:
            first[key][0] += as_int(r["hard_ok"])
            first[key][1] += 1
        # runner를 키에 넣지 않으면 여러 사람의 같은 케이스가 한 칸으로 합쳐진다
        case_key = (r.get("runner", ""), r["prompt_id"], r["repeat_no"])
        prev = final[key].get(case_key, 0)
        final[key][case_key] = prev or as_int(r["hard_ok"])

    def fmt(hit, total):
        return f"{hit}/{total}" if total else "-"

    body_first, body_final = [], []
    for m in models:
        row_f, row_l = [m], [m]
        tot_f = tot_fd = tot_l = tot_ld = 0
        for g in groups:
            hit, total = first[(m, g)]
            row_f.append(fmt(hit, total))
            tot_f += hit
            tot_fd += total

            done = final[(m, g)]
            lhit, ltotal = sum(done.values()), len(done)
            row_l.append(fmt(lhit, ltotal))
            tot_l += lhit
            tot_ld += ltotal
        pct_f = f" ({tot_f / tot_fd * 100:.0f}%)" if tot_fd else ""
        pct_l = f" ({tot_l / tot_ld * 100:.0f}%)" if tot_ld else ""
        row_f.append(f"**{tot_f}/{tot_fd}{pct_f}**")
        row_l.append(f"**{tot_l}/{tot_ld}{pct_l}**")
        body_first.append(row_f)
        body_final.append(row_l)

    headers = ["모델"] + groups + ["합계"]
    return ("## 모델 x 군 — 1차 통과 (첫 시도)\n\n"
            + table(headers, body_first)
            + "\n\n## 모델 x 군 — 최종 통과 (재시도 포함)\n\n"
            + table(headers, body_final))


# ── 1-1. CHAIN 파이프라인 전체 통과율 ──────────────────────────────
# CHAIN 그룹은 GEN/PATCH/JSADD/JSMOD처럼 여러 단계(prompt_id)가 한
# 파이프라인을 이루는데, 위 section_pass_rate()의 CHAIN 열은 이 단계들을
# 서로 독립된 케이스처럼 그냥 더한 값이다 — GEN 5/5·PATCH 5/5·JSADD 5/5·
# JSMOD 0/5면 "15/20(75%)"로 보이지만 docs/methodology.md §4("성공 판정은
# 체인 전체가 기준")대로면 끝까지 이어진 체인은 실제로 0개(0%)다. 이 섹션은
# 각 단계 행에 이미 붙어 있는 pair 필드(체인 ID)로 같은 체인의 단계를 묶어
# "체인 전체가 끝까지 성공했는가"를 따로 집계한다.
CHAIN_FALLBACK_RULES = {
    # K가 실패했을 때만 E로 우회하는 설계(cases_chain.py의 CHAIN4)라
    # "모든 단계 통과"가 아니라 "GEN 통과 AND (K 통과 OR E 통과)"가 맞다.
    "CHAIN4": {"require": {"CHAIN4_GEN"}, "any_of": [{"CHAIN4_K"}, {"CHAIN4_E"}]},
}


def section_chain_pipeline(rows):
    chain_rows = [r for r in rows if r["group"] == "CHAIN" and r.get("pair")]
    if not chain_rows:
        return ""

    # 단계 하나의 통과 여부 = (runner, model, prompt_id, repeat_no)에서
    # 재시도(attempt) 중 하나라도 hard_ok=1이면 통과 — section_pass_rate의
    # final 집계와 동일한 규칙.
    stage_passed = {}
    for r in chain_rows:
        key = (r["runner"], r["model"], r["prompt_id"], r["repeat_no"])
        stage_passed[key] = stage_passed.get(key, 0) or as_int(r["hard_ok"])

    # 체인 인스턴스 하나 = (runner, model, pair, repeat_no). 그 안에서
    # 실제로 기록된 단계(prompt_id) 집합을 모은다.
    instances = defaultdict(set)
    for r in chain_rows:
        instances[(r["runner"], r["model"], r["pair"], r["repeat_no"])].add(r["prompt_id"])

    tally = defaultdict(lambda: [0, 0])  # (model, pair) -> [완주, 전체]
    for (runner, model, pair, repeat_no), pids in instances.items():
        rule = CHAIN_FALLBACK_RULES.get(pair)
        if rule:
            ok = (all(stage_passed.get((runner, model, p, repeat_no), 0) for p in rule["require"])
                  and any(all(stage_passed.get((runner, model, p, repeat_no), 0) for p in grp)
                          for grp in rule["any_of"]))
        else:
            ok = all(stage_passed.get((runner, model, p, repeat_no), 0) for p in pids)
        tally[(model, pair)][0] += int(bool(ok))
        tally[(model, pair)][1] += 1

    models = models_in(chain_rows)
    pairs = sorted({p for (_, p) in tally})
    body = []
    for m in models:
        line = [m]
        for p in pairs:
            hit, total = tally.get((m, p), [0, 0])
            line.append(f"{hit}/{total}" if total else "-")
        body.append(line)

    return ("## CHAIN 파이프라인 전체 통과율 (모든 단계가 이어져야 성공 — "
            "위 '모델 x 군' 표의 CHAIN 열과는 다른 수치)\n\n"
            + table(["모델"] + pairs, body)
            + "\n\n> CHAIN4는 설계상 K 성공 또는(K 실패 시) E 성공 중 하나면 통과로 봅니다. "
              "나머지 체인은 기록된 모든 단계가 전부 통과해야 성공입니다.")


# ── 2. 라우터 동작별 정확도 ─────────────────────────────────────────
def expected_op(row):
    """정답이면 router_op 이 곧 정답. 틀렸으면 fails 의 want_ 에서 뽑는다."""
    if as_int(row.get("router_ok")) == 1:
        return row.get("router_op", "")
    for token in str(row.get("fails", "")).split("|"):
        if token.startswith("want_"):
            rest = token[len("want_"):]
            for op in KNOWN_OPS:
                if rest.startswith(op):
                    return op
    return ""


def section_router(rows):
    r_rows = [r for r in rows if r["group"] == "R"]
    if not r_rows:
        return ""

    models = models_in(r_rows)
    acc = defaultdict(lambda: [0, 0])        # (op, model) -> [정답, 전체]
    for r in r_rows:
        op = expected_op(r)
        if not op:
            continue
        acc[(op, r["model"])][0] += as_int(r.get("router_ok"))
        acc[(op, r["model"])][1] += 1

    ops = [o for o in KNOWN_OPS if any((o, m) in acc for m in models)]
    body = []
    for op in ops:
        line = [op]
        for m in models:
            hit, total = acc[(op, m)]
            line.append(f"{hit}/{total}" if total else "-")
        body.append(line)

    return ("## 라우터 — 동작별 정확도 (동작+대상 둘 다 맞아야 정답)\n\n"
            + table(["동작"] + models, body))


# ── 3. 실패 유형 분포 ──────────────────────────────────────────────
def section_fails(rows, top=15):
    hard = defaultdict(int)
    soft = defaultdict(int)
    for r in rows:
        for f in str(r.get("fails", "")).split("|"):
            if f and not f.startswith("want_"):
                hard[f] += 1
        for f in str(r.get("soft_fails", "")).split("|"):
            if f:
                soft[f] += 1

    total_calls = len(rows)
    body = [[k, v, f"{v / total_calls * 100:.0f}%"]
            for k, v in sorted(hard.items(), key=lambda x: -x[1])[:top]]
    out = (f"## 실패 유형 분포 (전체 {total_calls}건 중)\n\n"
           + table(["유형", "건수", "비율"], body))

    if soft:
        sbody = [[k, v, f"{v / total_calls * 100:.0f}%"]
                 for k, v in sorted(soft.items(), key=lambda x: -x[1])]
        out += ("\n\n### 소프트 실패 (후처리로 통과시킨 것)\n\n"
                + table(["유형", "건수", "비율"], sbody))
    return out


# ── 4. 회차별 생성 속도 (발열) ──────────────────────────────────────
def section_drift(rows):
    models = models_in(rows)
    repeats = sorted({as_int(r["repeat_no"]) for r in rows if as_int(r["repeat_no"])})
    if not repeats:
        return ""

    body = []
    for m in models:
        line = [m]
        for rn in repeats:
            vals = [as_float(r["eval_rate"]) for r in rows
                    if r["model"] == m and as_int(r["repeat_no"]) == rn]
            vals = [v for v in vals if v and v > 0]
            line.append(f"{sum(vals) / len(vals):.1f}" if vals else "-")
        body.append(line)

    return ("## 회차별 평균 생성 속도 (tok/s) — 단조 감소면 발열\n\n"
            + table(["모델"] + [f"r{i}" for i in repeats], body))


# ── 5. runner x 모델 시간 ──────────────────────────────────────────
def section_time(rows):
    runners = sorted({r["runner"] for r in rows if r.get("runner")})
    models = models_in(rows)
    if not runners:
        return ""

    backend = {r["runner"]: r.get("backend", "") for r in rows if r.get("runner")}
    body = []
    for m in models:
        line = [m]
        for rn in runners:
            vals = [as_float(r["wall_sec"]) for r in rows
                    if r["model"] == m and r["runner"] == rn]
            vals = [v for v in vals if v is not None]
            line.append(f"{sum(vals) / len(vals):.1f}s" if vals else "-")
        body.append(line)

    headers = ["모델"] + [f"{rn} ({backend.get(rn, '?')})" for rn in runners]
    return ("## runner x 모델 — 평균 응답시간\n\n"
            + table(headers, body)
            + "\n\n> 기기 간 절대 시간 비교는 무효입니다. 같은 runner 열 안에서 모델끼리만 비교하세요.")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    target = sys.argv[1]
    rows, paths = load_rows(target)

    print(f"# 분석 결과 — {target}\n")
    print(f"- 소스 CSV {len(paths)}개, 총 {len(rows)}행")
    print(f"- runner: {', '.join(sorted({r['runner'] for r in rows if r.get('runner')}))}")
    print(f"- 모델: {', '.join(models_in(rows))}\n")

    for section in (section_pass_rate(rows), section_chain_pipeline(rows), section_router(rows),
                    section_fails(rows), section_drift(rows), section_time(rows)):
        if section:
            print(section + "\n")


if __name__ == "__main__":
    main()
