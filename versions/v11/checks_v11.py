"""
checks_v11.py — 백엔드 `registry.BlockValidator` 미러
=====================================================

Java 쪽 extract / sanitize / validateGenerated / validateEdited / merge 를
옮긴 것이다.

★★ v1~v7 과 결정적으로 다른 점: **정화(sanitize) 뒤를 채점한다.**

    지금까지 벤치마크 :  raw → extract → check 
    현재 백엔드 :        raw → extract → sanitize → validate 

    이 차이가 실제 버그를 숨겼다. 모델이 `<a href="#">` 를 올바르게 냈는데
    정화가 href 를 지워버리고, 검증은 "`<a>` 가 있나"만 보니 통과한다.
    **모델 출력이 맞아도 제품은 깨진다.** 정화 전을 채점하면 이걸 영영 못 본다.

    그래서 v8 의 판정 순서는 서비스와 같다. `run_v11.py` 가 이 순서를 강제한다.

★ 정화는 Jsoup Safelist 를 파이썬으로 흉내 낸 것이다 — **의도적으로 버그까지
  같이 옮겼다.** 여기가 서비스보다 관대하면 v8 은 "통과했는데 실제로는 깨지는"
  모델을 고르게 된다. `self_check()` 가 그 동치성을 검사한다.
"""

import re

from bs4 import BeautifulSoup, NavigableString

import registry_v11 as R

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

# ── keepInteractive=true 일 때 더해지는 것 (수정 경로 전용)
#
#   ★ v9 와 달라진 점. v9 는 data-slot 하나만 더했는데, 실제 템플릿을
#     baseline 으로 쓰려면 그걸로 부족하다 — 25블록 중 11개가 깨졌다
#     (cta 는 전멸: button 태그·class·slot·data-demo-msg 가 통째로 사라짐).
#
#   `button`·`input` 을 태그로 받고, 호스트 JS 가 읽는 선언을 속성으로 받는다.
_INTERACTIVE_TAGS = {"button", "input"}
_INTERACTIVE_ATTRS = {
    "data-slot",       # 서버가 값을 쓰는 자리
    "id",              # getElementById 로 찾는 것들
    "type",            # <button type="button">
    "value", "placeholder",
    "data-href",       # <button> 일 때 서버가 넣는 링크
    "data-demo-msg",   # 클릭 반응 문구 — 나중에 data-behavior 로 바뀔 자리
    "data-state", "data-vote",
}

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


