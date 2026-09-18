"""
checks_v4.py — v4 채점기 (추가분, base/checks.py는 건드리지 않음)
==================================================================
`base/checks.py`의 `check_html` · `check_plan`은 **그대로 둡니다.**
v1·v2·v3은 영향을 받지 않고 지금까지의 결과도 재현됩니다.

이 파일은 v4가 새로 요구하는 것만 얹습니다.

    1) 최종 HTML 기준 통일 채점   S와 J를 같은 자로 잰다
    2) 제품 규격 보존 검사 5종     AI_EDIT_RULES.md §3 을 검사로 옮긴 것
    3) 텍스트 필드 태그 주입 검사   check_plan 에 없어서 새던 구멍
    4) 공통/전용 실패 분리         검사 항목 수 차이가 점수를 왜곡하지 않게

왜 최종 HTML로 통일하는가
    S :  LLM ─────────────────────→ HTML  ┐
                                           ├→ 같은 검사기 → 비교 성립
    J :  LLM → plan → render_plan() → HTML ┘

    지금은 S를 check_html로, J를 check_plan으로 채점한 점수를 나란히
    놓고 있다. 실패 이름도 검사 항목도 달라서 "S 100% vs J 77%"는
    같은 것을 잰 숫자가 아니다.

두는 위치
    run.py 가 버전 폴더를 sys.path 에 넣고 `cases_*.py` 만 글롭하므로,
    이 파일은 versions/v4/cases_*.py 에서 `import checks_v4` 로 쓸 수
    있고 케이스 모듈로 오인되지도 않는다. base/ 를 건드리지 않는 자리다.

    팀 합의 후 v5부터 표준으로 쓸 거라면 그때 base/ 로 옮긴다.
"""

import json
import re

from bs4 import BeautifulSoup

import checks as base_checks
from registry import BY_KEY, SERVER, render_plan


# ══════════════════════════════════════════════════════════════
#  계약 상수
# ══════════════════════════════════════════════════════════════

# AI_EDIT_RULES.md §3 "디자인 필수 클래스 불변 유지".
# 신규 생성처럼 baseline 이 없을 때 쓰는 최소 계약.
# 수정(baseline 있음)일 때는 baseline 에서 실제 클래스를 뽑아 쓰므로
# 이 표에 없는 테마별 클래스(sp-*, hol-* 등)도 자동으로 보호된다.
CONTRACT_CLASSES = {
    "hero":     {"ev-block", "block-hero"},
    "benefits": {"ev-block", "block-benefits"},
    "steps":    {"ev-block", "block-steps"},
    "notices":  {"ev-block", "block-notices"},
    "cta":      {"ev-block", "block-cta"},
}

# AI_EDIT_RULES.md §3 이 명시적으로 허용한 인라인 태그.
# 이 둘 말고 텍스트 필드에 태그가 섞이면 tag_in_field_* 로 잡는다.
ALLOWED_INLINE = {"br", "span"}

TAG_IN_TEXT = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
THEME_CLASS = re.compile(r"^theme-")

# 비교에 쓰는 실패 — S와 J 양쪽에서 같은 의미로 나올 수 있는 것만.
# J 전용(no_json·unknown_variant 등)은 J 내부 진단용이고 비교에서 뺀다.
COMMON_PREFIXES = (
    "lost_", "extra_", "wrote_", "empty_", "few_",
    "bad_tag_", "full_doc_",
)
COMMON_EXACT = {
    "code_fence", "extra_text", "placeholder",
    "no_section", "no_data_block", "unparseable_html",
    "class_lost", "data_block_changed", "inline_style",
    "theme_leaked", "nested_section",
}


def is_common(fail: str) -> bool:
    """S↔J 비교에 쓰는 실패인가."""
    return fail in COMMON_EXACT or fail.startswith(COMMON_PREFIXES)


def split_fails(fails: list) -> tuple:
    """(공통, 전용) 으로 가른다. 비교는 공통만 쓴다."""
    common = [f for f in fails if is_common(f)]
    only = [f for f in fails if not is_common(f)]
    return common, only


