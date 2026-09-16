"""
cases_k.py — K군: 패치 (고정 입력)
====================================
담당자만 이 파일을 건드리세요.

이 파일이 반드시 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

from engine import Case
from registry import THEME_DEFAULTS, render_plan, REQUIRED, build_patch_json_schema

# K1~K6의 기준 문서(약 370자), K7~K10의 기준 문서(약 590자) — 두 크기를
# 재서 "문서 크기가 패치 출력에 영향을 주는지"를 확인한다(E군과 같은 질문,
# K군 자체 내에서도 재현).
SHORT_BASELINE = {
    "blocks": [
        {"type": "hero", "variant": "hyperui_centered", "title": "여름 데이터 대방출",
         "sub": "이번 여름 데이터 걱정 없이 마음껏 즐기세요"},
        {"type": "benefits", "variant": "hyperui_list",
         "items": ["데이터 3GB 즉시 지급", "월 요금 30% 할인"]},
        {"type": "cta", "variant": "hyperui_simple", "label": "가입하기"},
    ],
    "theme": dict(THEME_DEFAULTS),
}

LONG_BASELINE = {
    "blocks": [
        {"type": "hero", "variant": "flowbite_split", "title": "여름 데이터 대방출 페스타",
         "sub": "이번 여름, 데이터 걱정 없이 마음껏 즐기세요"},
        {"type": "benefits", "variant": "flowbite_cards", "items": [
            "데이터 3GB 즉시 지급 — 가입 완료 즉시 자동 충전",
            "월 요금 30% 할인 — 개통 익월부터 6개월간 적용",
            "제휴 카페 음료 쿠폰 — 매월 1장씩 총 3장 제공",
        ]},
        {"type": "steps", "variant": "hyperui_numbered", "items": [
            "이벤트 페이지에서 요금제 선택", "온라인으로 가입 신청서 작성", "개통 완료 후 혜택 자동 적용",
        ]},
        {"type": "cta", "variant": "flowbite_banner", "label": "지금 바로 가입하기"},
    ],
    "theme": dict(THEME_DEFAULTS),
}


PATCH_SCHEMA = build_patch_json_schema()


def _patch_system(current_plan: dict) -> str:
    import json
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성을 수정하는 도우미다.

[현재 계획]
{plan_json}

전체 계획을 다시 쓰지 마라. 요청과 관련된 부분만 오퍼레이션으로 표현하라.

사용 가능한 오퍼레이션:
- set_field: {{"op":"set_field","block_key":"cta","field":"label","value":"..."}}
- append_item: {{"op":"append_item","block_key":"benefits","value":"..."}}
- remove_block: {{"op":"remove_block","block_key":"steps"}}
- add_block: {{"op":"add_block","type":"steps","variant":"hyperui_numbered","items":["...","..."]}}
- set_theme: {{"op":"set_theme","field":"buttonColor","value":"#2f9e44"}}

출력 형식: {{"ops":[ ...오퍼레이션들... ]}}

규칙:
- 언급되지 않은 블록/필드는 오퍼레이션에 아예 포함하지 마라.
- 최소한의 오퍼레이션으로 요청을 처리하라.
- notices 블록은 서버 전용이므로 절대 건드리지 마라.
- 색상은 #으로 시작하는 6자리 16진수로 표현하라.
- JSON 외에는 아무것도 출력하지 마라."""


def check_no_shrink_on_delete(op_type):
    """remove_block인데 결과가 원본보다 작아지지 않으면 렌더러/측정
    문제라는 신호 — engine.run_one은 rendered 길이를 직접 안 넘겨주므로,
    여기서는 신호만 표시하고 실제 비교는 결과 CSV 집계 단계에서 한다."""
    return []  # TODO: 필요시 run_one을 확장해 rendered 길이를 넘겨받아 비교


CASES = [
    Case("K1", "문구수정_패치_단순", "K", _patch_system(SHORT_BASELINE),
         "CTA 버튼 문구만 '지금 신청하기'로 바꿔줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K2", "혜택추가_패치_단순", "K", _patch_system(SHORT_BASELINE),
         "혜택 목록에 '제휴 카페 음료 쿠폰 3장 제공'을 추가해줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K3", "영역추가_패치_단순", "K", _patch_system(SHORT_BASELINE),
         "참여 방법(steps) 영역을 3단계로 추가해줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K4", "제목수정_패치_단순", "K", _patch_system(SHORT_BASELINE),
         "hero 제목을 '여름엔 데이터가 두 배'로 바꿔줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K5", "버튼색상_테마패치", "K", _patch_system(SHORT_BASELINE),
         "CTA 버튼 색상을 초록색 계열로 바꿔줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K6", "제목굵기_테마패치", "K", _patch_system(SHORT_BASELINE),
         "제목 글씨를 더 굵게 해줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="J1", json_schema=PATCH_SCHEMA),

    Case("K7", "문구수정_패치_복잡", "K", _patch_system(LONG_BASELINE),
         "CTA 버튼 문구만 '지금 신청하기'로 바꿔줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=LONG_BASELINE, pair="K1", json_schema=PATCH_SCHEMA),

    Case("K8", "혜택추가_패치_복잡", "K", _patch_system(LONG_BASELINE),
         "혜택 목록에 '친구 추천 시 5,000원 쿠폰 지급'을 추가해줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=LONG_BASELINE, pair="K2", json_schema=PATCH_SCHEMA),

    Case("K9", "영역삭제_패치_복잡", "K", _patch_system(LONG_BASELINE),
         "참여 방법(steps) 영역을 통째로 빼줘.",
         "patch", keep=["hero", "benefits", "cta"], forbid=["notices", "steps"],
         current_plan=LONG_BASELINE, pair="K3", json_schema=PATCH_SCHEMA),

    Case("K10", "제목수정_패치_복잡", "K", _patch_system(LONG_BASELINE),
         "hero 제목을 '여름엔 데이터가 두 배'로 바꿔줘.",
         "patch", keep=list(REQUIRED), forbid=["notices"],
         current_plan=LONG_BASELINE, pair="K4", json_schema=PATCH_SCHEMA),
]


def self_check():
    for name, plan in [("SHORT_BASELINE", SHORT_BASELINE), ("LONG_BASELINE", LONG_BASELINE)]:
        r = render_plan(plan)
        assert r, f"{name}이 빈 렌더링 결과를 냄"
    assert len(render_plan(LONG_BASELINE)) > len(render_plan(SHORT_BASELINE))
    assert len(CASES) == 10
    for c in CASES:
        assert c.group == "K"
        assert c.mode == "patch"
        assert c.current_plan is not None
        assert c.json_schema is not None, f"{c.pid}에 json_schema가 없음"
    assert PATCH_SCHEMA["type"] == "object"
    assert "action" in PATCH_SCHEMA["properties"]
