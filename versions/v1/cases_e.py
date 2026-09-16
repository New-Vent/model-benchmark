"""
cases_e.py — E군: 왕복 단위 3단 (실제 구현)
==============================================
담당자만 이 파일을 건드리세요.

업로드된 benchmark_v8_3.py의 check_edit()/canonical()/outside_preserved()
로직을 그대로 포팅했다 — 그 파일 자체는 "이 파일을 고치지 마세요"로
잠긴 팀 공용 버전이라 손대지 않고, 이 modular 아키텍처(run.py로
군별 개별 실행 가능)에 맞춰 별도로 옮겨 담은 것이다.

## 핵심 아이디어 — canonical()

"요청한 부분만 정확히 바뀌었는지"를 판정하려면, 그냥 문자열을
통째로 비교하면 안 된다(공백 하나만 달라도 다르다고 나옴). 대신:

  1. 대상 블록(cta 등)만 통째로 지운 뒤 나머지 DOM 구조를 비교
     → "요청 안 한 부분이 한 글자도 안 바뀌었는지" 확인
  2. 대상 블록 안에서는 "바뀌어야 할 요소"만 플레이스홀더로 치환한 뒤
     비교 → "딱 그 부분만 바뀌고 나머지 속성/구조는 그대로인지" 확인

이 두 비교 모두를 canonical()이라는 하나의 정규화 함수로 처리한다
(태그명 + 속성 + 자식 노드를 재귀적으로 튜플화 → 순서/공백에 안
흔들리는 구조적 동등성 비교).

## 세 가지 방식 비교 (E1/E4 vs E2/E5)

  E1/E4 (전체 재생성) — 문서 전체를 다시 쓰게 시키고, "나머지는
                        그대로 유지"라고 지시. 실제로 지켜지는지 검증.
  E2/E5 (블록 왕복)   — 대상 블록 하나만 떼어서 보여주고, 그 블록만
                        다시 쓰게 함. 다른 블록은 애초에 LLM 출력에
                        등장할 수 없음(K군과 같은 안전 원리).
  (E3/E6 패치는 cases_k.py의 케이스로 이미 커버됨 — 같은 요청을
   K1/K7이 이미 테스트하고 있으므로 중복 구현하지 않는다.)
"""

from bs4 import BeautifulSoup, NavigableString
import re

from engine import Case
from registry import BY_KEY

SOFT_FAILS_LOCAL = {"code_fence", "extra_text"}


# ── 고정 입력 문서 (registry.py의 Variant 시스템과 무관하게, E군은
#    "정확히 이 문서에서 정확히 이 부분만 바뀌었는가"를 재는 게
#    목적이라 단순한 고정 HTML 문자열을 그대로 쓴다) ──────────────

SHORT_DOC = """<section data-block="hero">
  <h1>여름 데이터 대방출</h1>
  <p>이번 여름 데이터 걱정 없이 마음껏 즐기세요</p>
</section>
<section data-block="benefits">
  <h2>혜택</h2>
  <ul><li>데이터 3GB 즉시 지급</li><li>월 요금 30% 할인</li></ul>
</section>
<section data-block="cta">
  <a href="#" class="btn">가입하기</a>
</section>"""

LONG_DOC = """<section data-block="hero">
  <h1>여름 데이터 대방출 페스타</h1>
  <p>이번 여름, 데이터 걱정 없이 마음껏 즐기세요</p>
  <p class="period">2026년 8월 1일 ~ 8월 31일</p>
</section>
<section data-block="benefits">
  <h2>이런 혜택을 드립니다</h2>
  <ul>
    <li><strong>데이터 3GB 즉시 지급</strong> — 가입 완료 즉시 자동 충전</li>
    <li><strong>월 요금 30% 할인</strong> — 개통 익월부터 6개월간 적용</li>
    <li><strong>제휴 카페 음료 쿠폰</strong> — 매월 1장씩 총 3장 제공</li>
  </ul>
</section>
<section data-block="steps">
  <h2>참여 방법</h2>
  <ol>
    <li>이벤트 페이지에서 요금제 선택</li>
    <li>온라인으로 가입 신청서 작성</li>
    <li>개통 완료 후 혜택 자동 적용</li>
  </ol>
</section>
<section data-block="notices">
  <h2>유의사항</h2>
  <ul>
    <li>본 이벤트는 신규 가입 및 번호이동 고객을 대상으로 합니다.</li>
    <li>데이터 쿠폰은 지급일로부터 30일간 유효합니다.</li>
  </ul>
</section>
<section data-block="cta">
  <a href="#" class="btn">가입하기</a>
</section>"""


def _safe_soup(markup):
    """BeautifulSoup 파싱을 안전하게 감싼다 — 깨진 마크업(<![--- 등)이
    ParserRejectedMarkup을 던져 전체를 죽이는 걸 방지한다."""
    try:
        return BeautifulSoup(markup or "", "html.parser")
    except Exception:
        return BeautifulSoup("", "html.parser")