# ══════════════════════════════════════════════════════════════
#  1. 제품 규격 보존 검사 5종  (AI_EDIT_RULES.md §3)
# ══════════════════════════════════════════════════════════════

def _soup(html):
    try:
        return BeautifulSoup(html, "html.parser")
    except Exception:
        return None


def _classes_of(el) -> set:
    return set(el.get("class", []) or [])


def check_product_rules(html: str, block: str = "", baseline_html: str = "") -> tuple:
    """제품 마크업 계약을 지켰는가.

    baseline_html 을 주면 "거기 있던 클래스가 출력에도 있는가"로 검사한다
    (수정 흐름). 안 주면 CONTRACT_CLASSES 의 최소 집합으로 검사한다
    (신규 생성 흐름).

    반환: (fails, notes)
    """
    fails, notes = [], []
    soup = _soup(html)
    if soup is None:
        return ["unparseable_html"], "HTML을 파싱할 수 없습니다."

    sections = soup.find_all("section")

    # ── nested_section : section 안에 section
    #    AI_EDIT_RULES §2-1 "innerHTML 만 반환하면 중첩 section 이 생긴다"
    for sec in sections:
        if sec.find("section"):
            fails.append("nested_section")
            notes.append("<section> 안에 <section> 이 있습니다. "
                         "교체 대상 section 전체(outerHTML)만 출력하세요.")
            break

    # ── inline_style : 인라인 CSS 주입
    #    AI_EDIT_RULES §1-2 "LLM 은 인라인 CSS 나 미디어쿼리를 주입하지 않는다"
    if soup.find(attrs={"style": True}):
        fails.append("inline_style")
        notes.append('style="..." 를 넣지 마세요. 색·여백은 event.css 가 담당합니다.')

    # ── theme_leaked : theme-* 를 블록 안으로 복사
    #    AI_EDIT_RULES §3 "테마는 바깥 컨테이너가 관리한다"
    for el in soup.find_all(class_=True):
        if any(THEME_CLASS.match(c) for c in _classes_of(el)):
            fails.append("theme_leaked")
            notes.append("theme-* 클래스는 블록 안에 넣지 마세요. "
                         "부모의 CSS 변수를 상속받습니다.")
            break

    # ── data_block_changed : data-block 값이 바뀌거나 사라짐
    if block:
        target = soup.select_one(f'[data-block="{block}"]')
        if target is None:
            fails.append("data_block_changed")
            notes.append(f'data-block="{block}" 이 사라졌거나 값이 바뀌었습니다. '
                         f"이 속성은 그대로 두세요.")

    # ── class_lost : 필수/원본 클래스 유실
    want = set()
    if baseline_html:
        base_soup = _soup(baseline_html)
        if base_soup is not None:
            src = (base_soup.select_one(f'[data-block="{block}"]') if block
                   else base_soup)
            if src is not None:
                for el in src.find_all(class_=True):
                    want |= _classes_of(el)
                want |= _classes_of(src)
    else:
        want = set(CONTRACT_CLASSES.get(block, ()))

    if want:
        have = set()
        for el in soup.find_all(class_=True):
            have |= _classes_of(el)
        missing = sorted(want - have)
        if missing:
            fails.append("class_lost")
            notes.append("없어지면 디자인이 깨지는 클래스가 빠졌습니다: "
                         + ", ".join(missing[:5]))

    return fails, " ".join(notes)


# ══════════════════════════════════════════════════════════════
#  2. 최종 HTML 통일 채점
# ══════════════════════════════════════════════════════════════

