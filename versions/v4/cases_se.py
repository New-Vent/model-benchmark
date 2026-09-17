"""
cases_se.py — S-E 군: 실제 제품 블록을 HTML 로 직접 수정
==========================================================
`AI_EDIT_RULES.md` §1-1 이 정의한 제품의 주 경로다.

    "LLM 은 전체 HTML 문서를 생성하지 않고, 관리자가 클릭하여 지정한
     단일 <section data-block="..."> 을 수정합니다."

v1 의 E군(블록 왕복)과 같은 메커니즘이지만 baseline 이 다르다.

    v1 E군   인공 블록      80자    형태 규칙 ul/li, a
    v4 S-E   실제 제품 블록  291~1,447자   .benefit-card, button.cta-btn, 테마 클래스

채점은 `checks_v4.check_html_v4` 를 쓴다 — 기존 check_html 에 제품 규격
보존 5종(class_lost · data_block_changed · inline_style · theme_leaked ·
nested_section)을 얹은 것이다.

**이 군이 답하는 질문**: 모델이 `AI_EDIT_RULES.md` §3 "디자인 필수 클래스
불변 유지"를 지킬 수 있는가. 못 지키면 HTML 노선(A)은 쓸 수 없다.
"""

from engine import Case

import checks_v4
import templates as T

GROUPS = ["S-E"]

# 블록 하나만 출력하므로 html 캡(1536)으로 충분하다.
#   실측: hero 660 tok · benefits 572 · steps 471 · cta 133
# 전체 페이지 생성(1,985~2,443 tok)은 캡을 넘어서 이번 군에 넣지 않았다.


def _system(key: str, baseline: str) -> str:
    """블록 하나만 고치게 하고, 제품 계약을 프롬프트에 명시한다."""
    return "\n".join([
        "너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.",
        "",
        f'<section data-block="{key}"> 영역만 수정해서 그 영역만 출력한다.',
        "",
        "출력 규칙:",
        f'- <section data-block="{key}"> 로 시작해서 </section> 으로 끝난다.',
        "- 다른 영역을 새로 만들지 마라.",
        "- 코드블록으로 감싸지 마라. 설명을 붙이지 마라.",
        "",
        "반드시 그대로 두어야 하는 것:",
        f'- data-block="{key}" 속성',
        "- class 속성에 있는 모든 클래스 이름 (디자인이 여기에 걸려 있다)",
        "- 요청받지 않은 텍스트와 구조",
        "",
        "금지:",
        '- style="..." 을 새로 넣지 마라. 색과 여백은 CSS 가 담당한다.',
        "- theme- 으로 시작하는 클래스를 넣지 마라.",
        "- <section> 안에 <section> 을 만들지 마라.",
        "- 날짜를 임의로 만들지 마라.",
        "- 대괄호 자리표시자를 남기지 마라.",
    ])


def _make_check(key: str, baseline: str, want: str = "", expect_items=None):
    """Case.extra_check(raw, html) 시그니처에 맞춘 클로저.

    ★ keep=() 로 두는 이유
        engine 은 check_html(..., strict_structure=True) 를 하드코딩으로
        부르고, 그 안에서 keep 에 든 블록마다 registry 의 must 셀렉터를
        검사한다. 그런데 must 는 벤치마크 전용 규격(ul li / ol li / a)이라
        **실제 제품 마크업에서는 원본을 넣어도 실패한다** — 실측으로
        20개 중 15개가 empty_* 로 떨어지는 것을 확인했다.

        그래서 keep 을 비워 그 검사를 끄고, 블록 존재·항목 수는 여기서
        실제 템플릿 기준으로 직접 본다. check_html 의 나머지 검사(태그
        균형, 금지 태그, no_section, placeholder 등)는 그대로 살아 있다.

    expect_items: 수정 후 있어야 할 항목 개수. None 이면 검사하지 않는다.
    """
    def _check(raw, html):
        html = html or ""
        fails, _ = checks_v4.check_product_rules(
            html, block=key, baseline_html=baseline)

        soup = checks_v4._soup(html)
        el = soup.select_one(f'[data-block="{key}"]') if soup else None
        if el is None:
            # data_block_changed 가 이미 같은 사실을 잡았으면 중복으로 세지 않는다
            if "data_block_changed" not in fails:
                fails.append(f"lost_{key}")
            return fails

        if expect_items is not None and key in T.ITEM_SELECTORS:
            n = len(el.select(T.ITEM_SELECTORS[key]))
            if n != expect_items:
                fails.append(f"item_count_{key}")

        if want and want not in html:
            fails.append("request_not_applied")
        return fails
    return _check


