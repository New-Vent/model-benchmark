"""
templates.py — 실제 제품 템플릿을 케이스 baseline 으로 읽어오는 로더
====================================================================
`template/template_1~5.html` 은 팀이 만든 **실제 서비스 템플릿**이다.
v1~v3 이 쓰던 인공 문서(370~590자)와 달리 4,351~5,356자이고,
`.benefit-card` · `.step-card` · `button.cta-btn` 같은 제품 마크업을 쓴다.

여기서 두 가지를 뽑는다.

    block_html(t, "cta")   → 그 블록의 outerHTML  (S 노선 baseline)
    plan_of(t)             → 같은 내용을 담은 plan (K 노선 baseline)

plan_of 의 한계 — 반드시 읽을 것
    현재 `base/component_library.py` 의 variant 들은 Tailwind 풍 마크업을
    낸다(`mx-auto max-w-screen-xl ...`). 실제 템플릿의 `ev-block block-*`
    마크업과 완전히 다르다. 그래서 plan_of 는 **내용(문구·항목 수·분량)만**
    실제 템플릿에서 가져오고, variant 는 기존 것을 쓴다.

    K 노선에서 모델은 plan JSON 만 보고 마크업을 아예 안 보므로, 모델의
    패치 능력을 재는 데는 이걸로 충분하다. 다만 렌더 결과의 클래스 보존
    검사는 할 수 없다 — component_library 에 실제 템플릿 variant 가
    등록된 뒤에 가능하다(레지스트리 파트 작업).
"""

import os
import re

from bs4 import BeautifulSoup

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "template",
)

NAMES = {
    1: "template_1_sports_cheer",
    2: "template_2_holiday_gift",
    3: "template_3_member_appreciation",
    4: "template_4_flash_sale",
    5: "template_5_pre_registration",
}

_cache = {}


def _soup(n: int):
    if n not in _cache:
        path = os.path.join(TEMPLATE_DIR, NAMES[n] + ".html")
        with open(path, encoding="utf-8") as f:
            _cache[n] = BeautifulSoup(f.read(), "html.parser")
    return _cache[n]


def container(n: int) -> str:
    """페이지 본문(.ev-container) 전체."""
    return str(_soup(n).find("div", class_="ev-container"))


def block_html(n: int, key: str) -> str:
    """블록 하나의 outerHTML. 없으면 빈 문자열."""
    el = _soup(n).select_one(f'[data-block="{key}"]')
    return str(el) if el else ""


def blocks_of(n: int) -> list:
    """그 템플릿에 있는 data-block 이름들 (문서 순서)."""
    c = _soup(n).find("div", class_="ev-container")
    return [s["data-block"] for s in c.find_all(attrs={"data-block": True})]


def theme_of(n: int) -> str:
    body = _soup(n).find("body")
    for c in (body.get("class", []) if body else []):
        if c.startswith("theme-"):
            return c
    return ""


# ── plan 추출 ────────────────────────────────────────────────

def _txt(el, sel):
    x = el.select_one(sel) if el else None
    return " ".join(x.get_text(" ", strip=True).split()) if x else ""


def _hero_fields(el):
    title = _txt(el, "h1") or _txt(el, ".hero-title")
    sub = _txt(el, ".hero-desc") or _txt(el, "p")
    return {"title": title, "sub": sub}


# 템플릿마다 항목 컨테이너 클래스가 전부 다르다. 실측으로 확인한 목록.
#   benefits : benefit-card(1) · hl-pouch-card(2) · vp-coupon(3)
#              fs-deal-item(4) · lc-milestone-item(5)
#   steps    : step-card(1·4·5) · hl-step-item(2) · vp-step-row(3)
#
# 이것이 `class_lost` 를 하드코딩 목록이 아니라 **baseline 대조**로
# 구현한 이유다 — 테마마다 계약 클래스가 다르므로 고정 목록으로는
# 다섯 템플릿을 다 못 덮는다.
ITEM_SELECTORS = {
    "benefits": (".benefit-card, .sp-prize-main, .hl-pouch-card, "
                 ".vp-coupon, .fs-deal-item, .lc-milestone-item"),
    "steps": ".step-card, .hl-step-item, .vp-step-row",
}