def check_rendered(html: str, keep, forbid, block: str = "",
                   baseline_html: str = "", strict_structure: bool = True) -> tuple:
    """S 와 J 의 **최종 HTML** 을 같은 기준으로 채점한다.

    base_checks.check_html 을 그대로 쓰되, "LLM 출력 형식"에 해당하는
    검사(code_fence · extra_text · no_html)는 결과에서 뺀다 — 서버가
    렌더한 HTML 에 코드펜스가 붙어 있을 리 없으므로, 남겨두면 J 만
    부당하게 유리해진다.

    반환: (fails, notes)
    """
    if not html:
        return ["no_html"], "HTML이 비어 있습니다."

    fails, notes = base_checks.check_html(
        raw=html,              # raw == html : 형식 검사가 자동으로 통과
        html=html,
        keep=keep,
        forbid=forbid,
        strict_structure=strict_structure,
        allow_script=False,
    )
    fails = [f for f in fails if f not in ("code_fence", "extra_text")]

    p_fails, p_notes = check_product_rules(html, block=block,
                                           baseline_html=baseline_html)
    fails += p_fails
    if p_notes:
        notes = (notes + " " + p_notes).strip()

    return fails, notes


# ══════════════════════════════════════════════════════════════
#  3. 텍스트 필드 태그 주입  (check_plan 에 없던 구멍)
# ══════════════════════════════════════════════════════════════

def check_tag_in_fields(plan: dict) -> tuple:
    """plan 의 텍스트 필드 안에 HTML 태그가 섞였는가.

    base_checks.check_plan 에는 bad_tag_* 검사가 없어서, 텍스트 필드에
    <strong> 이나 <script> 가 들어가도 통과한다. v3 감사에서 "exaone 의
    J8/J9 에서 성공 처리된 22건이 이걸로 샌다"고 지적한 구멍이다.

    AI_EDIT_RULES.md §3 이 문구 강조(span)와 줄바꿈(br)은 명시적으로
    허용하므로 그 둘만 통과시킨다.
    """
    fails, notes = [], []
    for item in (plan or {}).get("blocks", []) or []:
        if not isinstance(item, dict):
            continue
        t = item.get("type", "?")
        for f, val in item.items():
            if f in ("type", "variant"):
                continue
            values = val if isinstance(val, list) else [val]
            for v in values:
                if not isinstance(v, str):
                    continue
                tags = {m.lower() for m in TAG_IN_TEXT.findall(v)}
                bad = sorted(tags - ALLOWED_INLINE)
                if bad:
                    fails.append(f"tag_in_field_{t}_{f}")
                    notes.append(f"{t}.{f} 안에 태그가 있습니다({', '.join(bad[:3])}). "
                                 f"값만 쓰세요 — 마크업은 서버가 만듭니다.")
                    break
    return fails, " ".join(notes)


# ══════════════════════════════════════════════════════════════
#  4. 노선별 진입점 — 케이스에서 이걸 부른다
# ══════════════════════════════════════════════════════════════

def check_html_v4(raw, html, keep, forbid, block: str = "",
                  baseline_html: str = "", strict_structure: bool = True):
    """S 노선. 기존 check_html + 제품 규격 5종.

    반환: (fails, notes, rendered_html)
    """
    fails, notes = base_checks.check_html(
        raw=raw, html=html, keep=keep, forbid=forbid,
        strict_structure=strict_structure, allow_script=False,
    )
    p_fails, p_notes = check_product_rules(html, block=block,
                                           baseline_html=baseline_html)
    fails += p_fails
    if p_notes:
        notes = (notes + " " + p_notes).strip()
    return fails, notes, html


def check_plan_v4(raw, keep, forbid, block: str = "", baseline_html: str = ""):
    """J 노선. 기존 check_plan + 렌더 결과 통일 채점 + 태그 주입.

    반환: (fails, notes, plan, rendered_html)
    """
    fails, notes, plan, rendered = base_checks.check_plan(raw, keep, forbid)

    # plan 자체가 안 나온 경우엔 렌더할 게 없다
    if plan is None:
        return fails, notes, plan, rendered

    t_fails, t_notes = check_tag_in_fields(plan)
    fails += t_fails
    if t_notes:
        notes = (notes + " " + t_notes).strip()

    if rendered:
        r_fails, r_notes = check_rendered(
            rendered, keep=keep, forbid=forbid,
            block=block, baseline_html=baseline_html,
        )
        # check_plan 이 이미 같은 이름으로 잡은 건 중복으로 세지 않는다
        for f in r_fails:
            if f not in fails:
                fails.append(f)
        if r_notes:
            notes = (notes + " " + r_notes).strip()

    return fails, notes, plan, rendered