def block_of(html: str, key: str) -> str:
    el = _safe_soup(html).select_one(f'[data-block="{key}"]')
    return str(el) if el else ""


def canonical(node):
    """DOM 노드를 순서/공백에 안 흔들리는 튜플로 정규화한다.
    문자열 그대로 비교하면 공백 하나만 달라도 '다르다'고 나오는데,
    실제로 우리가 알고 싶은 건 '구조와 내용이 의미상 같은가'다."""
    if isinstance(node, NavigableString):
        return ("text", re.sub(r"\s+", " ", str(node)).strip())
    attrs = tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                         for k, v in node.attrs.items())) if getattr(node, "attrs", None) else ()
    return (node.name, attrs, tuple(
        canonical(c) for c in node.children
        if not isinstance(c, NavigableString) or str(c).strip()
    ))


def outside_preserved(before: str, after: str, key: str) -> bool:
    """대상 블록(key)을 뺀 나머지가 정말로 한 글자도 안 바뀌었는지 확인.
    섹션 순서 자체가 바뀌었는지도 함께 본다 — 단, '원래 없던 블록을
    새로 추가'하는 경우(E군에서는 안 쓰지만 C군 등에서 재사용 가능)는
    예외로 허용한다."""
    a, b = _safe_soup(before), _safe_soup(after)
    old_keys = [x.get("data-block") for x in a.find_all("section")]
    new_keys = [x.get("data-block") for x in b.find_all("section")]
    if new_keys != old_keys and not (key not in old_keys and new_keys == old_keys + [key]):
        return False
    for doc in (a, b):
        for el in doc.select(f'[data-block="{key}"]'):
            el.decompose()
    return canonical(a) == canonical(b)


def check_cta_text_edit(baseline: str, html: str, want_text: str) -> list:
    """
    cta 블록의 버튼 문구만 정확히 바뀌었는지 확인한다.
    - 요청한 문구로 정확히 바뀌었는가 (request_not_applied)
    - href, class 등 다른 속성은 그대로인가 (diff_unintended)
    - 대상 블록 외 다른 블록은 한 글자도 안 바뀌었는가 (diff_unintended, outside_preserved로 처리)
    """
    fails = []
    a, b = _safe_soup(baseline), _safe_soup(html)
    aa = a.select_one('[data-block="cta"]')
    bb = b.select_one('[data-block="cta"]')

    if bb is None:
        return ["edit_target_missing"]

    if not outside_preserved(baseline, html, "cta"):
        fails.append("diff_unintended")

    old_a, new_a = (aa.find("a") if aa else None), bb.find("a")
    if new_a is None or new_a.get_text(strip=True) != want_text:
        fails.append("request_not_applied")
    if old_a is None:
        fails.append("edit_element_missing")
    else:
        # 텍스트만 플레이스홀더로 맞춘 뒤 나머지(속성 등)가 같은지 확인
        old_copy, new_copy = _safe_soup(str(aa)), _safe_soup(str(bb))
        oa, na = old_copy.find("a"), new_copy.find("a")
        if oa and na:
            oa.clear(); oa.append("__EDIT_TEXT__")
            na.clear(); na.append("__EDIT_TEXT__")
            if canonical(old_copy) != canonical(new_copy):
                fails.append("diff_unintended")

    return list(dict.fromkeys(fails))


def make_extra_check(baseline: str, want_text: str):
    """Case.extra_check(raw, html) 시그니처에 맞춰 클로저로 감싼다."""
    def _check(raw, html):
        return check_cta_text_edit(baseline, html, want_text)
    return _check


SYSTEM_WHOLE_EDIT = """너는 기존 이벤트 HTML을 수정한다.
사용자가 요청한 변경만 수행하고 나머지 텍스트, 태그, 속성, 영역 순서를 유지한다.
기존 notices는 서버가 이미 제공한 내용이므로 삭제하거나 수정하지 않는다.
입력의 section 조각 전체만 출력한다. 설명, 코드펜스, html/head/body는 출력하지 않는다.
새로운 날짜, 혜택, 링크를 만들어내지 않는다."""


