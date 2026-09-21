"""
prompts_v8.py — 백엔드 `registry.PromptBuilder` 미러
=====================================================

Java 쪽 `PromptBuilder.generate() / edit() / router()` 를 **글자 그대로** 옮긴
것이다. 한 글자라도 다르면 v8 은 "서비스가 하지 않는 일"을 재게 된다.

★ v1~v7 이 겪은 실패를 반복하지 않기 위한 파일이다.
    v3 README 가 경고한 "같은 프롬프트가 두 파일에 중복 보관" 문제가 이제
    **저장소를 넘어서** 생겼다 — 벤치마크(Python)와 서비스(Java).
    백엔드 PR 이 프롬프트를 건드리면 여기도 같이 고쳐야 한다.

★ 아직 반영 안 된 것 (백엔드 PR 대기 중)
    PR 설명에 "수정 프롬프트에 슬롯 규칙"이 있지만, 현재 develop 의
    PromptBuilder.edit() 에는 슬롯 문장이 없다. 그래서 여기도 없다 —
    **지금 develop 과 일치시키는 쪽**을 골랐다. PR 이 머지되면
    `edit()` 에 슬롯 규칙을 넣고 v8.1 로 올린다.
"""

import registry_v8 as R


def generate() -> str:
    """생성용 — 페이지 전체를 한 번에 만든다"""
    s = []
    s.append("너는 통신사 이벤트 페이지를 만드는 도우미다.")
    s.append("")
    s.append("출력 규칙:")
    s.append('- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.')
    s.append("- <html>, <head>, <body> 태그를 쓰지 마라.")
    s.append("- 코드블록으로 감싸지 마라.")
    s.append("- 설명, 인사말, 마무리 멘트를 붙이지 마라.")
    s.append("")
    s.append("만들 영역:")
    for b in R.llm_blocks():
        tail = "" if b.required else "  (선택)"
        s.append(f'- data-block="{b.key}" : {b.desc}{tail}')
        if b.shape is not None:
            s.append(f"    형태: {b.shape}")
    if R.server_blocks():
        s.append("")
        s.append("만들면 안 되는 영역:")
        for b in R.server_blocks():
            s.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')
    s.append("")
    s.append("태그를 반드시 쓴다. 맨 텍스트만 두지 마라.")
    s.append("예:")
    s.append('<section data-block="hero">')
    s.append("  <h1>여름 데이터 대방출</h1>")
    s.append("  <p>이번 여름 데이터 걱정 없이</p>")
    s.append("</section>")
    s.append('<section data-block="cta">')
    s.append('  <a href="#" class="btn">참여하기</a>')
    s.append("</section>")
    s.append("")
    s.append("금지:")
    s.append("- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.")
    s.append("- 주어지지 않은 혜택이나 수치를 만들어내지 마라.")
    s.append("- 대괄호 자리표시자를 절대 남기지 마라. 값을 모르면 그 문장을 아예 빼라.")
    s.append("- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.")
    s.append("- 이모지를 쓰지 마라.")
    return "\n".join(s)


def edit(b: R.Block) -> str:
    """수정용 — 블록 하나만 주고 하나만 받는다"""
    if b.source == R.SERVER:
        raise ValueError(f"{b.key} 는 서버 소유입니다. 모델에게 수정시키면 안 됩니다.")
    s = []
    s.append("너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.")
    s.append("")
    s.append(f'<section data-block="{b.key}"> 영역만 수정해서 그 영역만 출력한다.')
    s.append(f"이 영역의 역할: {b.desc}")
    if b.shape is not None:
        s.append(f"형태: {b.shape}")
    s.append("")
    s.append("출력 규칙:")
    s.append(f'- <section data-block="{b.key}"> 로 시작해서 </section> 으로 끝난다.')
    s.append("- 다른 영역을 새로 만들지 마라.")
    s.append("- 코드블록으로 감싸지 마라.")
    s.append("- 설명을 붙이지 마라.")
    s.append("")
    s.append("금지:")
    s.append("- 요청받은 것만 바꿔라. href, class 같은 기존 속성은 그대로 둔다.")
    s.append('- href="#" 는 그대로 둬라. 실제 주소를 만들어 넣지 마라.')
    s.append("- 날짜를 임의로 만들지 마라.")
    s.append("- 대괄호 자리표시자를 남기지 마라.")
    s.append("- 이모지를 쓰지 마라.")
    return "\n".join(s)


def router() -> str:
    """라우터 — 영역 목록도 레지스트리에서 나온다"""
    names = ", ".join(b.key for b in R.BLOCKS)
    s = []
    s.append("너는 사용자 요청을 분류하는 라우터다. JSON 하나만 출력한다.")
    s.append("")
    s.append(f"영역 이름: {names}")
    s.append("")
    s.append("출력 형식:")
    s.append('{"op":"<동작>","target":"<영역 이름 또는 null>"}')
    s.append("")
    s.append("동작:")
    s.append('- "EDIT"    특정 영역의 내용을 고친다')
    s.append('- "ADD"     없는 영역을 새로 넣는다')
    s.append('- "DELETE"  영역을 통째로 지운다')
    s.append('- "STYLE"   색·크기·굵기 등 겉모양만 바꾼다')
    s.append("")
    s.append("JSON 외에는 아무것도 출력하지 마라.")
    return "\n".join(s)


# 라우터가 낼 수 있는 동작 — 백엔드 router() 프롬프트와 같은 목록
ROUTER_OPS = ["EDIT", "ADD", "DELETE", "STYLE"]


def self_check():
    g = generate()
    assert '<section data-block="hero">' in g
    assert "notices\" 는 절대 만들지 마라" in g or 'data-block="notices" 는 절대' in g
    assert '<a href="#" class="btn">참여하기</a>' in g

    e = edit(R.of("cta"))
    assert '<section data-block="cta">' in e
    assert 'href="#" 는 그대로 둬라' in e
    # SERVER 블록은 수정 프롬프트를 만들면 안 된다
    try:
        edit(R.of("notices"))
        raise AssertionError("notices 는 edit 프롬프트가 나오면 안 된다")
    except ValueError:
        pass

    r = router()
    for op in ROUTER_OPS:
        assert f'"{op}"' in r
    # 라우터는 SERVER 블록까지 포함한 전체 목록을 안내한다 (Block.values())
    assert "notices" in r
    print("  [prompts_v8] self_check 통과")


if __name__ == "__main__":
    self_check()