def _flat(node) -> str:
    """노드의 보이는 텍스트를 한 줄로. 마크업은 버린다."""
    return " ".join(node.get_text(" ", strip=True).split())


def _items_of(el, key: str) -> list:
    """반복 항목을 문자열 리스트로.

    실제 카드는 tag/icon/name/desc/value 같은 여러 필드로 쪼개져 있지만
    기존 variant 의 fields 는 ("items",) 라 문자열 리스트만 받는다.
    항목 수와 한국어 문장 분량은 그대로 유지되므로, 모델이 plan JSON
    만 보는 K 노선을 재는 데는 지장이 없다.
    """
    items, taken = [], []
    for c in el.select(ITEM_SELECTORS[key]):
        # 중첩 매칭 방지 — 이미 담은 항목의 자손이면 건너뛴다
        if any(c in prev.descendants for prev in taken):
            continue
        line = _flat(c)
        if line:
            taken.append(c)
            items.append(line)
    return items


def _cta_label(el):
    b = el.select_one(".cta-btn, button, a")
    return " ".join(b.get_text(" ", strip=True).split()) if b else ""


def plan_of(n: int, variants: dict = None) -> dict:
    """템플릿의 **내용**으로 만든 plan.

    variants 로 블록별 variant 이름을 지정할 수 있다. 기본은
    flowbite 계열(카드형)이라 실제 템플릿 성격에 가장 가깝다.
    notices 는 서버 소유라 plan 에 넣지 않는다.
    """
    v = {"hero": "flowbite_split", "benefits": "flowbite_cards",
         "steps": "hyperui_numbered", "cta": "flowbite_banner"}
    if variants:
        v.update(variants)

    from registry import THEME_DEFAULTS

    blocks = []
    for key in blocks_of(n):
        if key == "notices":            # 서버 소유 — LLM 이 다루지 않는다
            continue
        el = _soup(n).select_one(f'[data-block="{key}"]')
        if key == "hero":
            blocks.append({"type": "hero", "variant": v["hero"], **_hero_fields(el)})
        elif key == "benefits":
            blocks.append({"type": "benefits", "variant": v["benefits"],
                           "items": _items_of(el, "benefits")})
        elif key == "steps":
            blocks.append({"type": "steps", "variant": v["steps"],
                           "items": _items_of(el, "steps")})
        elif key == "cta":
            blocks.append({"type": "cta", "variant": v["cta"], "label": _cta_label(el)})
    return {"blocks": blocks, "theme": dict(THEME_DEFAULTS)}


# ── 자기 점검 ────────────────────────────────────────────────

def self_check():
    assert os.path.isdir(TEMPLATE_DIR), f"템플릿 폴더가 없습니다: {TEMPLATE_DIR}"
    for n in NAMES:
        bs = blocks_of(n)
        assert bs == ["hero", "benefits", "steps", "notices", "cta"], \
            f"template_{n} 블록 구성이 다릅니다: {bs}"
        assert theme_of(n).startswith("theme-"), f"template_{n} 테마 클래스 없음"
        for k in bs:
            assert block_html(n, k), f"template_{n} 의 {k} 블록을 못 읽음"

        p = plan_of(n)
        keys = [b["type"] for b in p["blocks"]]
        assert "notices" not in keys, "notices 는 plan 에 넣으면 안 됩니다"
        assert keys == ["hero", "benefits", "steps", "cta"], f"plan 블록: {keys}"
        for b in p["blocks"]:
            for f, val in b.items():
                if f in ("type", "variant"):
                    continue
                if isinstance(val, list):
                    assert val and all(isinstance(x, str) and x.strip() for x in val), \
                        f"template_{n} {b['type']}.{f} 가 비었습니다"
                    assert len(val) >= 2, f"template_{n} {b['type']} 항목이 2개 미만"
                else:
                    assert isinstance(val, str) and val.strip(), \
                        f"template_{n} {b['type']}.{f} 가 비었습니다"
                    # 평평하게 만든 값에 태그가 섞이면 안 된다
                    assert not re.search(r"</?[a-zA-Z]", val), \
                        f"template_{n} {b['type']}.{f} 에 태그가 섞임"
    print("  [templates] self_check 통과")


if __name__ == "__main__":
    self_check()
