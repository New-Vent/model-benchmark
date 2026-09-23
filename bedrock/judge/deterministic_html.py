"""
deterministic_html.py — HTML 방식의 Code 기반(Deterministic) 평가
====================================================================
`docs/architect/project-architect.md (HTML 파트)` §19~§27, `docs/bedrock/v2-pipeline.md` §18·§23·§24
의 "Deterministic Validator" 를 구현한다.

★ 정확성 근거 — 어디서 베꼈는지 숨기지 않는다
    이 파일의 Block/Slot 정의와 fail 코드(no_html, lost_hero, extra_cta,
    slot_lost_*, slot_invented_* ...)는 문서의 추상적인 설명이 아니라
    **실제로 배포된 코드**에서 그대로 옮긴 것이다.

        newvent-backend/src/main/java/com/newvent/registry/Block.java
        newvent-backend/src/main/java/com/newvent/registry/Slot.java
        newvent-backend/src/main/java/com/newvent/registry/BlockValidator.java

    이미 한 번 이식된 적이 있다 — model-benchmark/versions/v8/registry_v8.py,
    checks_v8.py. 이 파일은 그 이식을 **다시 베낀 것**이지 가져다 쓴(import) 것이
    아니다. `versions/v8`은 버전이 고정된 폴더(성적표가 이미 나온 실험)라
    합의 없이 새 스크립트가 거기 얹혀살면 안 되고, bedrock/ 은 "독립적인
    judge 스크립트"로 요청받았기 때문에 자체 사본을 둔다.

    ⚠ Block.java 가 바뀌면 이 파일도 사람이 손으로 맞춰야 한다 — v8과
      동일한 한계이고, 자동으로 감지되지 않는다(각 self_check()가 서로를
      보증하지 않는다).

★ 실제로 구현되어 있지 않은 것 — 정직하게 표시한다
    `project-architect.md (HTML 파트)` §7~§12, §27 이 설명하는 data-behavior
    검증(`BehaviorValidator`)은 **newvent-backend에 클래스 자체가 없다**
    (2026-09-22 기준, com.newvent 패키지 전체를 뒤져도 없음). 아래
    `validate_behavior()`는 문서의 규칙(allowlist)만 근거로 새로 작성한
    것이며, 대조할 실제 구현이 없다는 뜻이다. `BEHAVIOR_IMPLEMENTED_IN_BACKEND
    = False` 로 이 사실을 코드에도 남긴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════
#  Block / Slot 레지스트리 — Block.java + Slot.java 미러
# ══════════════════════════════════════════════════════════════════

LLM, SERVER, MIXED = "LLM", "SERVER", "MIXED"


@dataclass(frozen=True)
class Block:
    key: str
    required: bool
    source: str
    desc: str
    shape: str | None
    must: str | None
    min_items: int

    def selector(self) -> str:
        return f'[data-block="{self.key}"]'


BLOCKS = [
    Block("hero", True, MIXED,
          "이벤트 제목과 한 줄 소개. 기간은 서버가 넣는다",
          "제목은 <h1>, 소개는 <p> 로 감싼다", "h1", 0),
    Block("benefits", True, MIXED,
          "혜택 — 항목은 폼 값, 문장만 다듬는다",
          "<ul> 안에 <li> 로 항목을 나열한다. 2개 이상", "ul li", 2),
    Block("steps", False, LLM,
          "참여 방법 2~4단계",
          "<ol> 안에 <li> 로 순서대로 나열한다", "ol li", 2),
    Block("notices", True, SERVER,
          "유의사항 — 승인된 문구만 서버가 삽입", None, None, 0),
    Block("cta", True, MIXED,
          "참여 버튼. 문구만 생성, 링크는 폼 값",
          '<a href="#" class="btn"> 안에 버튼 문구를 넣는다', "a", 0),
]
BY_KEY = {b.key: b for b in BLOCKS}
LLM_BLOCKS = [b for b in BLOCKS if b.source != SERVER]
SERVER_BLOCKS = [b for b in BLOCKS if b.source == SERVER]

SLOT_KEYS = {"period", "cta-link"}

_PLACEHOLDER = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")


def block_of(key: str) -> Block:
    if key not in BY_KEY:
        raise ValueError(f"없는 블록: {key}")
    return BY_KEY[key]


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _slots_in(soup: BeautifulSoup) -> set:
    return {el["data-slot"] for el in soup.select("[data-slot]")}


# ══════════════════════════════════════════════════════════════════
#  extract — BlockValidator.extract() 미러
# ══════════════════════════════════════════════════════════════════

def extract(raw: str) -> str:
    """모델 출력에서 HTML만 뽑는다. 코드펜스가 섞여 와도 걷어낸다."""
    t = (raw or "").replace("```html", "").replace("```", "")
    s, e = t.find("<"), t.rfind(">")
    return t[s:e + 1].strip() if (s >= 0 and e > s) else ""


# ══════════════════════════════════════════════════════════════════
#  soft/hard 실패 구분 — base/checks.py의 SOFT_FAILS·base/engine.py의
#  hard_ok/all_ok 관례를 그대로 옮긴다.
#
#  ★ 왜 필요한가 — extract()가 이미 코드펜스를 걷어내므로 `BlockValidator`
#    (실제 백엔드)는 raw 자체는 보지 않고 추출된 결과만 본다. 즉 code_fence·
#    extra_text는 **백엔드 계약 위반이 아니다**(서버가 알아서 지운다).
#    그런데도 base/checks.py가 이걸 굳이 SOFT_FAILS로 잡아온 이유는, 이게
#    "결과가 맞았나"가 아니라 "모델이 지시를 얼마나 깔끔하게 따르는가"를
#    보여주는 신호이기 때문이다 — 코드펜스를 매번 감싸는 모델은 정답률이
#    같아도 신뢰도가 낮다. bedrock/의 목적도 모델 비교이므로 이 신호를 버리지
#    않는다. 단, **이 분류는 고정된 규칙(SOFT_FAILS 집합)이지 LLM Judge의
#    판단이 아니다** — `docs/bedrock/v2-pipeline.md` §36.3("Judge에게 구조
#    검증을 전부 맡기지 않는다")과 같은 이유로, 이런 형식적 사실은 코드가
#    결정하고 Judge는 의미 판단만 한다.
#
#  ★ base/checks.py의 SOFT_FAILS = {"code_fence","extra_text","excess_ops_review"}
#    중 excess_ops_review는 옮기지 않는다 — 그건 v1~v8의 K군(ops 배열에
#    여러 오퍼레이션을 담는 JSON 패치) 전용 개념이고, 이 프로젝트가 따르는
#    project-architect.md (JSON 파트)의 Modification Command는 명령 하나에 오퍼레이션도
#    하나뿐이라 애초에 "오퍼레이션 개수 과다"라는 상황 자체가 없다.
FENCE = re.compile(r"```")
SOFT_FAILS = {"code_fence", "extra_text"}


def format_fails(raw: str, extracted: str) -> list:
    """raw(모델이 실제로 낸 원문)와 extracted(코드펜스·군더더기를 걷어낸
    결과)를 비교해서 형식적 결함을 잡는다. base/checks.py의 check_html()
    앞부분과 동일한 판정 기준(길이 차 40자)을 쓴다."""
    fails = []
    if len(raw.strip()) - len(extracted) > 40:
        fails.append("extra_text")
    if FENCE.search(raw or ""):
        fails.append("code_fence")
    return fails


def split_fails(fails: list) -> tuple:
    """(hard, soft) — base/engine.py의 hard/soft 분리와 동일하다."""
    hard = [f for f in fails if f not in SOFT_FAILS]
    soft = [f for f in fails if f in SOFT_FAILS]
    return hard, soft


# ══════════════════════════════════════════════════════════════════
#  sanitize — BlockValidator.sanitizeGenerated/sanitizeEdited 미러
#  (Jsoup Safelist.relaxed() + addAttributes(style,data-block,class)
#   + addTags(section) 를 BeautifulSoup으로 흉내)
# ══════════════════════════════════════════════════════════════════

_RELAXED_TAGS = {
    "a", "b", "blockquote", "br", "caption", "cite", "code", "col", "colgroup",
    "dd", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "i",
    "img", "li", "ol", "p", "pre", "q", "small", "span", "strike", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
_RELAXED_ATTRS = {
    "a": {"href"}, "blockquote": {"cite"}, "col": {"span", "width"},
    "colgroup": {"span", "width"},
    "img": {"align", "alt", "height", "src", "title", "width"},
    "ol": {"start", "type"}, "q": {"cite"}, "table": {"summary", "width"},
    "td": {"abbr", "axis", "colspan", "rowspan", "width"},
    "th": {"abbr", "axis", "colspan", "rowspan", "scope", "width"},
    "ul": {"type"},
}
ALLOWED_TAGS = _RELAXED_TAGS | {"section"}
_ALL_ATTRS = {"style", "data-block", "class"}
_HREF_PROTOCOLS = ("ftp:", "http:", "https:", "mailto:")
ALLOWED_CSS = {
    "color", "background-color",
    "font-size", "font-weight", "font-style", "line-height",
    "text-align", "text-decoration",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "border", "border-color", "border-width", "border-style", "border-radius",
}


def _clean_style(style: str) -> str:
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
    """Jsoup의 baseUri="" 버그를 그대로 미러 — 상대경로 href는 전부 죽는다.
    (versions/v8/checks_v8.py의 문서화된 회귀, newvent-backend 실측)"""
    return (value or "").lower().startswith(_HREF_PROTOCOLS)


def sanitize(html: str, keep_slots: bool) -> str:
    """모델이 낸 조각 하나에만 건다. 최종 조립 문서에 걸면 안 된다."""
    soup = _soup(html)
    for el in soup.find_all(True):
        if el.name not in ALLOWED_TAGS:
            el.unwrap()
    allowed_all = set(_ALL_ATTRS) | ({"data-slot"} if keep_slots else set())
    for el in soup.find_all(True):
        allowed = allowed_all | _RELAXED_ATTRS.get(el.name, set())
        for attr in list(el.attrs):
            if attr not in allowed:
                del el[attr]
                continue
            if el.name == "a" and attr == "href" and not _href_survives(el[attr]):
                del el[attr]
    for el in soup.select("[style]"):
        safe = _clean_style(el["style"])
        if safe:
            el["style"] = safe
        else:
            del el["style"]
    return str(soup)


# ══════════════════════════════════════════════════════════════════
#  validate — BlockValidator.validateGenerated/validateEdited 미러
# ══════════════════════════════════════════════════════════════════

def _check_shape(b: Block, el, fails: list):
    if b.must is None:
        return
    if el.select_one(b.must) is None:
        fails.append(f"empty_{b.key}")
        return
    if b.min_items > 0:
        n = len(el.select(b.must))
        if n < b.min_items:
            fails.append(f"few_{b.key}")


def validate_generated(html: str, check_slots: bool = True, omit_ok: frozenset = frozenset()) -> list:
    """omit_ok — 이번 요청에서 애초에 내용을 안 준 블록의 키 집합(예: {"benefits"}).

    `Block.required`는 Block.java를 그대로 미러링한 **전역** 규칙이라 여기서
    건드리면 안 된다(파일 상단 ★ 참고) — 실제로는 "혜택 내용을 아직 안 정했다"는
    요청도 있는데(TC-GEN-005), 그럴 때 모델이 지어내지 않고 블록 자체를 생략하는
    건 결함이 아니라 정확히 바라는 동작이다("환각 방어"). 그런데도 `lost_benefits`가
    떴던 건 이 함수가 "혜택을 요청했는데 없다"와 "애초에 혜택을 안 줬다"를
    구분하지 못했기 때문 — 실측(bedrock/results)에서 TC-GEN-005가 gemma·haiku·
    oss120·qwen **4개 모델 전부**에서 같은 이유로 걸렸다. 한 케이스에서 전 모델이
    동시에 죽으면 모델 탓이 아니라 채점 로직 탓이라는 신호다(v10 README가 이미
    확인한 패턴). 그래서 전역 규칙은 그대로 두고, **호출자가 이번 요청에 그
    내용이 있었는지를 알려주는 optional 인자**로 좁혀서 고친다 — 기본값이
    빈 집합이라 기존 호출부는 전부 그대로 엄격하게 동작한다.
    """
    fails = []
    if not html or not html.strip():
        return ["no_html"]
    soup = _soup(html)
    sections = soup.find_all("section")
    if not sections:
        fails.append("no_section")
    for sec in sections:
        if not sec.has_attr("data-block"):
            fails.append("no_data_block")
            break
    for b in LLM_BLOCKS:
        el = soup.select_one(b.selector())
        if el is None:
            if b.required and b.key not in omit_ok:
                fails.append(f"lost_{b.key}")
            continue
        _check_shape(b, el, fails)
    for b in SERVER_BLOCKS:
        if soup.select_one(b.selector()) is not None:
            fails.append(f"wrote_{b.key}")
    if _PLACEHOLDER.search(html):
        fails.append("placeholder")
    if check_slots:
        for key in sorted(_slots_in(soup)):
            fails.append(f"slot_invented_{key}")
    return fails


def validate_edited(target_key: str, before: str, html: str) -> list:
    target = block_of(target_key)
    fails = []
    soup = _soup(html)
    el = soup.select_one(target.selector())
    if el is None:
        return [f"lost_{target.key}"]
    for b in BLOCKS:
        if b.key != target.key and soup.select_one(b.selector()) is not None:
            fails.append(f"extra_{b.key}")
    _check_shape(target, el, fails)
    was, now = _slots_in(_soup(before)), _slots_in(soup)
    for key in sorted(was - now):
        fails.append(f"slot_lost_{key}")
    for key in sorted(now - was):
        fails.append(f"slot_invented_{key}")
    return fails


# ══════════════════════════════════════════════════════════════════
#  data-behavior — project-architect.md (HTML 파트) §7~§12, §27
#  ⚠ 백엔드에 BehaviorValidator.java 가 없다. 문서 규칙만으로 새로 작성한
#    것이라 실제 구현과의 일치 여부를 대조할 수 없다 — 결과 리포트에
#    반드시 "spec-only" 로 표시한다 (run_judge.py 참고).
# ══════════════════════════════════════════════════════════════════

BEHAVIOR_IMPLEMENTED_IN_BACKEND = False

ALLOWED_ACTIONS = {"open-modal", "close-modal", "scroll", "show", "hide",
                    "api-request", "redirect"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
# doc §12의 유일한 실제 예시가 "/api/coupons/issue" — 프로젝트 전용 API만
# 허용한다는 원칙(§12 "필요한 API만 Allowlist로 관리")을 그대로 좁게 적용.
ALLOWED_ENDPOINT_PREFIXES = ("/api/",)
DENIED_URL_SCHEMES = ("javascript:", "data:")


def validate_behavior(behavior_json: str) -> list:
    """<button data-behavior='...'> 안의 JSON 하나를 검증한다.

    반환 fail 코드: bad_behavior_json, unknown_event, missing_action_or_actions,
    unknown_action_<x>, missing_target_<x>, unknown_method_<x>,
    disallowed_endpoint_<x>, external_url_<x>
    """
    fails = []
    try:
        b = json.loads(behavior_json)
    except Exception:
        return ["bad_behavior_json"]
    if not isinstance(b, dict):
        return ["bad_behavior_json"]

    if b.get("event") not in ("click", "change", "submit"):
        fails.append("unknown_event")

    actions = b.get("actions")
    if actions is None:
        actions = [{"type": b.get("action"), "target": b.get("target")}] \
            if b.get("action") else None
    if not actions or not isinstance(actions, list):
        return fails + ["missing_action_or_actions"]

    for a in actions:
        if not isinstance(a, dict):
            fails.append("bad_behavior_json")
            continue
        kind = a.get("type") or a.get("action")
        if kind not in ALLOWED_ACTIONS:
            fails.append(f"unknown_action_{kind}")
            continue
        if kind == "api-request":
            method = a.get("method")
            if method not in ALLOWED_METHODS:
                fails.append(f"unknown_method_{method}")
            endpoint = a.get("endpoint", "")
            if not any(endpoint.startswith(p) for p in ALLOWED_ENDPOINT_PREFIXES):
                fails.append(f"disallowed_endpoint_{endpoint}")
        elif kind == "redirect":
            url = a.get("url") or a.get("target") or ""
            low = url.lower()
            if low.startswith(DENIED_URL_SCHEMES) or low.startswith(("http://", "https://")):
                fails.append(f"external_url_{url}")
        else:
            if not a.get("target"):
                fails.append(f"missing_target_{kind}")
    return fails


def behaviors_in(html: str) -> list:
    """이 조각 안의 모든 data-behavior 원문 문자열을 순서대로 뽑는다."""
    soup = _soup(html)
    return [el["data-behavior"] for el in soup.select("[data-behavior]")]


# ══════════════════════════════════════════════════════════════════
#  자체 검사 — 프로젝트 전체 관례(self_check)를 그대로 따른다
# ══════════════════════════════════════════════════════════════════

def self_check():
    assert [b.key for b in BLOCKS] == ["hero", "benefits", "steps", "notices", "cta"]
    assert [b.key for b in LLM_BLOCKS] == ["hero", "benefits", "steps", "cta"]
    assert [b.key for b in SERVER_BLOCKS] == ["notices"]

    assert extract("```html\n<section data-block=\"cta\">x</section>\n```") \
        == '<section data-block="cta">x</section>'

    good = (
        '<section data-block="hero"><h1>여름 데이터</h1><p>소개</p></section>'
        '<section data-block="benefits"><ul><li>A</li><li>B</li></ul></section>'
        '<section data-block="steps"><ol><li>1</li><li>2</li></ol></section>'
        '<section data-block="cta"><a href="https://x.kr" class="btn">참여</a></section>'
    )
    assert not validate_generated(sanitize(good, keep_slots=False)), \
        validate_generated(sanitize(good, keep_slots=False))

    # 서버 소유 블록을 모델이 만들면 wrote_notices
    bad = good + '<section data-block="notices">내가 만든 유의사항</section>'
    assert "wrote_notices" in validate_generated(bad)

    # 필수 블록 유실
    assert "lost_hero" in validate_generated(
        '<section data-block="cta"><a>참여</a></section>')

    # placeholder
    assert "placeholder" in validate_generated(good.replace("여름 데이터", "[제목]"))

    # omit_ok — 혜택 정보를 애초에 안 준 요청에서는 benefits 생략을 실패로
    # 잡지 않는다 (TC-GEN-005 회귀: 4모델 전부가 이 이유만으로 오탐됐음)
    skeleton = (
        '<section data-block="hero"><h1>겨울 이벤트</h1></section>'
        '<section data-block="cta"><a href="#" class="btn">참여하기</a></section>'
    )
    assert "lost_benefits" in validate_generated(skeleton)
    assert "lost_benefits" not in validate_generated(skeleton, omit_ok={"benefits"})
    # omit_ok에 없는 다른 필수 블록(hero)은 여전히 잡는다 — 조건을 통째로
    # 끄는 게 아니라 지정된 키만 좁혀서 면제한다는 것을 확인
    cta_only = '<section data-block="cta"><a href="#" class="btn">참여하기</a></section>'
    assert "lost_hero" in validate_generated(cta_only, omit_ok={"benefits"})

    # 슬롯 — 생성은 금지, 수정은 보존 (정반대)
    with_slot = '<section data-block="hero"><h1>t</h1><span data-slot="period">기간</span></section>'
    assert "slot_invented_period" in validate_generated(with_slot)
    without = '<section data-block="hero"><h1>t</h1></section>'
    assert "slot_lost_period" in validate_edited("hero", with_slot, without)
    assert not [f for f in validate_edited("hero", without, without) if f.startswith("slot_")]

    # extra_<key> — 수정에서 요청 안 한 블록을 더 만듦
    assert "extra_cta" in validate_edited(
        "hero", "<section data-block=\"hero\"><h1>t</h1></section>",
        '<section data-block="hero"><h1>t</h1></section>'
        '<section data-block="cta"><a>x</a></section>')

    # sanitize 회귀 — Jsoup baseUri="" 버그(상대경로 href 소실)를 그대로 미러하는가
    anchor = '<a href="#" class="btn">참여하기</a>'
    cleaned = sanitize(anchor, keep_slots=False)
    assert 'href="#"' not in cleaned and "<a" in cleaned
    for href in ("#", "/events/1", "./next.html", "?page=2"):
        assert "href" not in sanitize(f'<a href="{href}">x</a>', keep_slots=False), href
    assert 'href="https://x.kr"' in sanitize('<a href="https://x.kr">x</a>', keep_slots=False)
    assert "data-slot" not in sanitize(with_slot, keep_slots=False)
    assert 'data-slot="period"' in sanitize(with_slot, keep_slots=True)

    # behavior — 허용 목록
    ok_behavior = json.dumps({"event": "click", "action": "open-modal", "target": "m"})
    assert not validate_behavior(ok_behavior)
    bad_action = json.dumps({"event": "click", "action": "execute-script", "target": "m"})
    assert "unknown_action_execute-script" in validate_behavior(bad_action)
    bad_endpoint = json.dumps({"event": "click", "actions": [
        {"type": "api-request", "method": "POST", "endpoint": "https://evil.example.com"}]})
    assert any(f.startswith("disallowed_endpoint_") for f in validate_behavior(bad_endpoint))
    good_endpoint = json.dumps({"event": "click", "actions": [
        {"type": "api-request", "method": "POST", "endpoint": "/api/coupons/issue"},
        {"type": "show-modal" if False else "show", "target": "coupon-success-modal"},
    ]})
    # "show-modal" 은 허용 목록에 없다(§11의 실제 목록은 show/hide) — 문서 §21 예시의
    # "type":"show-modal" 은 §11의 action 목록과 표기가 어긋난다(문서 자체의 불일치).
    # 여기서는 §11의 명시적 allowlist를 기준으로 삼는다.
    assert not validate_behavior(good_endpoint)

    # soft/hard 구분 — code_fence·extra_text는 soft, 구조 실패는 hard
    raw_with_fence = "```html\n" + good + "\n```"
    ff = format_fails(raw_with_fence, extract(raw_with_fence))
    assert "code_fence" in ff, ff
    hard, soft = split_fails(ff)
    assert soft == ["code_fence"] and hard == []

    raw_with_chatter = (
        "안녕하세요! 요청하신 이벤트 페이지를 아래와 같이 정성껏 만들어 드렸습니다. "
        "확인 부탁드립니다.\n\n" + good
    )
    ff2 = format_fails(raw_with_chatter, extract(raw_with_chatter))
    assert "extra_text" in ff2, ff2

    mixed = ["lost_hero", "code_fence", "empty_cta"]
    hard, soft = split_fails(mixed)
    assert hard == ["lost_hero", "empty_cta"] and soft == ["code_fence"]

    print("  [deterministic_html] self_check 통과")


if __name__ == "__main__":
    self_check()
