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


def _make_check(key: str, baseline: str, want: str = ""):
    """Case.extra_check(raw, html) 시그니처에 맞춘 클로저.

    engine 이 부르는 기본 채점(check_html)과 별개로, 제품 규격 보존 5종을
    여기서 얹는다. baseline 을 클로저에 가둬 두므로 클래스 대조가 그
    템플릿의 실제 클래스 기준으로 이뤄진다 — 테마마다 클래스가 다르기
    때문에 고정 목록으로는 불가능하다.
    """
    def _check(raw, html):
        fails, _ = checks_v4.check_product_rules(
            html, block=key, baseline_html=baseline)
        if want and want not in (html or ""):
            fails.append("request_not_applied")
        return fails
    return _check


def _case(pid, kind, tpl, key, prompt, want=""):
    baseline = T.block_html(tpl, key)
    return Case(
        pid, kind, "S-E",
        _system(key, baseline),
        f"{prompt}\n\n{baseline}",
        mode="html",
        keep=(key,),
        forbid=tuple(k for k in T.blocks_of(tpl) if k != key),
        extra_check=_make_check(key, baseline, want),
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
    _case("SE3", "혜택삭제_vip", 3, "benefits",
          "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘."),
    _case("SE4", "혜택추가_sale", 4, "benefits",
          "이 영역에 혜택 항목을 하나 더 추가해줘. "
          "기존 항목과 같은 구조로 만들어야 한다."),

    # ── 가장 긴 블록에서 부분만 고치기
    _case("SE5", "단계문구수정_launch", 5, "steps",
          "이 영역의 각 단계 설명을 더 짧고 간결하게 다듬어줘. "
          "단계 개수는 그대로 둬라."),
]


def self_check():
    assert len(CASES) == 5, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "S-E"
        assert c.mode == "html"
        assert c.extra_check is not None, f"{c.pid} extra_check 누락"
        assert len(c.keep) == 1, f"{c.pid} 는 블록 하나만 다뤄야 한다"
        key = c.keep[0]
        assert f'data-block="{key}"' in c.prompt, f"{c.pid} 프롬프트에 baseline 없음"
        assert key not in c.forbid, f"{c.pid} keep/forbid 충돌"

    # 실제 baseline 을 그대로 되돌려주면 규격 검사를 통과해야 한다
    for tpl in T.NAMES:
        for key in ("hero", "benefits", "steps", "cta"):
            h = T.block_html(tpl, key)
            f, _ = checks_v4.check_product_rules(h, block=key, baseline_html=h)
            assert not f, f"template_{tpl} {key} 원본이 규격 검사에 걸림: {f}"

    # 클래스를 지우면 잡혀야 한다
    base = T.block_html(1, "benefits")
    broken = base.replace("benefit-card", "x")
    f, _ = checks_v4.check_product_rules(broken, block="benefits", baseline_html=base)
    assert "class_lost" in f, "클래스 유실을 못 잡음"

    print("  [cases_se] self_check 통과")
