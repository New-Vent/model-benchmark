"""
registry.py — 블록/변형 레지스트리 (공통, 아무도 개별로 건드리지 않음)
====================================================================
새 컴포넌트를 추가하고 싶으면 component_library.py에 렌더 함수를
추가하고 여기 BLOCKS에 등록한다. 이 파일 자체의 구조(Block/Variant
클래스, shape↔must 짝 원칙)는 v7에서 그대로 가져왔다.
"""

import html as htmllib
import re
from dataclasses import dataclass

from component_library import (
    HERO_VARIANTS, BENEFITS_VARIANTS, STEPS_VARIANTS, CTA_VARIANTS,
    COUNTDOWN_VARIANTS, FAQ_VARIANTS, TABS_VARIANTS,
    COUNTDOWN_SCRIPT, TAB_SWITCHER_SCRIPT,
)

LLM, SERVER, MIXED = "llm", "server", "mixed"


def esc(v):
    return htmllib.escape(str(v), quote=True)


@dataclass(frozen=True)
class Variant:
    name: str
    desc: str
    fields: tuple
    render: object


@dataclass(frozen=True)
class Block:
    key: str
    required: bool
    source: str
    desc: str
    shape: str = ""
    must: str = ""
    min_items: int = 0
    count_selector: str = "li"
    variants: tuple = ()

    def variant(self, name):
        return next((v for v in self.variants if v.name == name), None)


BLOCKS = [
    Block("hero", True, LLM,
          "이벤트 제목과 한 줄 소개",
          shape="제목은 <h1>, 소개는 <p> 로 감싼다",
          must="h1",
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in HERO_VARIANTS)),

    Block("benefits", True, LLM,
          "혜택 2~4개. 각 항목은 한 문장",
          shape="<ul> 안에 <li> 로 항목을 나열한다. 2개 이상",
          must="ul li", min_items=2,
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in BENEFITS_VARIANTS)),

    Block("steps", False, LLM,
          "참여 방법 2~4단계",
          shape="<ol> 안에 <li> 로 순서대로 나열한다",
          must="ol li", min_items=2,
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in STEPS_VARIANTS)),

    Block("notices", True, SERVER,
          "유의사항 — 승인된 문구만 서버가 삽입"),

    Block("cta", True, MIXED,
          "참여 버튼. 문구만 생성, 링크는 폼 값",
          shape='<a href="#" class="btn"> 안에 버튼 문구를 넣는다',
          must="a",
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in CTA_VARIANTS)),

    Block("countdown", False, LLM,
          "마감까지 남은 시간을 보여주는 카운트다운",
          shape="목표 날짜(target_date)는 YYYY-MM-DD 형식, "
                "<h2>제목 + <span data-countdown-target=날짜> 구조로 감싼다",
          must="[data-countdown-target]",
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in COUNTDOWN_VARIANTS)),

    Block("faq", False, LLM,
          "자주 묻는 질문 2~4개 (질문|답변 형식)",
          shape="각 항목을 <details><summary>질문</summary><p>답변</p></details>로 감싼다",
          must="details summary", min_items=2, count_selector="details",
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in FAQ_VARIANTS)),

    Block("tabs", False, LLM,
          "탭으로 전환되는 콘텐츠 2~4개 (탭이름|내용 형식)",
          shape="버튼은 [data-tab-index], 내용은 [data-tab-panel] 속성으로 짝짓는다",
          must="[data-tab-index]", min_items=2, count_selector="[data-tab-index]",
          variants=tuple(Variant(n, d, f, fn) for n, d, f, fn in TABS_VARIANTS)),
]

BY_KEY = {b.key: b for b in BLOCKS}
LLM_BLOCKS = [b for b in BLOCKS if b.source != SERVER]
SERVER_BLOCKS = [b for b in BLOCKS if b.source == SERVER]
REQUIRED = [b.key for b in LLM_BLOCKS if b.required]


def build_plan_json_schema() -> dict:
    """
    LLM_BLOCKS 레지스트리로부터 실제 JSON Schema를 조립한다.
    이게 없으면 format="json"(그냥 유효한 JSON이면 통과)만 걸리는데,
    이 경우 모델이 존재하지 않는 type/variant를 지어내거나(unknown_type,
    unknown_variant), 옵션 블록(countdown 등)을 필드도 안 채운 채
    끼워 넣는 실패(missing_countdown_target_date)가 원천 차단되지
    않는다 — 실제로 이 스키마 없이 돌렸을 때 J군이 5/5 전부 실패했던
    원인이 정확히 이것이었다.

    oneOf + additionalProperties:false 조합으로 "정의된 type/variant
    조합, 정의된 필드만" 문법적으로 생성 가능하게 강제한다.
    """
    one_of = []
    for b in LLM_BLOCKS:
        for v in b.variants:
            props = {
                "type": {"const": b.key},
                "variant": {"const": v.name},
            }
            required = ["type", "variant"]
            for f in v.fields:
                if f == "items":
                    props["items"] = {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": max(b.min_items, 1),
                    }
                    required.append("items")
                elif f == "sub":
                    props["sub"] = {"type": "string"}   # sub는 선택 필드
                else:
                    props[f] = {"type": "string", "minLength": 1}
                    required.append(f)
            one_of.append({
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            })

    return {
        "type": "object",
        "properties": {
            "blocks": {
                "type": "array",
                "items": {"oneOf": one_of},
                "minItems": len(REQUIRED),
            },
        },
        "required": ["blocks"],
        "additionalProperties": False,
    }


