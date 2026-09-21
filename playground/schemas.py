"""
schemas.py — playground 전용 스키마. base/registry.py는 안 건드리고
(v1~v9가 의존하는 동결 파일) 여기서 확장만 한다.

PLAN_SCHEMA: 신규 생성용 — registry.build_plan_json_schema() 그대로.
PATCH_SCHEMA: 수정용 — registry.build_patch_json_schema()의 add_block은
    type/variant만 허용해서 poll/coupon 등을 "추가"할 때 콘텐츠 필드를
    못 싣는다(v3에서 지적된 gap, versions/v9/cases_scenarios.py와 동일한
    이유로 확장 필요). LLM_BLOCKS를 순회하는 방식이라 새 블록이 늘어도
    이 파일은 다시 안 고쳐도 된다.
"""
import os
import sys

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "base")
sys.path.insert(0, BASE_DIR)

from registry import LLM_BLOCKS, THEME_FIELDS, STYLE_PRESETS, build_plan_json_schema  # noqa: E402

PLAN_SCHEMA = build_plan_json_schema()

_BLOCK_KEYS = [b.key for b in LLM_BLOCKS]


def build_patch_schema_with_content() -> dict:
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
        {"type": "object", "properties": {
            "op": {"const": "set_theme"},
            "field": {"type": "string", "enum": list(THEME_FIELDS.keys())},
            "value": {"type": "string"},
        }, "required": ["op", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "apply_preset"},
            "name": {"type": "string", "enum": list(STYLE_PRESETS.keys())},
        }, "required": ["op", "name"], "additionalProperties": False},
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


PATCH_SCHEMA = build_patch_schema_with_content()
