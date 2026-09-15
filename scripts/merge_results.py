#!/usr/bin/env python3
"""여러 컴퓨터(runner)의 벤치마크 결과를 하나로 합칩니다.

results/raw/<runner>/ 아래의 CSV/JSON을 전부 모아
results/merged/combined_v8_<날짜>.csv 로 만듭니다.

실행: python scripts/merge_results.py
"""
import csv
import glob
import json
import os
from datetime import datetime

RAW_DIR = os.path.join("results", "raw")
MERGED_DIR = os.path.join("results", "merged")


def load_envs():
    envs = {}
    for path in glob.glob(os.path.join(RAW_DIR, "*", "env_*.json")):
        with open(path, encoding="utf-8") as f:
            env = json.load(f)
        envs[env["runner"]] = env
    return envs


def check_consistency(envs):
    """§11 — digest·base_options 불일치는 조용히 넘기지 않고 경고한다."""
    runners = list(envs.keys())
    if len(runners) < 2:
        return

    ref = envs[runners[0]]
    for runner in runners[1:]:
        env = envs[runner]

        if env["base_options"] != ref["base_options"]:
            print(f"[경고] {runner}의 base_options가 {runners[0]}와 다릅니다")
            print(f"       {runners[0]}: {ref['base_options']}")
            print(f"       {runner}: {env['base_options']}")

        for model, ref_info in ref["models"].items():
            other_info = env["models"].get(model)
            if other_info and other_info["digest"] != ref_info["digest"]:
                print(
                    f"[경고] {model}의 digest가 기기마다 다릅니다: "
                    f"{runners[0]}={ref_info['digest']} vs {runner}={other_info['digest']}"
                )

        if env.get("drift", 1.0) < 0.85:
            print(f"[경고] {runner}의 drift={env['drift']} — 이 기기의 시간 지표는 신뢰하지 마세요")


def merge_csv():
    rows = []
    fieldnames = None
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*", "results_*.csv"))):
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            rows.extend(reader)

    if not rows:
        print("합칠 결과 CSV가 없습니다 (results/raw/<runner>/ 확인)")
        return

    os.makedirs(MERGED_DIR, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(MERGED_DIR, f"combined_v8_{date_tag}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"합침 완료: {len(rows)}행 → {out_path}")
    print("주의: 시간(wall_sec 등) 비교는 runner별로만 하세요. 절대 시간 비교 금지 (§11).")


def main():
    envs = load_envs()
    print(f"발견된 runner: {list(envs.keys())}")
    check_consistency(envs)
    merge_csv()


if __name__ == "__main__":
    main()