def build_patch_json_schema() -> dict:
    """
    K군(패치) 방식용 스키마. action(patch/clarify/unsupported) 3분기와
    patch일 때의 오퍼레이션 종류를 문법적으로 강제한다.
    """
    block_keys = [b.key for b in LLM_BLOCKS]
    theme_fields = ["primaryColor", "buttonColor", "fontFamily", "headlineWeight"]
    preset_names = ["vivid", "cool", "minimal", "warm"]

    op_variants = [
        {"type": "object", "properties": {
            "op": {"const": "set_field"},
            "block_key": {"type": "string", "enum": block_keys},
            "field": {"type": "string"},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "append_item"},
            "block_key": {"type": "string", "enum": block_keys},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_block"},
            "block_key": {"type": "string", "enum": block_keys},
        }, "required": ["op", "block_key"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "add_block"},
            "type": {"type": "string", "enum": block_keys},
            "variant": {"type": "string"},
        }, "required": ["op", "type", "variant"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "set_theme"},
            "field": {"type": "string", "enum": theme_fields},
            "value": {"type": "string"},
        }, "required": ["op", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "apply_preset"},
            "name": {"type": "string", "enum": preset_names},
        }, "required": ["op", "name"], "additionalProperties": False},
    ]

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["patch", "clarify", "unsupported"]},
            "ops": {"type": "array", "items": {"oneOf": op_variants}},
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


def render_plan(plan: dict) -> str:
    """조합 계획 -> HTML. 태그는 전부 우리 것이다."""
    out = []
    for item in plan.get("blocks", []):
        if not isinstance(item, dict):
            continue
        b = BY_KEY.get(item.get("type"))
        if not b or b.source == SERVER or not b.variants:
            continue
        v = b.variant(item.get("variant")) or b.variants[0]

        missing = [f for f in v.fields
                   if f != "sub" and not str(item.get(f) or "").strip()
                   and not isinstance(item.get(f), list)]
        if missing:
            continue
        if "items" in v.fields:
            items = item.get("items")
            if not isinstance(items, list) or not items:
                continue
            item = {**item, "items": [x for x in items if isinstance(x, str) and x.strip()]}
            if not item["items"]:
                continue
        piece = v.render(item)
        if piece:
            out.append(piece)
    return "\n".join(out)


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
CSS_SAFE_IDENT = re.compile(r'^[A-Za-z0-9 ,\-\.\'\"]+$')

THEME_DEFAULTS = {
    "primaryColor": "#2d6cdf",
    "buttonColor": "#2d6cdf",
    "fontFamily": "Pretendard, sans-serif",
    "headlineWeight": "700",
}

THEME_FIELDS = {
    "primaryColor": ("페이지 전체 강조 색상 (HEX)",
                      lambda v: isinstance(v, str) and bool(HEX_COLOR.match(v))),
    "buttonColor": ("CTA 버튼 색상 (HEX)",
                     lambda v: isinstance(v, str) and bool(HEX_COLOR.match(v))),
    "fontFamily": ("본문 폰트 (영문/숫자/공백/쉼표/하이픈/따옴표/마침표만 허용)",
                    lambda v: isinstance(v, str) and 0 < len(v) <= 80
                    and bool(CSS_SAFE_IDENT.match(v))),
    "headlineWeight": ("제목 굵기 (400/500/600/700/800 중 하나)",
                        lambda v: v in {"400", "500", "600", "700", "800"}),
}

STYLE_PRESETS = {
    "vivid": {"primaryColor": "#e0a458", "buttonColor": "#e0a458", "headlineWeight": "800"},
    "cool": {"primaryColor": "#2d6cdf", "buttonColor": "#2d6cdf", "headlineWeight": "700"},
    "minimal": {"primaryColor": "#333333", "buttonColor": "#333333", "headlineWeight": "500"},
    "warm": {"primaryColor": "#d9736a", "buttonColor": "#d9736a", "headlineWeight": "700"},
}


def render_theme_style(theme: dict) -> str:
    t = {**THEME_DEFAULTS, **(theme or {})}
    return ("<style>\n"
            f"  :root {{ --primary-color: {t['primaryColor']}; --font-family: {t['fontFamily']}; }}\n"
            f"  h1, h2 {{ font-family: var(--font-family); font-weight: {t['headlineWeight']}; }}\n"
            f"  .btn {{ background: {t['buttonColor']}; }}\n"
            "</style>")


def assemble_page(plan: dict) -> str:
    blocks = plan.get("blocks", [])
    types_present = {b.get("type") for b in blocks if isinstance(b, dict)}
    scripts = ""
    if "countdown" in types_present:
        scripts += "\n" + COUNTDOWN_SCRIPT
    if "tabs" in types_present:
        scripts += "\n" + TAB_SWITCHER_SCRIPT
    return render_theme_style(plan.get("theme")) + "\n" + render_plan(plan) + scripts