def _clean(html: str, keep_slots: bool) -> str:   # keep_slots = keepInteractive
    """BlockValidator.clean(html, keepSlots) 이식.

    ★ 이 함수는 "모델이 준 조각" 에만 건다. 서버가 조립한 최종 문서에 걸면 안 된다.
      순서:  sanitize(모델 출력) → merge
    """
    soup = _soup(html)
    all_attrs = _ALL_ATTRS | (_INTERACTIVE_ATTRS if keep_slots else set())
    tags = ALLOWED_TAGS | (_INTERACTIVE_TAGS if keep_slots else set())

    # 1) 허용 안 된 태그는 벗겨낸다 (Jsoup 은 내용은 남기고 태그만 없앤다)
    for el in soup.find_all(True):
        if el.name not in tags:
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

    before_soup = _soup(before)

    # 슬롯 — 수정에서는 원본에 있던 것을 지켜야 한다 (생성과 정반대)
    was, now = _slots_in(before_soup), _slots_in(soup)
    for key in sorted(was - now):
        fails.append((f"slot_lost_{key}",
                      f'data-slot="{key}" 이 없어졌습니다. 그대로 두세요.'))
    for key in sorted(now - was):
        fails.append((f"slot_invented_{key}",
                      f'data-slot="{key}" 을 새로 만들지 마세요.'))

    # ── v11 추가 ①  id 대조 — **백엔드엔 있는데 v10 에 없었다**
    #
    # ★ 2026-09-23 재채점에서 발견했다. 백엔드 `checkPreserved` 는
    #   `id_lost_` / `id_invented_` 를 내는데 v10 validate_edited 에는 없었다.
    #   미러가 반쪽이었던 것이다.
    #
    #   넣자마자 qwen D1 에서 `id_lost_pouchSection` 이 잡혔다 —
    #   getElementById 로 타이머를 찾는 요소라 없어지면 화면 기능이 죽는다.
    was_id, now_id = _ids_in(before_soup), _ids_in(soup)
    for key in sorted(was_id - now_id):
        fails.append((f"id_lost_{key}",
                      f'id="{key}" 가 없어졌습니다. 화면 기능이 이 id 로 요소를 찾습니다.'))
    for key in sorted(now_id - was_id):
        fails.append((f"id_invented_{key}",
                      f'id="{key}" 를 새로 만들지 마세요. 중복되면 첫 번째만 잡힙니다.'))
    #
    #   백엔드 `checkPreserved` 는 data-slot 과 id 만 대조한다. 그런데 정화는
    #   class·href 를 **통과시킨다** — 즉 "정화가 지울 때"는 고쳐졌지만
    #   "모델이 지울 때"는 아무도 안 잡는 반쪽 상태다.
    #
    #        정화가 지움      모델이 지움
    #   href   고쳐짐         못 잡음   ← must="a" 는 <a> 존재만 본다
    #   class  통과           못 잡음
    #
    #   class 는 템플릿에서 451건으로 압도적 1위이고 `class_lost` 는
    #   v4·v5·v7 에서 반복 확인된 주요 실패 유형이다. 여기서 먼저 재고
    #   결과를 백엔드에 넘긴다.

    # class — **유실만** 본다. 날조는 막지 않는다:
    #   혜택 항목을 하나 추가하면 그 항목의 클래스가 정당하게 늘어난다.
    #   슬롯·id 와 성격이 다른 지점이다(집합 비교, 개별 이름이 아님).
    lost_cls = _classes_in(before_soup) - _classes_in(soup)
    for c in sorted(lost_cls):
        fails.append((f"class_lost_{c}",
                      f'class="{c}" 를 지웠습니다. 디자인이 이 클래스에 걸려 있습니다.'))

    # href — 원본 <a> 의 href 값이 살아있는가
    lost_href = _hrefs_in(before_soup) - _hrefs_in(soup)
    for h in sorted(lost_href):
        fails.append(("href_lost",
                      f'href="{h}" 가 없어졌습니다. 기존 속성은 그대로 두세요.'))

    # ── v10 추가 ①  이름표 있는 요소의 class 가 바뀌었나 (백엔드 diffClasses 이식)
    was_map, now_map = class_map(before), class_map(html)
    for at, old in was_map.items():
        new = now_map.get(at)
        if new is None or new == old:
            continue          # 요소가 없어진 건 위 slot_lost/id_lost 가 잡는다
        fails.append((f"class_changed_{at}",
                      f'{at} 의 class 를 바꿨습니다. 원래대로 두세요: "{old}"'))

    # ── v10 추가 ②  호스트 JS 선언이 지워졌나
    #
    # ★ 항목을 **지우라고 시킨** 경우는 그 항목의 훅도 같이 사라지는 게 정상이다.
    #   실측으로 고친 것 — D2("마지막 하나를 삭제해줘")에서 버튼이 3→2 로 줄자
    #   훅 1개 유실이 실패로 찍혔다(gemma 30건 · haiku 14건). 시킨 대로 했는데
    #   실패한 것이다.
    #
    #   그래서 **항목이 준 개수만큼은 허용**하고, 그보다 더 사라진 것만 잡는다.
    lost_hooks = _behavior_hooks(before_soup) - _behavior_hooks(soup)
    removed_items = max(0, _item_count(before_soup) - _item_count(soup))
    if len(lost_hooks) > removed_items:
        for hook in sorted(lost_hooks)[removed_items:]:
            attr = hook.split("=", 1)[0]
            fails.append((f"hook_lost_{attr}",
                          f"{attr} 속성을 지웠습니다. 버튼 동작이 여기 걸려 있습니다."))
    return fails


# 반복 항목 — 템플릿마다 두 번째 클래스가 다르므로 공통 클래스로만 센다
_ITEM_SEL = ".benefit-card, .step-card"