def build_block_edit_system(key: str) -> str:
    """블록 하나만 고칠 때 — 그 블록 외에는 출력 자체를 막는다."""
    b = BY_KEY[key]
    lines = [
        "너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.",
        "",
        f'<section data-block="{key}"> 영역만 수정해서 그 영역만 출력한다.',
        f"이 영역의 역할: {b.desc}",
    ]
    if b.shape:
        lines.append(f"형태: {b.shape}")
    lines += [
        "",
        "출력 규칙:",
        f'- <section data-block="{key}"> 로 시작해서 </section> 으로 끝난다.',
        "- 다른 영역을 새로 만들지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명을 붙이지 마라.",
        "",
        "금지:",
        "- 요청받은 것만 바꿔라. href, class 같은 기존 속성은 그대로 둔다.",
        '- href="#" 는 그대로 둬라. 실제 주소를 만들어 넣지 마라.',
        "- 날짜를 임의로 만들지 마라.",
        "- 대괄호 자리표시자를 남기지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


EDIT_REQUEST = "버튼 문구만 '지금 신청하기'로 바꿔줘."

CASES = [
    # E1/E4 — 전체 재생성 방식. "나머지는 그대로 유지"를 텍스트로만
    # 지시하고 실제로 지켜지는지 본다 (K/E2 대비 안전성이 낮을 것으로
    # 예상되는 대조군).
    Case("E1", "전체재생성_짧은문서", "E", SYSTEM_WHOLE_EDIT,
         f"다음 HTML에서 {EDIT_REQUEST} "
         f"나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n{SHORT_DOC}",
         mode="html", keep=("hero", "benefits", "cta"), forbid=(),
         extra_check=make_extra_check(SHORT_DOC, "지금 신청하기")),

    Case("E4", "전체재생성_긴문서", "E", SYSTEM_WHOLE_EDIT,
         f"다음 HTML에서 {EDIT_REQUEST} "
         f"나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n{LONG_DOC}",
         mode="html", keep=("hero", "benefits", "steps", "notices", "cta"), forbid=(),
         extra_check=make_extra_check(LONG_DOC, "지금 신청하기"), pair="E1"),

    # E2/E5 — 블록 왕복 방식. 대상 블록(cta)만 떼어 보여주고 그것만
    # 다시 쓰게 한다. 다른 블록은 LLM 출력에 등장할 수조차 없다.
    Case("E2", "블록왕복_짧은문서", "E", build_block_edit_system("cta"),
         f"이 영역의 {EDIT_REQUEST}\n\n" + block_of(SHORT_DOC, "cta"),
         mode="html", keep=("cta",),
         forbid=("hero", "benefits", "steps", "notices"),
         extra_check=make_extra_check(block_of(SHORT_DOC, "cta"), "지금 신청하기"),
         pair="E1"),

    Case("E5", "블록왕복_긴문서", "E", build_block_edit_system("cta"),
         f"이 영역의 {EDIT_REQUEST}\n\n" + block_of(LONG_DOC, "cta"),
         mode="html", keep=("cta",),
         forbid=("hero", "benefits", "steps", "notices"),
         extra_check=make_extra_check(block_of(LONG_DOC, "cta"), "지금 신청하기"),
         pair="E4"),
]


def self_check():
    # canonical/outside_preserved 자체가 제대로 동작하는지
    for key in ("hero", "benefits", "cta"):
        assert block_of(SHORT_DOC, key), f"SHORT_DOC에서 {key}를 못 뗌"
    for key in ("hero", "benefits", "steps", "notices", "cta"):
        assert block_of(LONG_DOC, key), f"LONG_DOC에서 {key}를 못 뗌"

    # 정상 수정 — 실패 없어야 함
    good = SHORT_DOC.replace("가입하기", "지금 신청하기")
    assert not check_cta_text_edit(SHORT_DOC, good, "지금 신청하기"), \
        "정상적인 수정인데 실패로 판정됨"

    # 요청을 아예 반영 안 한 경우 — 반드시 잡혀야 함
    assert "request_not_applied" in check_cta_text_edit(SHORT_DOC, SHORT_DOC, "지금 신청하기")

    # href를 실수로 바꾼 경우 — diff_unintended로 잡혀야 함
    wrong_href = good.replace('href="#"', 'href="https://wrong.example"')
    assert "diff_unintended" in check_cta_text_edit(SHORT_DOC, wrong_href, "지금 신청하기")

    # cta 블록을 중복으로 만든 경우 — outside_preserved가 잡아야 함
    duplicated = good + block_of(good, "cta")
    assert check_cta_text_edit(SHORT_DOC, duplicated, "지금 신청하기"), \
        "cta 중복 생성을 못 잡아냄"

    # 다른 블록(hero)까지 몰래 바뀐 경우 — outside_preserved가 잡아야 함
    drifted = good.replace("여름 데이터 대방출", "여름 데이터 대방출!")
    assert "diff_unintended" in check_cta_text_edit(SHORT_DOC, drifted, "지금 신청하기"), \
        "요청 안 한 hero 변경(드리프트)을 못 잡아냄"

    assert len(CASES) == 4
    for c in CASES:
        assert c.group == "E"
        assert c.mode == "html"
        assert c.extra_check is not None, f"{c.pid}에 extra_check(수정 검증) 누락"

    print("  E1/E4(전체재생성) vs E2/E5(블록왕복) 페어링 확인")
    print("  canonical/outside_preserved DOM 정규화 비교 회귀 통과")
    print("  (정상수정/미반영/속성오류/블록중복/타블록드리프트 5가지 시나리오 검증)")
