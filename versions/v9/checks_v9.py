"""
checks_v9.py — 백엔드 `registry.BlockValidator` 미러
=====================================================

Java 쪽 extract / sanitize / validateGenerated / validateEdited / merge 를
옮긴 것이다.

★★ v1~v7 과 결정적으로 다른 점: **정화(sanitize) 뒤를 채점한다.**

    지금까지 벤치마크 :  raw → extract → check 
    현재 백엔드 :        raw → extract → sanitize → validate 

    이 차이가 실제 버그를 숨겼다. 모델이 `<a href="#">` 를 올바르게 냈는데
    정화가 href 를 지워버리고, 검증은 "`<a>` 가 있나"만 보니 통과한다.
    **모델 출력이 맞아도 제품은 깨진다.** 정화 전을 채점하면 이걸 영영 못 본다.

    그래서 v8 의 판정 순서는 서비스와 같다. `run_v9.py` 가 이 순서를 강제한다.

★ 정화는 Jsoup Safelist 를 파이썬으로 흉내 낸 것이다 — **의도적으로 버그까지
  같이 옮겼다.** 여기가 서비스보다 관대하면 v8 은 "통과했는데 실제로는 깨지는"
  모델을 고르게 된다. `self_check()` 가 그 동치성을 검사한다.
"""

import re

from bs4 import BeautifulSoup, NavigableString

import registry_v9 as R

# ── Jsoup Safelist.relaxed() 의 태그 목록 (jsoup 1.17 기준)
_RELAXED_TAGS = {
    "a", "b", "blockquote", "br", "caption", "cite", "code", "col", "colgroup",
    "dd", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "i",
    "img", "li", "ol", "p", "pre", "q", "small", "span", "strike", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}

# Safelist.relaxed() 의 태그별 허용 속성
_RELAXED_ATTRS = {
    "a": {"href"},
    "blockquote": {"cite"},
    "col": {"span", "width"},
    "colgroup": {"span", "width"},
    "img": {"align", "alt", "height", "src", "title", "width"},
    "ol": {"start", "type"},
    "q": {"cite"},
    "table": {"summary", "width"},
    "td": {"abbr", "axis", "colspan", "rowspan", "width"},
    "th": {"abbr", "axis", "colspan", "rowspan", "scope", "width"},
    "ul": {"type"},
}

# ── 백엔드가 relaxed 에 더한 것
#     .addAttributes(":all", "style", "data-block", "class")
#     .addTags("section")
#
# ★ data-slot 은 일부러 없다 (BlockValidator 주석: "모델이 만들어낼 수 있으면 안 된다").
#   백엔드 PR 이 수정 경로에만 이걸 허용하도록 바꾸는 중이다 — §슬롯 참고.
_ALL_ATTRS = {"style", "data-block", "class"}
_EXTRA_TAGS = {"section"}

ALLOWED_TAGS = _RELAXED_TAGS | _EXTRA_TAGS

# a[href] 에 허용된 프로토콜 — Safelist.relaxed() 기본값
_HREF_PROTOCOLS = ("ftp:", "http:", "https:", "mailto:")

# ★ 백엔드가 `.addProtocols("a", "href", "#")` 를 추가했다 (커밋 e6a41fd).
#   Jsoup 은 "#" 을 특수 프로토콜로 취급해서 앵커 링크를 통과시킨다.
#   v8 에서 CTA 링크가 통째로 죽던 버그가 이걸로 고쳐졌다.
#
#   ★ 다만 상대 경로는 여전히 죽는다 — baseUri 가 빈 문자열이라
#     `/events/1` `./next.html` `?page=2` 는 전부 제거된다.
#     이 설계에서는 문제가 안 된다: 정화는 **모델 출력에만** 걸고, 서버가
#     슬롯에 채우는 실제 URL 은 정화를 안 거친다. 프롬프트도 모델에게
#     'href="#" 는 그대로 둬라, 실제 주소를 만들어 넣지 마라' 고 못박는다.
#     즉 모델이 URL 을 지어내면 지워지는 게 **의도된 동작**이다.
_HREF_ANCHOR_OK = True

# style="..." 안에서 허용할 CSS 속성 (ALLOWED_CSS 이식)
ALLOWED_CSS = {
    "color", "background-color",
    "font-size", "font-weight", "font-style", "line-height",
    "text-align", "text-decoration",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "border", "border-color", "border-width", "border-style", "border-radius",
}

_PLACEHOLDER = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


