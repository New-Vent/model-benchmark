"""
cases_jt.py — J-T군: 실제 크기 신규 생성, JSON 노선
=====================================================
cases_st.py(S-T)와 **글자 그대로 같은 요청 문구**를 쓴다. 그래야 pair
비교가 성립한다. 어긋나면 "다른 요청"을 비교하게 되므로, 프롬프트를
고칠 때는 반드시 두 파일을 함께 고칠 것 (v1 cases_ns ↔ v2 cases_j에서
이미 겪은 문제 — v4 cases_se/cases_kt의 규약을 그대로 이어받았다).

    ST1 ↔ JT1   스포츠 응원
    ST2 ↔ JT2   명절 선물
    ST3 ↔ JT3   멤버십 감사
    ST4 ↔ JT4   플래시 세일
    ST5 ↔ JT5   사전예약

모델은 plan JSON만 내고, 마크업은 `registry.render_plan()`이 조립한다 —
그래서 class는 서버가 보장하고(J의 원래 강점), 모델의 실패는 "내용을
올바르게 채우는가"에만 집중된다. checks_v4.check_tag_in_fields로
텍스트 필드 안에 태그가 섞이는지도 함께 본다(v3 감사에서 지적된 구멍).

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

from engine import Case
from registry import REQUIRED, build_plan_json_schema

import checks_v4

GROUPS = ["J-T"]

PLAN_SCHEMA = build_plan_json_schema()

# plan 자체는 짧지만(항목 텍스트뿐), 전체 페이지 분량(혜택 3·단계 3)을
# 요구하므로 v2의 plan 캡(512)보다는 넉넉하게 잡는다. html 캡처럼 캡을
# 넘길 위험은 낮지만(구조는 서버가 만듦), S-T와 캡 조건을 맞춰 비교
# 왜곡을 없앤다.
NUM_PREDICT_T = 3072

SYSTEM = """너는 통신사 이벤트 페이지의 구성 계획(JSON)을 만드는 도우미다.

요청에 맞는 이벤트 페이지를 blocks 배열로 표현한다. 마크업은 서버가
만들므로 너는 내용(문구·항목)만 낸다.

포함할 블록:
- hero: 제목(title)과 소개(sub)
- benefits: 혜택 3개(items)
- steps: 참여 방법 3단계(items)
- cta: 버튼 문구(label)

규칙:
- notices 블록은 서버 전용이므로 절대 포함하지 마라.
- 값만 쓴다. HTML 태그를 넣지 마라 — 마크업은 서버가 만든다.
- 날짜를 임의로 만들지 마라.
- 대괄호 자리표시자를 남기지 마라.
- 주어지지 않은 혜택을 지어내지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


def _make_check():
    def _check(raw, _):
        # base_checks.check_plan은 engine.run_one()이 이미 돌려서
        # fails/hard_ok에 반영했다 — 여기서는 그게 못 잡는 것만 추가한다
        # (checks_v4.check_plan_v4와 같은 목적이지만, 기본 검사를 다시
        # 실행해서 fails를 중복 집계하지 않도록 직접 조합한다).
        from checks import check_plan
        fails, _note, plan, rendered = check_plan(raw, keep=list(REQUIRED),
                                                    forbid=["notices"])
        if plan is None:
            return []  # no_json/bad_json은 base가 이미 잡음 — 더 볼 게 없다

        new_fails = []
        t_fails, _ = checks_v4.check_tag_in_fields(plan)
        new_fails += t_fails

        if rendered:
            r_fails, _ = checks_v4.check_rendered(
                rendered, keep=list(REQUIRED), forbid=["notices"])
            for f in r_fails:
                if f not in fails and f not in new_fails:
                    new_fails.append(f)
        return new_fails
    return _check


def _case(pid, kind, prompt):
    return Case(
        pid, kind, "J-T", SYSTEM, prompt, mode="plan",
        keep=list(REQUIRED), forbid=["notices"],
        json_schema=PLAN_SCHEMA,
        extra_check=_make_check(),
        num_predict=NUM_PREDICT_T,
    )


# 요청 문구는 cases_st.py와 글자 그대로 같아야 한다.
CASES = [
    _case("JT1", "신규생성_스포츠응원",
          "2026년 프로야구 시즌 응원 이벤트 페이지를 만들어줘. "
          "혜택 3개(굿즈, 할인, 포인트 적립), 참여 방법 3단계를 포함해줘."),
    _case("JT2", "신규생성_명절선물",
          "설 명절 선물 대축제 이벤트 페이지를 만들어줘. "
          "혜택 3개(상품권, 할인 쿠폰, 사은품), 참여 방법 3단계를 포함해줘."),
    _case("JT3", "신규생성_멤버십감사",
          "장기 고객 대상 멤버십 감사 이벤트 페이지를 만들어줘. "
          "혜택 3개(쿠폰, 등급 혜택, 특별 사은품), 참여 방법 3단계를 포함해줘."),
    _case("JT4", "신규생성_플래시세일",
          "24시간 한정 플래시 세일 이벤트 페이지를 만들어줘. "
          "혜택 3개(즉시 할인, 무료배송, 포인트 2배), 참여 방법 3단계를 포함해줘."),
    _case("JT5", "신규생성_사전예약",
          "신제품 사전예약 이벤트 페이지를 만들어줘. "
          "혜택 3개(얼리버드 할인, 한정 굿즈, 우선 출고), 참여 방법 3단계를 포함해줘."),
]


def self_check():
    import cases_st

    assert len(CASES) == 5, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "J-T"
        assert c.mode == "plan"
        assert c.json_schema is not None
        assert c.num_predict == NUM_PREDICT_T, f"{c.pid} num_predict 오버라이드 누락"
        assert "notices" not in c.keep

    # ★ pair 무결성 — S-T와 요청 문구가 글자 그대로 같아야 한다
    st = {c.pid: c for c in cases_st.CASES}
    for j, s in zip(CASES, ["ST1", "ST2", "ST3", "ST4", "ST5"]):
        assert j.prompt == st[s].prompt, (
            f"{j.pid} 와 {s} 의 요청 문구가 다릅니다. pair 비교가 무너집니다.\n"
            f"  {s}: {st[s].prompt!r}\n  {j.pid}: {j.prompt!r}")

    # 회귀 — 계약을 지킨 최소 plan은 전부 통과해야 한다.
    good_plan = {
        "blocks": [
            {"type": "hero", "variant": "flowbite_split", "title": "제목", "sub": "소개"},
            {"type": "benefits", "variant": "flowbite_cards",
             "items": ["혜택1", "혜택2", "혜택3"]},
            {"type": "steps", "variant": "hyperui_numbered",
             "items": ["1단계", "2단계", "3단계"]},
            {"type": "cta", "variant": "flowbite_banner", "label": "참여하기"},
        ],
    }
    import json
    raw = json.dumps(good_plan, ensure_ascii=False)
    extra_fails = CASES[0].extra_check(raw, raw)
    assert not extra_fails, f"최소 계약 plan이 추가 검사에 걸림: {extra_fails}"

    # 텍스트 필드에 태그가 섞이면 잡혀야 한다 (tag_in_field 회귀)
    bad_plan = json.loads(raw)
    bad_plan["blocks"][0]["title"] = "<strong>제목</strong>"
    bad_raw = json.dumps(bad_plan, ensure_ascii=False)
    bad_fails = CASES[0].extra_check(bad_raw, bad_raw)
    assert any(f.startswith("tag_in_field_") for f in bad_fails), "태그 주입을 못 잡음"

    print("  [cases_jt] self_check 통과")