def _item_count(soup) -> int:
    return len(soup.select(_ITEM_SEL))


def _slots_in(soup) -> set:
    return {el["data-slot"] for el in soup.select("[data-slot]")}


def _ids_in(soup) -> set:
    return {el["id"].strip() for el in soup.select("[id]") if el.get("id", "").strip()}


# 문구의 일부인 인라인 강조 — 여기 붙은 class 는 유실 검사에서 뺀다.
#
# ★ 실측으로 고친 것. template_5 hero 의 제목이 이렇게 생겼다:
#       <h1>... <span class="highlight">NewVent 2.0</span> ...</h1>
#   "제목을 '사전예약 마지막 기회' 로 바꿔줘" 는 제목을 **통째로** 갈라는
#   요청이라, 안쪽 강조가 사라지는 게 자연스럽다. 그런데 이걸 class_lost 로
#   잡으면 시킨 대로 한 모델이 3회 모두 실패로 찍힌다(gemma·haiku 각 12건).
#
#   디자인 계약은 **구조 요소**(div·section·ul·li·button)에 걸려 있다.
_INLINE_TAGS = {"span", "b", "em", "strong", "i", "small", "u", "mark", "sub", "sup"}


def _classes_in(soup, structural_only: bool = True) -> set:
    """클래스 이름 집합. structural_only 면 인라인 강조는 뺀다."""
    out = set()
    for el in soup.select("[class]"):
        if structural_only and el.name in _INLINE_TAGS:
            continue
        out.update(el.get("class") or [])
    return out


# ── v10 이 새로 보는 것 ───────────────────────────────────────────
#
# 백엔드 `Slots.classMap()` 은 **이름표가 있는 요소**(root · data-slot · id)의
# class 만 대조한다. 오탐이 없는 대신, 이름표 없는 반복 요소는 못 본다.
#
#   `.benefit-card` 는 id 도 data-slot 도 없다 → classMap 에 안 잡힌다.
#
# 그래서 v10 은 **집합 기반 유실 검사**를 같이 쓴다. 둘은 보완 관계다.

def class_map(html: str) -> dict:
    """백엔드 `Slots.classMap()` 이식 — 이름표 있는 요소의 class 만."""
    soup = _soup(html)
    out = {}
    root = soup.select_one("section[data-block]")
    if root is not None:
        out["root"] = " ".join(sorted(root.get("class") or []))
    for el in soup.select("[data-slot]"):
        k = (el.get("data-slot") or "").strip()
        if k:
            out[f"slot:{k}"] = " ".join(sorted(el.get("class") or []))
    for el in soup.select("[id]"):
        v = (el.get("id") or "").strip()
        if v:
            out[f"id:{v}"] = " ".join(sorted(el.get("class") or []))
    return out


def _behavior_hooks(soup) -> set:
    """호스트 JS 가 읽는 선언 — 지워지면 버튼은 남고 동작만 죽는다.

    `data-demo-msg` 는 백엔드가 아직 없어서 넣어둔 임시 자리표다
    (문구 끝에 "(데모)"). 나중에 `data-behavior` 로 바뀔 자리라,
    **모델이 지금 지워버리면 그 자리를 잃는다.**
    """
    out = set()
    for attr in ("data-demo-msg", "data-vote", "data-state", "data-href"):
        for el in soup.select(f"[{attr}]"):
            out.add(f"{attr}={el[attr][:40]}")
    return out


def _hrefs_in(soup) -> set:
    return {el["href"] for el in soup.select("a[href]")}


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

    # ★ class·href 보존 — 백엔드에 아직 없는 검사
    cta_before = '<section data-block="cta">' + anchor + "</section>"
    broke_cls = cta_before.replace(' class="btn"', "")
    codes = [c for c, _ in validate_edited(R.of("cta"), cta_before, broke_cls)]
    assert "class_lost_btn" in codes, codes

    broke_href = cta_before.replace(' href="#"', "")
    codes = [c for c, _ in validate_edited(R.of("cta"), cta_before, broke_href)]
    assert "href_lost" in codes, codes

    #   클래스가 늘어나는 건 정상이다 — 항목을 추가하면 자연히 늘어난다
    more_cls = cta_before.replace('class="btn"', 'class="btn btn-lg"')
    assert not [c for c, _ in validate_edited(R.of("cta"), cta_before, more_cls)
                if c.startswith("class_")], "클래스 추가를 막으면 항목 추가가 불가능해진다"

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

    print("  [checks_v11] self_check 통과")