# ── extract ───────────────────────────────────────────────────────
def extract(raw: str) -> str:
    """모델 출력에서 HTML 만 뽑는다. 코드펜스가 45% 확률로 붙어서 온다."""
    t = (raw or "").replace("```html", "").replace("```", "")
    s, e = t.find("<"), t.rfind(">")
    return t[s:e + 1].strip() if (s >= 0 and e > s) else ""


# ── 정화 ──────────────────────────────────────────────────────────
def _clean_style(style: str) -> str:
    """style="..." 안에서 허용 목록에 있는 선언만 남긴다"""
    out = []
    for decl in (style or "").split(";"):
        i = decl.find(":")
        if i < 0:
            continue
        prop = decl[:i].strip().lower()
        val = decl[i + 1:].strip()
        if not val or prop not in ALLOWED_CSS:
            continue
        low = val.lower()
        if any(x in low for x in ("url(", "expression(", "javascript:", "@import", "/*", "\\")):
            continue
        out.append(f"{prop}:{val}")
    return (";".join(out) + ";") if out else ""


def _href_survives(value: str) -> bool:
    """Jsoup 의 a[href] 프로토콜 검사 이식.

        href="#"            → 유지   ★ v9 에서 바뀐 것 (addProtocols 로 허용)
        href="https://..."  → 유지
        href="/events/1"    → 제거   (baseUri 가 "" 라 절대화 실패)
        href="./next.html"  → 제거
        href="?page=2"      → 제거
    """
    v = (value or "").strip()
    if _HREF_ANCHOR_OK and v.startswith("#"):
        return True
    return v.lower().startswith(_HREF_PROTOCOLS)


def sanitize_generated(html: str) -> str:
    """생성 결과 정화 — data-slot 을 **지운다**.

    빈 문서에서 만드는 것이라 슬롯이 있을 이유가 없다. 모델이 만들어내면
    서버의 쓰기 지점을 모델이 정하는 셈이 된다.
    """
    return _clean(html, keep_slots=False)


def sanitize_edited(html: str) -> str:
    """수정 결과 정화 — data-slot 을 **남긴다**.

    ★ 생성과 반대다. 원본에 이미 있던 슬롯을 보존해야 하기 때문이다.
      대신 모델이 지어낸 슬롯은 `validate_edited` 의 슬롯 대조가 잡는다.
      백엔드 주석 그대로 — "지우기와 대조하기 중 하나만 있으면 안 된다,
      둘이 한 쌍이다."

    ★ 그래서 **새 위험이 생겼다.** 정화가 슬롯을 통과시키므로 모델이 없던
      슬롯을 새로 만들어 넣을 수 있다. v8 에서는 정화가 무조건 지워서
      이 경우가 아예 존재할 수 없었다 — v9 가 처음 잴 수 있는 축이다.
    """
    return _clean(html, keep_slots=True)


def _clean(html: str, keep_slots: bool) -> str:
    """BlockValidator.clean(html, keepSlots) 이식.

    ★ 이 함수는 "모델이 준 조각" 에만 건다. 서버가 조립한 최종 문서에 걸면 안 된다.
      순서:  sanitize(모델 출력) → merge
    """
    soup = _soup(html)
    all_attrs = _ALL_ATTRS | ({"data-slot"} if keep_slots else set())

    # 1) 허용 안 된 태그는 벗겨낸다 (Jsoup 은 내용은 남기고 태그만 없앤다)
    for el in soup.find_all(True):
        if el.name not in ALLOWED_TAGS:
            el.unwrap()

    # 2) 속성 정리
    for el in soup.find_all(True):
        allowed = all_attrs | _RELAXED_ATTRS.get(el.name, set())
        for attr in list(el.attrs):
            if attr not in allowed:
                del el[attr]
                continue
            if el.name == "a" and attr == "href" and not _href_survives(el[attr]):
                del el[attr]

    # 3) Jsoup 은 style 속성이 "있는지"만 보고 "값"은 안 본다. 값은 여기서 거른다.
    for el in soup.select("[style]"):
        safe = _clean_style(el["style"])
        if safe:
            el["style"] = safe
        else:
            del el["style"]

    return str(soup)


# ── 검증 ──────────────────────────────────────────────────────────
def _check_shape(b: R.Block, el, fails: list):
    """블록 하나가 제 모양을 갖췄나. 생성·수정이 같은 규칙을 쓰게 하는 지점."""
    if b.must is None:
        return
    if el.select_one(b.must) is None:
        fails.append((f"empty_{b.key}", f"{b.key} 안에 {b.shape} — 맨 텍스트만 두면 안 됩니다."))
        return
    if b.min_items > 0:
        n = len(el.select(b.must))
        if n < b.min_items:
            fails.append((f"few_{b.key}",
                          f"{b.key} 항목이 {n}개입니다. {b.min_items}개 이상 필요합니다."))


