"""
edit_lib.py — 블록 왕복 편집 공용 헬퍼 (base/)
================================================
versions/v1/cases_e.py 에서 처음 구현된 canonical()/outside_preserved()/
build_block_edit_system() 로직을 그대로 옮겨 담았다. v1/cases_e.py 자체는
그 버전의 조건을 보존하기 위해 건드리지 않고 그대로 두며(그 파일도 여기
있는 것과 동일한 로직을 자기 안에 갖고 있다 — 중복이지만 v1은 "그 버전의
결과를 낸 스크립트를 그대로 보존"하는 게 원칙이라 의도적으로 냅둔다).

새 버전(v3부터)에서 같은 "블록 하나만 왕복시켜 편집" 메커니즘이 필요할
때는 v1 파일에서 복사하지 말고 이 모듈을 import 해서 쓴다.
(versions/v3/README.md §3 — "CHAIN3·CHAIN4·CHAIN5는 build_block_edit_system을
재사용해야 하므로 base/ 공용으로 옮기는 작업이 선행돼야 한다"의 결과물.)
"""

import re

from bs4 import BeautifulSoup, NavigableString

from registry import BY_KEY


def safe_soup(markup):
    """BeautifulSoup 파싱을 안전하게 감싼다 — 깨진 마크업(<![--- 등)이
    ParserRejectedMarkup을 던져 전체 실행을 죽이는 걸 방지한다."""
    try:
        return BeautifulSoup(markup or "", "html.parser")
    except Exception:
        return BeautifulSoup("", "html.parser")


def block_of(html: str, key: str) -> str:
    el = safe_soup(html).select_one(f'[data-block="{key}"]')
    return str(el) if el else ""


def replace_block(doc: str, key: str, new_html: str) -> str:
    """수정된 블록을 문서에 되돌려 끼운다. 대상 블록이 원래 없었으면
    맨 뒤에 붙인다(C6류 체인에서 '새 영역 추가' 단계에 필요)."""
    soup = safe_soup(doc)
    old = soup.select_one(f'[data-block="{key}"]')
    frag = safe_soup(new_html)
    new = frag.select_one(f'[data-block="{key}"]')
    if new is None:
        return doc
    if old is None:
        soup.append(new)
    else:
        old.replace_with(new)
    return str(soup)


def canonical(node):
    """DOM 노드를 순서/공백에 안 흔들리는 튜플로 정규화한다.
    문자열 그대로 비교하면 공백 하나만 달라도 '다르다'고 나오는데,
    실제로 알고 싶은 건 '구조와 내용이 의미상 같은가'다."""
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
    새로 추가'하는 경우(맨 뒤에 key가 새로 붙은 경우)는 예외로 허용한다."""
    a, b = safe_soup(before), safe_soup(after)
    old_keys = [x.get("data-block") for x in a.find_all("section")]
    new_keys = [x.get("data-block") for x in b.find_all("section")]
    if new_keys != old_keys and not (key not in old_keys and new_keys == old_keys + [key]):
        return False
    for doc in (a, b):
        for el in doc.select(f'[data-block="{key}"]'):
            el.decompose()
    return canonical(a) == canonical(b)


def build_block_edit_system(key: str) -> str:
    """블록 하나만 고칠 때 — 그 블록 외에는 출력 자체를 막는 시스템 프롬프트."""
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


def self_check():
    """LLM 호출 없이 이 모듈만 단독으로 회귀 검증한다."""
    doc = ('<section data-block="hero"><h1>제목</h1></section>'
           '<section data-block="cta"><a href="#" class="btn">가입하기</a></section>')
    assert block_of(doc, "hero")
    assert block_of(doc, "steps") == ""

    edited_cta = '<section data-block="cta"><a href="#" class="btn">지금 신청하기</a></section>'
    merged = replace_block(doc, "cta", edited_cta)
    assert "지금 신청하기" in merged
    assert "<h1>제목</h1>" in merged
    assert outside_preserved(doc, merged, "cta"), "cta 외 영역이 보존됐어야 함"

    drifted = merged.replace("<h1>제목</h1>", "<h1>제목!</h1>")
    assert not outside_preserved(doc, drifted, "cta"), "hero 드리프트를 못 잡아냄"

    new_block = '<section data-block="steps"><ol><li>1단계</li><li>2단계</li></ol></section>'
    added = replace_block(doc, "steps", new_block)
    assert outside_preserved(doc, added, "steps"), "새 블록 추가는 나머지 보존으로 인정돼야 함"

    system = build_block_edit_system("cta")
    assert "cta" in system and "href" in system


if __name__ == "__main__":
    self_check()
    print("edit_lib.py self_check 통과")
