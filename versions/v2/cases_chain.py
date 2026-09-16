"""
cases_chain.py — CHAIN군: J로 생성한 실제 결과를 K로 이어서 수정
=================================================================
지금까지 J/K는 서로 완전히 독립적으로 테스트됐다 — K는 사람이
미리 써둔 고정 baseline(SHORT_BASELINE)에서 시작했다. 이건 "K군
자체의 순수한 성능"을 재는 데는 맞는 설계지만, "실제 서비스처럼
J가 만든 걸 K가 이어받아도 잘 되는가"는 따로 확인한 적이 없다.

이 파일은 그 실제 파이프라인을 검증한다:
  1단계(생성) — cases_j의 프롬프트로 신규 Plan을 실제로 생성
  2단계(수정) — 1단계가 "진짜로 만들어낸" Plan을 current_plan으로
               삼아 K 패치를 실행 (baseline이 고정값이 아니라 매번
               다른, 방금 그 모델이 만든 결과라는 게 핵심 차이)

1단계가 실패하면 2단계는 아예 진행하지 않는다 — 패치할 대상 자체가
없기 때문이다. 이 경우도 "chain_blocked_by_generation_failure"로
정직하게 기록한다(조용히 건너뛰지 않는다).

Case.mode == "custom"이라 engine.py 수정 없이 동작한다.
"""

import engine
from engine import Case, call, run_one
from checks import check_plan, SOFT_FAILS
from registry import REQUIRED
import cases_j
import cases_k

CHAIN_REQUEST = "CTA 버튼 문구를 '지금 신청하기'로 바꿔줘."
MAX_RETRY = 3


def custom_run_generate_then_patch(model, case, runner, digest, backend,
                                    repeat_no, seed, rows, out_dir):
    """
    반환값은 engine.run_one()과 동일한 계약: (first_hard_ok, final_ok).
    다만 여기서는 "체인 전체"(생성+수정 둘 다)가 성공해야 성공(1)으로
    본다 — 생성이 실패했는데 수정만 어쩌다 됐다고 성공 처리하면
    안 되기 때문이다.
    """
    # ── 1단계: J 방식으로 신규 생성 (run_one을 그대로 안 쓰는 이유:
    #    성공 여부만 돌려주지 파싱된 plan 자체를 안 돌려주기 때문에,
    #    2단계에 넘겨줄 실제 데이터가 필요해서 직접 호출한다) ──────
    gen_system = cases_j.build_plan_system()
    gen_prompt = cases_j.P1
    messages = [
        {"role": "system", "content": gen_system},
        {"role": "user", "content": gen_prompt},
    ]

    generated_plan = None
    gen_hard_ok = 0

    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = call(model, messages, mode="plan", as_json=True, seed=seed,
                       json_schema=cases_j.PLAN_SCHEMA)
        except Exception as e:
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group=case.group, prompt_id=f"{case.pid}_GEN", kind="생성단계",
                pair=case.pid, repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error",
            ))
            break

        raw = res["message"]["content"]
        fails, note, plan, rendered = check_plan(raw, list(REQUIRED), ["notices"])
        hard = [f for f in fails if f not in SOFT_FAILS]
        hard_ok = int(not hard)

        pc, ec = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
        pd, ed = res.get("prompt_eval_duration", 1), res.get("eval_duration", 1)

        rows.append(engine._empty_row(
            runner=runner, model=model, digest=digest, backend=backend,
            group=case.group, prompt_id=f"{case.pid}_GEN", kind="생성단계",
            pair=case.pid, repeat_no=repeat_no, seed=seed, attempt=attempt,
            hard_ok=hard_ok, all_ok=int(not fails), fails="|".join(hard),
            wall_sec=res["_wall_sec"], prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
            eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
            prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
            out_len=len(raw.strip()), html_len=len(rendered) if rendered else 0,
            done_reason=res.get("done_reason", ""),
        ))

        safe = model.replace(":", "_")
        base = f"{out_dir}/{safe}_{case.pid}_GEN_r{repeat_no}_s{seed}_try{attempt}"
        with open(f"{base}.txt", "w", encoding="utf-8") as f:
            f.write(raw)
        if rendered:
            with open(f"{base}.rendered.html", "w", encoding="utf-8") as f:
                f.write(rendered)

        if hard_ok:
            generated_plan = plan   # ← 이게 2단계로 넘어갈 "진짜" baseline
            gen_hard_ok = 1
            break

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                         "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

    if generated_plan is None:
        # 생성 자체가 끝내 실패 — 패치 단계로 넘어갈 대상이 없다.
        # "조용히 건너뛰기"가 아니라 명시적으로 실패를 기록한다.
        rows.append(engine._empty_row(
            runner=runner, model=model, digest=digest, backend=backend,
            group=case.group, prompt_id=f"{case.pid}_PATCH",
            kind="수정단계_생성실패로_스킵", pair=case.pid,
            repeat_no=repeat_no, seed=seed, attempt=1,
            hard_ok=0, all_ok=0, fails="chain_blocked_by_generation_failure",
        ))
        return 0, 0

    # ── 2단계: 방금 "실제로" 생성된 Plan을 대상으로 K 패치 ──────
    patch_system = cases_k._patch_system(generated_plan)
    patch_case = Case(
        pid=f"{case.pid}_PATCH", kind="생성결과를_실제로_패치",
        group=case.group, system=patch_system, prompt=CHAIN_REQUEST,
        mode="patch", keep=list(REQUIRED), forbid=["notices"],
        current_plan=generated_plan, json_schema=cases_k.PATCH_SCHEMA,
    )
    patch_first, patch_final = run_one(model, patch_case, runner, digest, backend,
                                        repeat_no, seed, rows, out_dir)

    chain_first = 1 if (gen_hard_ok and patch_first) else 0
    chain_final = 1 if (gen_hard_ok and patch_final) else 0
    return chain_first, chain_final


CASES = [
    Case("CHAIN1", "생성후_실제로_패치", "CHAIN", "", "", "custom",
         custom_run=custom_run_generate_then_patch),
]


def self_check():
    # 이 체인이 의존하는 함수들이 실제로 존재하고 정상 작동하는지
    # (LLM 호출 없이) 확인한다.
    assert callable(cases_j.build_plan_system)
    assert isinstance(cases_j.P1, str) and cases_j.P1

    demo_plan = {"blocks": [
        {"type": "hero", "variant": "hyperui_centered", "title": "제목", "sub": "소개"},
        {"type": "benefits", "variant": "hyperui_list", "items": ["a", "b"]},
        {"type": "cta", "variant": "hyperui_simple", "label": "가입하기"},
    ], "theme": {}}
    patch_system = cases_k._patch_system(demo_plan)
    assert "가입하기" in patch_system, "_patch_system이 실제 계획 내용을 프롬프트에 못 넣음"

    assert len(CASES) == 1
    assert CASES[0].mode == "custom"
    assert CASES[0].custom_run is not None
