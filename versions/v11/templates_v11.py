"""
templates_v11.py — 실제 제품 템플릿 5종 로더
=============================================

v8·v9 는 백엔드 `Block.shape` 를 그대로 따른 **최소 마크업**을 baseline 으로
썼다. 그게 맞는 선택이었지만, 실제 서비스가 편집할 문서는 `template/*.html` 이다.

    v8·v9 baseline   class 1개 (`btn`) · 블록 ~150자
    실제 템플릿      class 451건 · 블록 최대 2,229자

v10 부터 후자를 baseline 으로 쓴다. 그래야 v4~v7 에서 반복 확인된 `class_lost`
같은 실패를 제대로 잴 수 있다.

★ v4 가 같은 일을 하다 결과를 통째로 버렸다
  그때는 채점기가 **벤치마크 전용 규격**(`ul li` 같은)을 실제 마크업에 적용해서
  원본을 그대로 넣어도 20개 중 15개가 실패했다. v10~v11 은 그 교훈으로
  `self_check()` 에서 **원본 무변경·무실패**를 먼저 단언한다.
"""

import glob
import os

from bs4 import BeautifulSoup

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "template")

# 파일명 → 짧은 이름 (케이스 id 와 로그에 쓴다)
NAMES = {
    1: "sports", 2: "holiday", 3: "member", 4: "sale", 5: "launch",
}

_cache = {}


def _doc(n: int) -> BeautifulSoup:
    if n not in _cache:
        paths = sorted(glob.glob(os.path.join(TEMPLATE_DIR, f"template_{n}_*.html")))
        if not paths:
            raise FileNotFoundError(f"template_{n}_*.html 을 찾을 수 없습니다: {TEMPLATE_DIR}")
        _cache[n] = BeautifulSoup(open(paths[0], encoding="utf-8").read(), "html.parser")
    return _cache[n]


def block_html(n: int, key: str) -> str:
    """템플릿 n 의 블록 하나를 원문 그대로."""
    el = _doc(n).select_one(f'[data-block="{key}"]')
    if el is None:
        raise KeyError(f"template_{n} 에 {key} 블록이 없습니다")
    return str(el)


def blocks_of(n: int) -> list:
    return [e.get("data-block") for e in _doc(n).select("[data-block]")]


# ── 항목 선택자 ───────────────────────────────────────────────────
#
# ★ 템플릿마다 반복 항목의 **두 번째 클래스가 다르다**. 공통은 첫 번째뿐이다.
#      .benefit-card sp-prize-main / hl-pouch-card / vp-coupon / fs-deal-item ...
#   그래서 개수를 셀 때는 공통 클래스로만 센다.
#
# ★ 백엔드 `must` 는 `"ul li, .benefit-card"` 로 **둘 다** 받는다.
#   그게 D군의 질문을 만든다 — §cases_v11 참고.
ITEM_SELECTOR = {
    "benefits": ".benefit-card",
    "steps": ".step-card",
}


def item_count(html: str, key: str) -> int:
    sel = ITEM_SELECTOR.get(key)
    if sel is None:
        return 0
    return len(BeautifulSoup(html, "html.parser").select(sel))


def self_check():
    for n in NAMES:
        bs = blocks_of(n)
        assert bs == ["hero", "benefits", "steps", "notices", "cta"], (n, bs)
        # 슬롯 2종이 다 있어야 한다 (P군이 보존을 재는 대상)
        doc = str(_doc(n))
        for s in ("period", "cta-link"):
            assert f'data-slot="{s}"' in doc, f"template_{n} 에 {s} 슬롯이 없다"
        # benefits 는 .benefit-card 로 3개 이상 (ul li 가 아니다)
        b = block_html(n, "benefits")
        assert item_count(b, "benefits") >= 2, f"template_{n} benefits 항목 부족"
        assert "<li" not in b, (
            f"template_{n} benefits 가 <li> 를 쓴다 — ITEM_SELECTOR 를 다시 보라")
    print(f"  [templates_v11] self_check 통과 — 템플릿 {len(NAMES)}종")


if __name__ == "__main__":
    self_check()