if __name__ == "__main__":
    self_check()


# ── v10 추가 ③  기존 항목이 그대로인가 (결정 ④)
#
# ★ 처음엔 **낱말 단위**로 "원본·요청에 없던 낱말이 생겼나"를 봤다. 실측에서
#   오탐이 쏟아졌다(gemma 39건 · haiku 35건) — 템플릿 항목이 "제목 + 설명"
#   구조라, 제목만 주고 추가를 시키면 모델이 설명 문구를 쓴다.
#
#       "'영화 관람권 1매' 혜택을 추가해줘"
#         → 모델이 "추첨을 통해 드립니다" 같은 설명을 같이 씀
#         → 낱말 검사는 이걸 환각으로 잡는다. 그런데 정상 동작이다.
#
#   결정 ④("요청하지 않은 것을 추가하거나 내용을 바꾸면 안 된다")가 금지하는
#   것은 **항목이라는 실체**이지 설명 문구가 아니다. 개수는 expect_items 가
#   이미 보므로, 여기서는 **기존 항목이 살아있는가**만 본다.
#
# ★ Source.LLM 블록(steps)은 아예 안 본다 — 레지스트리가 "모델이 전부
#   만든다"고 정의했다. benefits 와 규칙이 다르다.

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_COMMON = {
    "이벤트", "혜택", "참여", "응모", "지급", "제공", "증정", "무료", "할인",
    "쿠폰", "당첨", "추첨", "기간", "대상", "안내", "확인", "신청", "선착순",
    "회원", "고객", "포인트", "적립", "사용", "가능", "이상", "최대", "한정",
}


def _tokens(text: str) -> set:
    return {t for t in _TOKEN.findall(text or "") if t not in _COMMON}


# 혜택의 **실체**를 나타내는 값 — 숫자가 붙은 토큰.
#   "10GB" "1매" "30%" "25만원" "1++" ... 문구를 다듬어도 이건 안 바뀌어야 한다.
_VALUE = re.compile(r"[0-9]+[0-9A-Za-z가-힣+%]*")


def _values_in(html: str) -> list:
    """항목별 수치 토큰. 순서를 유지해 삭제분을 셀 수 있게 한다."""
    return [set(_VALUE.findall(el.get_text(" ", strip=True)))
            for el in _soup(html).select(_ITEM_SEL)]


def check_items_preserved(before: str, after: str, block: str,
                          source: str = "") -> list:
    """기존 항목의 **수치**가 그대로인가.

    ★ 왜 수치인가
      문구를 다듬으라는 요청에 모델이 "10GB" 를 "20GB" 로 바꾸거나 "1매" 를
      빼먹으면 **관리자가 모르는 약속**이 나간다. 반대로 설명 문장을 고치는
      것은 정상 동작이라 건드리면 안 된다. 수치는 그 둘을 가르는 선이다.

    ★ 항목을 지우라고 시킨 만큼은 허용한다 (훅 검사와 같은 이유).
    """
    if source == "LLM":
        return []                      # 모델이 전부 만드는 블록 — 볼 것이 없다

    was, now = _values_in(before), _values_in(after)
    if not was:
        return []
    removed = max(0, len(was) - len(now))

    now_all = set().union(*now) if now else set()
    missing = []
    for i, vals in enumerate(was, 1):
        gone = vals - now_all
        if gone:
            missing.append((i, sorted(gone)))

    # 지운 항목 수만큼은 사라져도 정상
    fails = []
    for i, gone in missing[removed:]:
        fails.append((f"value_lost_{i}",
                      f"{i}번째 항목의 값 {', '.join(gone[:3])} 이(가) 사라졌거나 "
                      f"바뀌었습니다. 문구만 다듬고 값은 그대로 두세요."))
    return fails