def validate_generated(html: str) -> list:
    """생성 결과 검증 — 필수 블록이 다 있고 형태가 맞는가.

    ★ v8 에 있던 `check_slots` 인자를 없앴다. 정화를 2종으로 나눈 뒤로는
      생성 경로에 슬롯 검사 자체가 없으므로(백엔드 validateGenerated 와 동일)
      끄고 켤 것이 없다. C군이 누적 문서를 검사할 때도 그냥 이걸 쓰면 된다.
    """
    fails = []
    if not html or not html.strip():
        return [("no_html", "HTML을 찾을 수 없습니다. <section> 으로 시작하는 HTML만 출력하세요.")]

    soup = _soup(html)
    sections = soup.find_all("section")
    if not sections:
        fails.append(("no_section", "<section> 태그가 없습니다."))
    for sec in sections:
        if not sec.has_attr("data-block"):
            fails.append(("no_data_block",
                          '모든 <section> 에 data-block="이름" 속성이 있어야 합니다.'))
            break

    for b in R.llm_blocks():
        el = soup.select_one(b.selector())
        if el is None:
            if b.required:
                fails.append((f"lost_{b.key}", f"{b.key} 영역이 없습니다."))
            continue
        _check_shape(b, el, fails)

    for b in R.server_blocks():
        if soup.select_one(b.selector()) is not None:
            fails.append((f"wrote_{b.key}", f"{b.key} 영역은 만들면 안 됩니다. 서버가 채웁니다."))

    if _PLACEHOLDER.search(html):
        fails.append(("placeholder", "자리표시자가 남아 있습니다. 해당 문장을 빼세요."))

    # ★ 생성에는 슬롯 검사가 없다 — 백엔드 validateGenerated 와 같다.
    #   sanitizeGenerated() 가 이미 지우고 오므로 검사할 게 남지 않는다.
    #   (v8 에서는 여기에 slot_invented 를 뒀는데, 정화를 2종으로 나눈 뒤로는
    #    절대 발화하지 않는 죽은 검사가 된다)
    return fails


def validate_edited(target: R.Block, before: str, html: str) -> list:
    """수정 결과 검증 — 그 블록만 왔는가.

    ★ `before` 는 백엔드 PR 이 추가한 인자다. 슬롯이 없어졌는지는 원본을
      봐야 판정할 수 있다 (원본에 없던 슬롯을 "유실"로 잡으면 오탐).
    """
    fails = []
    soup = _soup(html)

    el = soup.select_one(target.selector())
    if el is None:
        return [(f"lost_{target.key}", f"{target.key} 영역이 없습니다.")]

    for b in R.BLOCKS:
        if b.key != target.key and soup.select_one(b.selector()) is not None:
            fails.append((f"extra_{b.key}",
                          f"{b.key} 영역은 만들지 마세요. 요청한 영역만 출력하세요."))

    _check_shape(target, el, fails)

    # 슬롯 — 수정에서는 원본에 있던 것을 지켜야 한다 (생성과 정반대)
    was, now = _slots_in(_soup(before)), _slots_in(soup)
    for key in sorted(was - now):
        fails.append((f"slot_lost_{key}",
                      f'data-slot="{key}" 이 없어졌습니다. 그대로 두세요.'))
    for key in sorted(now - was):
        fails.append((f"slot_invented_{key}",
                      f'data-slot="{key}" 을 새로 만들지 마세요.'))
    return fails


def _slots_in(soup) -> set:
    return {el["data-slot"] for el in soup.select("[data-slot]")}


# ── merge ─────────────────────────────────────────────────────────
def block_html(doc: str, target: R.Block) -> str:
    """누적 문서에서 그 블록만 꺼낸다 — 부분 재생성의 입력.

    전체 문서를 모델에 넘기지 않는 게 백엔드가 확정한 방식이다.
    """
    el = _soup(doc).select_one(target.selector())
    return str(el) if el is not None else ""


def merge(current_doc: str, target: R.Block, model_output: str) -> str:
    """모델이 뭘 돌려주든 그 블록 자리에만 끼워 넣는다."""
    cur = _soup(current_doc)
    out = _soup(model_output)

    incoming = out.select_one(target.selector())
    if incoming is None:
        return current_doc

    old = cur.select_one(target.selector())
    if old is None:
        cur.append(incoming)
    else:
        old.replace_with(incoming)
    return str(cur)


