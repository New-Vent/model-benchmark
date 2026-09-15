#!/usr/bin/env python3
"""Phase 2 — 파라미터 미니 스윕 (repeat_penalty, temperature)

Phase 1(benchmark_v8.py)에서 모델·출력방식이 확정된 뒤에만 실행합니다.
전체를 다시 스윕하지 않고, 위험 신호가 있던 파라미터 2개만 좁게 검증합니다.
근거: docs/v8-plan.md §7

실행: python scripts/param_sweep.py
"""
import csv
import json
import os
import re
import time
from datetime import datetime

import requests

OLLAMA = "http://localhost:11434"

# ── Phase 1에서 확정된 값으로 바꿔서 실행 ─────────────────────
CHOSEN_MODEL = os.environ.get("CHOSEN_MODEL", "exaone3.5:7.8b")

FIXED_OPTIONS = {"top_p": 0.9, "top_k": 40, "num_ctx": 8192}
KEEP_ALIVE = "30m"
SEEDS = [42, 43, 44]  # 미니 실험이라 3회로 축소

REPEAT_PENALTY_VALUES = [1.0, 1.1, 1.3]
TEMPERATURE_VALUES = [0.1, 0.2, 0.4]

# 혜택 3개 이상을 요구하는 고정 프롬프트 (repeat_penalty 검증용)
BENEFITS_PROMPT = (
    "이벤트명: 가을 멤버십 혜택\n"
    "요청: 혜택을 <ul> 안에 <li>로 4개 나열해줘. 각 항목은 한 문장으로."
)

# 환각 유발 조건 (temperature 검증용, docs/v8-plan.md D군과 동일 패턴)
HALLUCINATION_PROMPT = "가을 멤버십 이벤트 페이지 만들어줘."  # 기간/혜택 정보 없음
DATE_RE = re.compile(r"\d{4}\s*년|\d{1,2}\s*월\s*\d{1,2}\s*일")
NUM_UNIT_RE = re.compile(r"\d+\s*(GB|MB|원|명|%|개월|회|배)")
LI_RE = re.compile(r"<li>")


def call(options, prompt, seed):
    opts = dict(FIXED_OPTIONS, **options, seed=seed, num_predict=1536)
    t0 = time.time()
    res = requests.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": CHOSEN_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": opts,
        },
        timeout=180,
    ).json()
    res["wall_sec"] = round(time.time() - t0, 2)
    return res


def sweep_repeat_penalty(rows):
    for rp in REPEAT_PENALTY_VALUES:
        for seed in SEEDS:
            res = call({"temperature": 0.2, "repeat_penalty": rp}, BENEFITS_PROMPT, seed)
            html = res.get("message", {}).get("content", "")
            li_count = len(LI_RE.findall(html))
            rows.append(
                {
                    "sweep": "repeat_penalty",
                    "value": rp,
                    "seed": seed,
                    "li_count": li_count,
                    "few_benefits": li_count < 3,
                    "wall_sec": res["wall_sec"],
                }
            )


def sweep_temperature(rows, blind_dir, blind_key):
    idx = len(blind_key)
    for temp in TEMPERATURE_VALUES:
        for seed in SEEDS:
            res = call({"temperature": temp, "repeat_penalty": 1.1}, HALLUCINATION_PROMPT, seed)
            html = res.get("message", {}).get("content", "")
            hallucinated = bool(DATE_RE.search(html)) or bool(NUM_UNIT_RE.search(html))

            idx += 1
            blind_name = f"{idx:03d}.txt"
            with open(os.path.join(blind_dir, blind_name), "w", encoding="utf-8") as f:
                f.write(html)
            blind_key[blind_name] = {"sweep": "temperature", "value": temp, "seed": seed}

            rows.append(
                {
                    "sweep": "temperature",
                    "value": temp,
                    "seed": seed,
                    "hallucinated": hallucinated,
                    "blind_file": blind_name,
                    "wall_sec": res["wall_sec"],
                }
            )


def main():
    date_tag = datetime.now().strftime("%Y%m%d")
    out_dir = os.path.join("results", "param-sweep", date_tag)
    blind_dir = os.path.join(out_dir, "blind")
    os.makedirs(blind_dir, exist_ok=True)

    print(f"대상 모델: {CHOSEN_MODEL} (Phase 1에서 확정된 값이어야 합니다)")

    rp_rows = []
    sweep_repeat_penalty(rp_rows)
    with open(os.path.join(out_dir, "repeat_penalty_sweep.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rp_rows[0].keys()))
        writer.writeheader()
        writer.writerows(rp_rows)

    temp_rows = []
    blind_key = {}
    sweep_temperature(temp_rows, blind_dir, blind_key)
    with open(os.path.join(out_dir, "temperature_sweep.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(temp_rows[0].keys()))
        writer.writeheader()
        writer.writerows(temp_rows)

    # blind_key는 문장 품질 채점(사람)이 끝날 때까지 열어보지 않습니다 (docs/v8-plan.md §10 원칙과 동일)
    with open(os.path.join(out_dir, "blind_key.json"), "w", encoding="utf-8") as f:
        json.dump(blind_key, f, ensure_ascii=False, indent=2)

    print(f"완료 → {out_dir}")
    print(f"  - repeat_penalty_sweep.csv: few_benefits가 어느 값부터 늘어나는지 확인")
    print(f"  - temperature_sweep.csv + blind/: 환각률 확인, blind/ 파일은 문장 품질 블라인드 채점용")


if __name__ == "__main__":
    main()
