"""
cases_js_patch.py — JS-PATCH군: 인터랙션을 K(패치) 방식으로 "추가"
=====================================================================
v3 README §2의 3-way 비교 중 "이미 있는 페이지에 인터랙션 블록을
나중에 add_block으로 추가하는" 실전 시나리오를 잰다. JS-PLAN과 콘텐츠
값(카운트다운 날짜, FAQ/tabs 항목)은 동일하고 전달 메커니즘만 다르다.

⚠ registry.build_patch_json_schema()의 add_block 분기는 op/type/variant
필드만 허용한다(additionalProperties:false) — 새로 추가되는 블록에
title/items/target_date 같은 콘텐츠 필드를 실을 수 없다는 뜻이다.
v1·v2의 K3/K9(steps 블록 add_block)가 이 스키마로도 "성공"한 것처럼
보였던 건, keep 목록에 steps가 없어서(REQUIRED에 steps가 없음) 블록이
내용 없이 비어 렌더링돼도 lost_*로 안 잡혔기 때문이다(실제로는 있는
그대로 확인되지 않은 기존 한계). JS-PATCH는 "그 블록이 실제로
동작하는 콘텐츠와 함께 렌더링되는가"가 핵심 질문이므로, 이 파일만
add_block에 콘텐츠 필드를 실을 수 있는 확장 스키마를 따로 쓴다 —
registry.build_patch_json_schema()(v1·v2가 그대로 쓰는 공용 함수)는
건드리지 않는다.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

import json
import re

from engine import Case
from registry import LLM_BLOCKS, REQUIRED, THEME_DEFAULTS, render_plan

FENCE = re.compile(r"```")
COUNTDOWN_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

BASELINE = {
    "blocks": [
        {"type": "hero", "variant": "hyperui_centered", "title": "여름 데이터 대방출",
         "sub": "이번 여름 데이터 걱정 없이 마음껏 즐기세요"},
        {"type": "benefits", "variant": "hyperui_list",
         "items": ["데이터 3GB 즉시 지급", "월 요금 30% 할인"]},
        {"type": "cta", "variant": "hyperui_simple", "label": "가입하기"},
    ],
    "theme": dict(THEME_DEFAULTS),
}

_BLOCK_KEYS = [b.key for b in LLM_BLOCKS]


def build_add_block_content_schema() -> dict:
    """add_block 오퍼레이션에 한해 콘텐츠 필드까지 포함하는 확장 스키마.
    registry.build_plan_json_schema()가 블록별 oneOf를 만드는 방식을
    그대로 op="add_block" 아래에 적용한 것 — set_field/append_item/
    remove_block은 registry의 것과 동일하게 유지하고 add_block만 바꾼다.
    set_theme/apply_preset은 이 군의 케이스가 쓰지 않아 생략한다."""
    add_block_variants = []
    for b in LLM_BLOCKS:
        for v in b.variants:
            props = {
                "op": {"const": "add_block"},
                "type": {"const": b.key},
                "variant": {"const": v.name},
            }
            required = ["op", "type", "variant"]
            for f in v.fields:
                if f == "items":
                    props["items"] = {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": max(b.min_items, 1),
                    }
                    required.append("items")
                elif f == "sub":
                    props["sub"] = {"type": "string"}
                else:
                    props[f] = {"type": "string", "minLength": 1}
                    required.append(f)
            add_block_variants.append({
                "type": "object", "properties": props,
                "required": required, "additionalProperties": False,
            })

    other_ops = [
        {"type": "object", "properties": {
            "op": {"const": "set_field"},
            "block_key": {"type": "string", "enum": _BLOCK_KEYS},
            "field": {"type": "string"},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "append_item"},
            "block_key": {"type": "string", "enum": _BLOCK_KEYS},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_block"},
            "block_key": {"type": "string", "enum": _BLOCK_KEYS},
        }, "required": ["op", "block_key"], "additionalProperties": False},
    ]

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["patch", "clarify", "unsupported"]},
            "ops": {"type": "array", "items": {"oneOf": other_ops + add_block_variants}},
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


PATCH_SCHEMA = build_add_block_content_schema()


def _patch_system(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성을 수정하는 도우미다.

[현재 계획]
{plan_json}

전체 계획을 다시 쓰지 마라. 요청과 관련된 부분만 오퍼레이션으로 표현하라.

사용 가능한 오퍼레이션:
- set_field: {{"op":"set_field","block_key":"cta","field":"label","value":"..."}}
- append_item: {{"op":"append_item","block_key":"benefits","value":"..."}}
- remove_block: {{"op":"remove_block","block_key":"steps"}}
- add_block(카운트다운): {{"op":"add_block","type":"countdown","variant":"digital",
  "title":"...","target_date":"YYYY-MM-DD"}}
- add_block(자주 묻는 질문): {{"op":"add_block","type":"faq","variant":"native_details",
  "items":["질문|답변", "질문|답변"]}}
- add_block(탭 전환): {{"op":"add_block","type":"tabs","variant":"js_switcher",
  "items":["탭이름|내용", "탭이름|내용"]}}

출력 형식: {{"ops":[ ...오퍼레이션들... ]}}

규칙:
- 언급되지 않은 블록/필드는 오퍼레이션에 아예 포함하지 마라.
- 최소한의 오퍼레이션으로 요청을 처리하라.
- notices 블록은 서버 전용이므로 절대 건드리지 마라.
- countdown의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- faq/tabs의 items는 각 항목을 "앞부분|뒷부분" 형식(파이프 1개)으로 쓴다.
- JSON 외에는 아무것도 출력하지 마라."""