# ── v11 추가 ②  문구를 바꾸라고 했는데 그대로인가 ────────────────────
#
# ★ 왜 필요한가 — v10 의 9케이스 중 **4개가 무변경으로 통과**했다.
#     D3 "더 짧고 간결하게"  P3 "더 힘있게"  H2 "더 매력적으로"  H3
#   원본을 그대로 돌려줘도 아무 검사에 안 걸렸다. 그 케이스의 ✓ 는
#   "잘했다" 가 아니라 **"안 부쉈다"** 는 뜻이었고, gemma 27/27 중
#   9칸이 실질적으로 빈 칸이었다.
#
#   이 검사 하나가 D3·P3·H2 셋을 동시에 고친다.
#
# ★ 공백만 다른 것은 같은 것으로 본다. 직렬화 차이로 실패하면 안 된다.
def _norm_text(html: str) -> str:
    return " ".join(_soup(html).get_text(" ", strip=True).split())


def check_text_changed(before: str, after: str) -> list:
    """문구 변경을 시킨 케이스 전용. 텍스트가 한 글자도 안 바뀌었으면 실패."""
    if _norm_text(before) == _norm_text(after):
        return [("text_unchanged",
                 "문구를 바꾸라고 했는데 원본과 똑같습니다. 실제로 고쳐서 다시 출력하세요.")]
    return []


# ── v11 추가 ③  값을 **바꿨는가** (지금까지 한 번도 안 잰 축) ─────────
#
# ★ v8~v10 은 전부 "구조를 부수는가" 만 쟀다. 정작 서비스 사고는 여기서 난다.
#
#     "혜택 문구를 더 매력적으로" → "데이터 10GB" 가 "데이터 20GB" 가 되면
#     관리자가 모르는 약속이 게시된다. 문구 오류가 아니라 **사고**다.
#
# ★ 백엔드에는 이 검사가 **아예 없다.** validateEdited 가 내는 코드는 전부
#   구조·이름표 검사다(lost_·empty_·few_·slot_·id_·class_changed_).
#   `PromptBuilder` 주석이 "프롬프트·되묻기·폼 값 대조 세 겹" 이라 적어놨고
#   폼 값 대조(REQ-LLM-41)는 **이름만 있고 구현이 없다.** 이게 그 프로토타입이다.
#
# ★ check_items_preserved(유실) 와 다르다
#     유실  값이 **없어졌나**       — 항목 단위로 본다
#     변조  값이 **다른 게 됐나**   — 문서 전체 수치 집합을 본다
#   "10GB → 20GB" 는 유실 검사도 잡지만, 항목 순서가 바뀌거나 항목이
#   합쳐지면 유실 검사는 놓친다. 집합으로 한 번 더 본다.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(html: str) -> list:
    """텍스트에 나온 수치 토큰. 순서 유지(중복도 의미가 있다)."""
    return [m.group().replace(",", "") for m in _NUM.finditer(_norm_text(html))]


def check_values_intact(before: str, after: str, allow_new: bool = False) -> list:
    """원본 수치가 **바뀌지 않았나**.

    Args:
        allow_new: 항목을 더하는 요청이면 새 수치가 느는 게 정상이다.
                   그때도 **원본 수치가 사라지는 것**은 여전히 실패다.
    """
    was, now = _numbers_in(before), _numbers_in(after)
    if not was:
        return []

    fails, pool = [], list(now)
    missing = []
    for v in was:
        if v in pool:
            pool.remove(v)
        else:
            missing.append(v)
    if missing:
        fails.append(("value_changed",
                      f"원본 수치 {', '.join(sorted(set(missing))[:4])} 이(가) "
                      f"사라지거나 다른 값이 됐습니다. 숫자는 그대로 두세요."))
    if not allow_new and pool:
        fails.append(("value_added",
                      f"없던 수치 {', '.join(sorted(set(pool))[:4])} 이(가) 생겼습니다. "
                      f"주어지지 않은 수치를 만들지 마세요."))
    return fails