# ── 자체 검사 ─────────────────────────────────────────────────────
def self_check():
    R.self_check()

    # extract — 코드펜스 제거
    assert extract("```html\n<section data-block=\"cta\">x</section>\n```") \
        == '<section data-block="cta">x</section>'

    # ★ 회귀: 백엔드가 모델에게 시키는 형태(Block.shape)를 그대로 넣으면
    #   정화·검증을 통과해야 한다. (v4 에서 이걸 안 해서 결과를 통째로 버렸다)
    good = (
        '<section data-block="hero"><h1>여름 데이터</h1><p>소개</p></section>'
        '<section data-block="benefits"><ul><li>A</li><li>B</li></ul></section>'
        '<section data-block="steps"><ol><li>1</li><li>2</li></ol></section>'
        '<section data-block="cta"><a href="https://x.kr" class="btn">참여</a></section>'
    )
    assert not validate_generated(sanitize_generated(good)), \
        f"레지스트리 형태 그대로가 불합격: {validate_generated(sanitize_generated(good))}"

    # 정화 기본 동작 (두 경로 공통)
    for fn in (sanitize_generated, sanitize_edited):
        assert "<script>" not in fn('<section data-block="cta"><script>x</script></section>')
        assert 'class="btn"' in fn('<p class="btn">x</p>')
        assert "color:red" in fn('<p style="color:red">x</p>')
        assert "position" not in fn('<p style="position:fixed">x</p>')

    # ★ v8 의 href 버그가 고쳐졌다 — addProtocols("a","href","#") (커밋 e6a41fd)
    anchor = '<a href="#" class="btn">참여하기</a>'
    for fn in (sanitize_generated, sanitize_edited):
        assert 'href="#"' in fn(anchor), "앵커가 또 잘린다 — addProtocols 확인"
    assert 'href="https://x.kr"' in sanitize_edited('<a href="https://x.kr">x</a>')

    #   상대 경로는 여전히 죽는다 — 이 설계에서는 의도된 동작이다(위 주석)
    for href in ("/events/1", "./next.html", "?page=2"):
        assert "href" not in sanitize_edited(f'<a href="{href}">x</a>'), href

    # ★★ 정화 2종이 슬롯에서 **정반대**로 동작한다 — v9 의 핵심
    with_slot = ('<section data-block="hero"><h1>t</h1>'
                 '<span data-slot="period">기간</span></section>')
    assert "data-slot" not in sanitize_generated(with_slot), "생성은 슬롯을 지워야 한다"
    assert 'data-slot="period"' in sanitize_edited(with_slot), "수정은 슬롯을 남겨야 한다"

    # 생성 검증에는 슬롯 검사가 없다 (정화가 이미 지우므로)
    assert not [c for c, _ in validate_generated(sanitize_generated(with_slot))
                if c.startswith("slot_")]

    # 수정 검증 — 원본 대조로 유실·날조를 둘 다 잡는다
    without = '<section data-block="hero"><h1>t</h1></section>'
    codes = [c for c, _ in validate_edited(R.of("hero"), with_slot, without)]
    assert "slot_lost_period" in codes, codes

    #   ★ v9 가 처음 잴 수 있는 축 — 정화가 통과시키므로 날조가 가능해졌다
    codes = [c for c, _ in validate_edited(
        R.of("hero"), without, sanitize_edited(with_slot))]
    assert "slot_invented_period" in codes, codes

    assert not [c for c, _ in validate_edited(R.of("hero"), without, without)
                if c.startswith("slot_")], "원본에 없던 슬롯을 유실로 잡으면 오탐"

    # ★ 회귀 — 수정 경로에서 원본을 그대로 돌려주면 통과해야 한다.
    #   v8 에서는 정화가 슬롯·href 를 지워서 이게 **불가능**했다.
    for before in (with_slot, '<section data-block="cta">' + anchor + "</section>"):
        key = "hero" if "hero" in before else "cta"
        fails = [c for c, _ in validate_edited(
            R.of(key), before, sanitize_edited(before))]
        assert not fails, f"{key} 원본이 정화 후 불합격: {fails}"

    # merge
    doc = '<section data-block="cta">old</section>'
    assert "new" in merge(doc, R.of("cta"), '<section data-block="cta">new</section>')
    assert merge(doc, R.of("cta"), "<p>엉뚱한 출력</p>") == doc

    print("  [checks_v9] self_check 통과")


if __name__ == "__main__":
    self_check()