def _case(pid, kind, tpl, key, prompt, want="", expect_items=None):
    baseline = T.block_html(tpl, key)
    return Case(
        pid, kind, "S-E",
        _system(key, baseline),
        f"{prompt}\n\n{baseline}",
        mode="html",
        keep=(),          # ← 벤치마크 전용 must 검사를 끈다 (위 주석 참고)
        forbid=tuple(k for k in T.blocks_of(tpl) if k != key),
        extra_check=_make_check(key, baseline, want, expect_items),
    )


CASES = [
    # ── 텍스트만 바꾸기 — 구조를 건드릴 이유가 전혀 없는 요청
    _case("SE1", "버튼문구수정_sports", 1, "cta",
          "이 영역의 버튼 문구를 '지금 응원하기' 로 바꿔줘.",
          want="지금 응원하기"),
    _case("SE2", "제목수정_holiday", 2, "hero",
          "이 영역의 제목을 '설 선물 대축제' 로 바꿔줘.",
          want="설 선물 대축제"),

    # ── 항목 수 바꾸기 — 반복 구조를 유지한 채 늘리고 줄여야 한다
    #    baseline 은 셋 다 3개. 삭제면 2, 추가면 4, 문구만 고치면 3이어야 한다.
    _case("SE3", "혜택삭제_vip", 3, "benefits",
          "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.",
          expect_items=2),
    _case("SE4", "혜택추가_sale", 4, "benefits",
          "이 영역에 혜택 항목을 하나 더 추가해줘. "
          "기존 항목과 같은 구조로 만들어야 한다.",
          expect_items=4),

    # ── 가장 긴 블록에서 부분만 고치기
    _case("SE5", "단계문구수정_launch", 5, "steps",
          "이 영역의 각 단계 설명을 더 짧고 간결하게 다듬어줘. "
          "단계 개수는 그대로 둬라.",
          expect_items=3),
]


def self_check():
    from checks import check_html

    assert len(CASES) == 5, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "S-E"
        assert c.mode == "html"
        assert c.extra_check is not None, f"{c.pid} extra_check 누락"
        assert c.keep == (), (
            f"{c.pid}: keep 이 비어 있어야 한다. 비우지 않으면 engine 이 registry 의 "
            f"must(ul li / ol li / a)로 검사해서 실제 제품 마크업이 오탐으로 떨어진다")
        assert c.forbid, f"{c.pid} forbid 가 비었다 — 다른 블록 생성을 못 막는다"

    # ★ 회귀 — 실제 템플릿 원본을 그대로 되돌려주면 전부 통과해야 한다.
    #   (이 검사가 없어서 1차 실행의 S-E 결과를 통째로 버렸다)
    for c, (tpl, key) in zip(CASES, [(1, "cta"), (2, "hero"), (3, "benefits"),
                                     (4, "benefits"), (5, "steps")]):
        h = T.block_html(tpl, key)

        base_fails, _ = check_html(raw=h, html=h, keep=c.keep, forbid=c.forbid,
                                   strict_structure=True)
        assert not base_fails, (
            f"{c.pid}: template_{tpl} {key} 원본이 기본 채점에 걸림: {base_fails}")

        extra = c.extra_check(h, h)
        # 항목 수를 바꾸라고 한 케이스는 원본이 걸리는 게 정상이다
        expected = {"SE3": [f"item_count_{key}"], "SE4": [f"item_count_{key}"],
                    "SE1": ["request_not_applied"], "SE2": ["request_not_applied"]}
        assert sorted(extra) == sorted(expected.get(c.pid, [])), (
            f"{c.pid}: 원본에 대한 extra_check 가 예상과 다름 {extra}")

    # 클래스를 지우면 잡혀야 한다
    base = T.block_html(1, "benefits")
    broken = base.replace("benefit-card", "x")
    f, _ = checks_v4.check_product_rules(broken, block="benefits", baseline_html=base)
    assert "class_lost" in f, "클래스 유실을 못 잡음"

    print("  [cases_se] self_check 통과")