def _parse_patch_json(raw):
    """extra_check는 patch 모드에서도 (raw, raw)를 받는다(engine.run_one
    참고) — 렌더링된 HTML이 아니라 LLM이 낸 JSON 원문이다."""
    text = FENCE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def _find_add_block_op(raw, block_type):
    patch = _parse_patch_json(raw)
    if not patch:
        return None
    for op in patch.get("ops", []) or []:
        if isinstance(op, dict) and op.get("op") == "add_block" and op.get("type") == block_type:
            return op
    return None


def check_countdown_patch_format(raw, _):
    op = _find_add_block_op(raw, "countdown")
    if op is None:
        return []  # keep=[...,"countdown"]이 렌더링 누락은 이미 lost_countdown으로 잡음
    if not COUNTDOWN_DATE.match(str(op.get("target_date", ""))):
        return ["countdown_bad_date_format"]
    return []


def _check_pipe_items(raw, block_type, fail_code):
    op = _find_add_block_op(raw, block_type)
    if op is None:
        return []
    items = op.get("items")
    if not isinstance(items, list) or not items:
        return []
    if any(not isinstance(x, str) or "|" not in x for x in items):
        return [fail_code]
    return []


def check_faq_patch_format(raw, _):
    return _check_pipe_items(raw, "faq", "faq_item_missing_pipe")


def check_tabs_patch_format(raw, _):
    return _check_pipe_items(raw, "tabs", "tabs_item_missing_pipe")


CASES = [
    Case("KPATCH1", "카운트다운_패치추가", "JS-PATCH", _patch_system(BASELINE),
         "이벤트 마감까지 남은 시간을 보여주는 카운트다운을 추가해줘. 마감일은 2026-08-31이야.",
         "patch", keep=list(REQUIRED) + ["countdown"], forbid=["notices"],
         current_plan=BASELINE, extra_check=check_countdown_patch_format,
         json_schema=PATCH_SCHEMA, num_predict=3072),

    Case("KPATCH2", "아코디언_패치추가", "JS-PATCH", _patch_system(BASELINE),
         "자주 묻는 질문 2개를 추가해줘.",
         "patch", keep=list(REQUIRED) + ["faq"], forbid=["notices"],
         current_plan=BASELINE, extra_check=check_faq_patch_format,
         json_schema=PATCH_SCHEMA, num_predict=3072),

    Case("KPATCH3", "탭전환_패치추가", "JS-PATCH", _patch_system(BASELINE),
         "탭으로 전환되는 안내 콘텐츠를 2개 추가해줘.",
         "patch", keep=list(REQUIRED) + ["tabs"], forbid=["notices"],
         current_plan=BASELINE, extra_check=check_tabs_patch_format,
         json_schema=PATCH_SCHEMA, num_predict=3072),
]


def self_check():
    r = render_plan(BASELINE)
    assert r, "BASELINE이 빈 렌더링 결과를 냄"

    good = json.dumps({"ops": [
        {"op": "add_block", "type": "countdown", "variant": "digital",
         "title": "마감임박", "target_date": "2026-08-31"},
    ]}, ensure_ascii=False)
    assert check_countdown_patch_format(good, "") == []
    bad = json.dumps({"ops": [
        {"op": "add_block", "type": "countdown", "variant": "digital",
         "title": "마감임박", "target_date": "8월 31일"},
    ]}, ensure_ascii=False)
    assert "countdown_bad_date_format" in check_countdown_patch_format(bad, "")

    good_faq = json.dumps({"ops": [
        {"op": "add_block", "type": "faq", "variant": "native_details",
         "items": ["환불 되나요?|가능합니다."]},
    ]}, ensure_ascii=False)
    assert check_faq_patch_format(good_faq, "") == []
    bad_faq = json.dumps({"ops": [
        {"op": "add_block", "type": "faq", "variant": "native_details",
         "items": ["환불 되나요?"]},
    ]}, ensure_ascii=False)
    assert "faq_item_missing_pipe" in check_faq_patch_format(bad_faq, "")

    assert PATCH_SCHEMA["type"] == "object"
    variants = PATCH_SCHEMA["properties"]["ops"]["items"]["oneOf"]
    countdown_variants = [v for v in variants
                          if v["properties"].get("type", {}).get("const") == "countdown"]
    assert countdown_variants, "add_block 스키마에 countdown 변형이 없음"
    assert "target_date" in countdown_variants[0]["properties"], (
        "add_block(countdown) 스키마에 target_date 필드가 없음 — "
        "registry.build_patch_json_schema()의 기존 한계가 그대로 재현됨")

    assert len(CASES) == 3
    for c in CASES:
        assert c.group == "JS-PATCH"
        assert c.mode == "patch"
        assert c.current_plan is BASELINE
        assert c.json_schema is not None
        assert c.num_predict == 3072
    assert "countdown" in CASES[0].keep
    assert "faq" in CASES[1].keep
    assert "tabs" in CASES[2].keep