# ══════════════════════════════════════════════════════════════
#  자기 점검 — LLM 호출 없이 이 파일의 로직만 검증
# ══════════════════════════════════════════════════════════════

def self_check():
    ok = lambda c, m: None if c else (_ for _ in ()).throw(AssertionError(m))

    # nested_section
    f, _ = check_product_rules(
        '<section data-block="hero"><section><h1>제목</h1></section></section>',
        block="hero")
    ok("nested_section" in f, "중첩 section 을 못 잡음")

    # inline_style
    f, _ = check_product_rules(
        '<section class="ev-block block-cta" data-block="cta">'
        '<a style="color:red">참여</a></section>', block="cta")
    ok("inline_style" in f, "인라인 style 을 못 잡음")

    # theme_leaked
    f, _ = check_product_rules(
        '<section class="ev-block block-hero theme-sports" data-block="hero">'
        '<h1>제목</h1></section>', block="hero")
    ok("theme_leaked" in f, "theme-* 누출을 못 잡음")

    # data_block_changed
    f, _ = check_product_rules(
        '<section class="ev-block block-hero" data-block="heroo"><h1>제목</h1></section>',
        block="hero")
    ok("data_block_changed" in f, "data-block 변경을 못 잡음")

    # class_lost — baseline 대조
    base_html = ('<section class="ev-block block-benefits sp-benefits" data-block="benefits">'
                 '<div class="benefit-card"><div class="benefit-body">혜택</div></div></section>')
    out_html = ('<section class="ev-block block-benefits" data-block="benefits">'
                '<div>혜택</div></section>')
    f, _ = check_product_rules(out_html, block="benefits", baseline_html=base_html)
    ok("class_lost" in f, "baseline 클래스 유실을 못 잡음")

    # class_lost — baseline 없으면 CONTRACT_CLASSES 로
    f, _ = check_product_rules('<section data-block="hero"><h1>제목</h1></section>',
                               block="hero")
    ok("class_lost" in f, "계약 클래스 유실을 못 잡음")

    # 정상 출력은 통과해야 한다
    f, _ = check_product_rules(base_html, block="benefits", baseline_html=base_html)
    ok(not f, f"정상 마크업을 실패로 처리함: {f}")

    # tag_in_field — 금지 태그
    f, _ = check_tag_in_fields({"blocks": [
        {"type": "hero", "variant": "x", "title": "여름 <strong>대방출</strong>"}]})
    ok(any(x.startswith("tag_in_field_hero_title") for x in f), "필드 태그 주입을 못 잡음")

    # tag_in_field — 허용 태그는 통과
    f, _ = check_tag_in_fields({"blocks": [
        {"type": "hero", "variant": "x",
         "title": "여름 <span class='highlight'>대방출</span><br>시작"}]})
    ok(not f, f"허용된 span/br 을 실패로 처리함: {f}")

    # 리스트 필드도 본다
    f, _ = check_tag_in_fields({"blocks": [
        {"type": "benefits", "variant": "x", "items": ["정상", "<li>깨짐</li>"]}]})
    ok(any(x.startswith("tag_in_field_benefits_items") for x in f),
       "리스트 필드 태그 주입을 못 잡음")

    # check_rendered 는 형식 실패를 빼야 한다
    f, _ = check_rendered('```html\n<section data-block="hero"><h1>제목</h1></section>',
                          keep=[], forbid=[])
    ok("code_fence" not in f, "렌더 결과에서 code_fence 를 빼지 않음")

    # 공통/전용 분리
    common, only = split_fails(["lost_hero", "unknown_variant", "class_lost", "bad_json"])
    ok(set(common) == {"lost_hero", "class_lost"}, f"공통 분류가 틀림: {common}")
    ok(set(only) == {"unknown_variant", "bad_json"}, f"전용 분류가 틀림: {only}")

    print("  [checks_v4] self_check 통과")


if __name__ == "__main__":
    self_check()
