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

    for section in (section_pass_rate(rows), section_router(rows), section_fails(rows),
                    section_drift(rows), section_time(rows)):
        if section:
            print(section + "\n")


if __name__ == "__main__":
    main()
