"""
cases_k_content.py — K3/K9 재측정: add_block "내용 없이" 성공 처리되는 gap 검증
=================================================================================
[이슈] K3/K9: add_block이 "내용 없이" 성공 처리되는 gap

`registry.build_patch_json_schema()`의 `add_block` 분기는 `op`/`type`/`variant`만
허용한다(`additionalProperties:false`) — 새로 추가하는 블록에 `title`/`items` 같은
콘텐츠 필드를 실을 방법이 스키마상 없다. v1·v2의 K3("참여 방법 영역을 3단계로
추가해줘")가 지금까지 9/10·10/10 같은 수치로 "성공" 집계된 건, `keep` 목록에
`steps`가 없어서(`REQUIRED`가 아니라서) 블록이 내용 없이 비어 렌더링돼도
`lost_steps`로 안 걸렸기 때문이다 — 안에 실제 항목이 채워졌는지는 한 번도
검증되지 않았다.

이 파일은 v2 `cases_k.py`의 K3/K9과 **baseline·요청 문구가 글자 그대로 동일**하다.
바뀐 건 스키마 하나뿐이다 — `cases_js_patch.py`가 JS-PATCH(카운트다운 등)를 위해
이미 만들어둔 "add_block에 콘텐츠 필드까지 포함하는 확장 스키마"를 그대로 가져다
쓰고, `keep`에 `steps`를 추가해서 `check_html`이 이제 `steps`의
`must="ol li"`·`min_items=2`까지 실제로 검증하게 했다. `registry.build_patch_json_schema()`
자체(v1·v2가 그대로 쓰는 공용 함수)는 건드리지 않으므로 v1·v2 결과는 안 바뀐다.

**읽는 법**: 이 케이스(K3FIX/K9FIX)의 통과율을 v2 README의 K3/K9 수치와 비교하면
"스키마 수정 하나"의 순수한 효과만 분리해서 볼 수 있다 — 떨어지는 폭이 크면
클수록, 기존 K3/K9 수치가 그만큼 과대평가돼 있었다는 뜻이다. K9은 `remove_block`
이라 애초에 콘텐츠 필드가 필요 없어서(지울 대상 이름만 있으면 됨) 이 gap의
영향을 받지 않는다 — 그대로 실어둔 건 "스키마를 바꿔도 remove_block 쪽엔
부작용이 없다"는 대조군 역할이다.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

from engine import Case
from registry import THEME_DEFAULTS, REQUIRED, render_plan
import cases_js_patch

# v2 cases_k.py의 SHORT_BASELINE/LONG_BASELINE과 글자 그대로 동일 — baseline이
# 달라지면 "스키마만 바꿨을 때의 순수한 효과"를 더 이상 분리해서 볼 수 없다.
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

# cases_js_patch.py가 JS-PATCH(카운트다운/FAQ/탭)를 위해 이미 만든 확장 스키마를
# 그대로 재사용한다 — set_field/append_item/remove_block은 registry의 것과
# 동일하고 add_block만 콘텐츠 필드까지 포함한다. 새로 만들지 않는다.
PATCH_SCHEMA = cases_js_patch.PATCH_SCHEMA


def _patch_system(current_plan: dict) -> str:
    return cases_js_patch._patch_system(current_plan)


CASES = [
    Case("K3FIX", "영역추가_패치_콘텐츠검증", "K-CONTENT", _patch_system(SHORT_BASELINE),
         "참여 방법(steps) 영역을 3단계로 추가해줘.",
         "patch", keep=list(REQUIRED) + ["steps"], forbid=["notices"],
         current_plan=SHORT_BASELINE, pair="K3", json_schema=PATCH_SCHEMA),

    Case("K9FIX", "영역삭제_패치_콘텐츠검증_대조군", "K-CONTENT", _patch_system(LONG_BASELINE),
         "참여 방법(steps) 영역을 통째로 빼줘.",
         "patch", keep=["hero", "benefits", "cta"], forbid=["notices", "steps"],
         current_plan=LONG_BASELINE, pair="K9", json_schema=PATCH_SCHEMA),
]


def self_check():
    for name, plan in [("SHORT_BASELINE", SHORT_BASELINE), ("LONG_BASELINE", LONG_BASELINE)]:
        r = render_plan(plan)
        assert r, f"{name}이 빈 렌더링 결과를 냄"
    assert len(render_plan(LONG_BASELINE)) > len(render_plan(SHORT_BASELINE))

    # 이 파일의 핵심 목적 — 확장 스키마가 진짜로 콘텐츠 필드를 요구하는지 자체 검증.
    # registry.build_patch_json_schema()(원본, v1·v2가 씀)는 못 잡던 것을
    # 여기 스키마는 required로 강제해야 한다.
    steps_add_variants = [
        v for v in PATCH_SCHEMA["properties"]["ops"]["items"]["oneOf"]
        if v["properties"].get("op", {}).get("const") == "add_block"
        and v["properties"].get("type", {}).get("const") == "steps"
    ]
    assert steps_add_variants, "add_block(steps) 변형이 스키마에 없음"
    assert "items" in steps_add_variants[0]["required"], (
        "steps add_block 스키마가 items를 required로 요구하지 않음 — "
        "이러면 v2 K3와 똑같이 내용 없이도 통과해버림")

    assert len(CASES) == 2
    for c in CASES:
        assert c.group == "K-CONTENT"
        assert c.mode == "patch"
        assert c.json_schema is not None
    assert "steps" in CASES[0].keep, "K3FIX는 steps가 실제로 채워졌는지 keep으로 검증해야 함"
    assert "steps" not in CASES[1].keep and "steps" in CASES[1].forbid
