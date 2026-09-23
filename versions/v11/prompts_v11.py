"""
prompts_v11.py — **두 갈래**. 미러와 제안을 나란히 잰다.
=========================================================

v8~v10 은 백엔드를 글자 그대로 옮기는 게 규칙이었다. v11 은 다르다 —
**"백엔드가 안 한 일도 해보고, 더 나은지 숫자로 답한다."**

다만 섞으면 안 된다. 섞으면 "우리 제안이 더 나은가" 에 영원히 답 못 한다.

    MIRROR    백엔드 develop 그대로            ← 기준선
    PROPOSAL  우리가 더 낫다고 보는 것          ← 비교 대상

같은 케이스·같은 모델로 둘 다 돌려서 **arm 끼리만** 비교한다.

★ v4 가 망한 이유와 구분할 것
  v4 는 "앞서 나가서" 망한 게 아니라 **채점기가 버그라 원본조차 실패**해서
  망했다. 앞서 나가는 것 자체는 문제가 아니다. 라벨만 정확하면 된다.

기준점: backend `develop` @ `bf2b75a`
  v10 은 `9fd0c64` 를 미러했는데 그 뒤 두 번 더 움직였다.
  MIRROR 는 그 두 변경을 반영한 **현재** 백엔드다.

      141487d  edit() 에서 shape 제거
      0af71f5  지어내기 금지를 edit() 에도
"""

import registry_v11 as R

MIRROR = "mirror"
PROPOSAL = "proposal"
ARMS = (MIRROR, PROPOSAL)


def _지어내기_금지() -> list:
    """생성과 수정에 **둘 다** 들어가는 금지 (백엔드 `PromptBuilder.지어내기_금지()`).

    ★ v10 에는 이게 edit() 에 없었다. 백엔드가 v10 실행 20분 전에 넣었는데
      v10 이 안 집어갔다. MIRROR 는 이제 반영한다.
    """
    return [
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택이나 수치를 만들어내지 마라.",
        "- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.",
    ]


def generate() -> str:
    """생성용 — v11 은 생성을 재지 않는다. 미러 유지용으로만 둔다."""
    s = ["너는 통신사 이벤트 페이지를 만드는 도우미다.", ""]
    s += ["출력 규칙:",
          '- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.',
          "- <html>, <head>, <body> 태그를 쓰지 마라.",
          "- 코드블록으로 감싸지 마라.",
          "- 설명, 인사말, 마무리 멘트를 붙이지 마라.", ""]
    s.append("만들 영역:")
    for b in R.llm_blocks():
        s.append(f'- data-block="{b.key}" : {b.desc}{"" if b.required else "  (선택)"}')
        if b.shape is not None:
            s.append(f"    형태: {b.shape}")
    if R.server_blocks():
        s += ["", "만들면 안 되는 영역:"]
        for b in R.server_blocks():
            s.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')
    s += ["", "태그를 반드시 쓴다. 맨 텍스트만 두지 마라.", "예:",
          '<section data-block="hero">', "  <h1>여름 데이터 대방출</h1>",
          "  <p>이번 여름 데이터 걱정 없이</p>", "</section>",
          '<section data-block="cta">',
          '  <a href="#" class="btn">참여하기</a>', "</section>", "", "금지:"]
    s += _지어내기_금지()
    s.append("- 대괄호 자리표시자를 절대 남기지 마라. 값을 모르면 그 문장을 아예 빼라.")
    return "\n".join(s)


def edit(b: R.Block, arm: str = MIRROR) -> str:
    """수정용 — 블록 하나만 주고 하나만 받는다.

    ## 두 arm 의 유일한 차이: shape

        MIRROR    형태 줄 없음    백엔드가 141487d 에서 뺐다
        PROPOSAL  형태 줄 있음    v10 이 쓰던 것

    ★ 백엔드가 뺀 이유는 **추론이지 측정이 아니다.** 커밋 주석:
        "템플릿 benefits 는 .benefit-card div 인데 '<ul> 안에 <li>' 를 주면
         모델이 구조를 갈아엎어서 디자인이 망가진다."

      그런데 v10 은 **shape 를 주고도** D군 9/9 였다(gemma·haiku).
      정말 방해였는지 여기서 답한다.
    """
    if arm not in ARMS:
        raise ValueError(f"모르는 arm: {arm} (mirror | proposal)")
    if b.source == R.SERVER:
        raise ValueError(f"{b.key} 는 서버 소유입니다. 모델에게 수정시키면 안 됩니다.")

    s = ["너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.", "",
         f'<section data-block="{b.key}"> 영역만 수정해서 그 영역만 출력한다.',
         f"이 영역의 역할: {b.desc}"]

    # ★★ 두 arm 이 갈리는 **유일한** 지점
    if arm == PROPOSAL and b.shape is not None:
        s.append(f"형태: {b.shape}")

    s += ["", "출력 규칙:",
          f'- <section data-block="{b.key}"> 로 시작해서 </section> 으로 끝난다.',
          "- 다른 영역을 새로 만들지 마라.",
          "- 코드블록으로 감싸지 마라.",
          "- 설명을 붙이지 마라.", ""]
    s += ["건드리면 안 되는 것:",
          '- data-slot="..." 이 붙은 태그는 지우지 마라. 태그와 속성을 그대로 둔다.',
          "- 그 안의 내용을 채우지 마라. 비어 있으면 비운 채로 둔다. 서버가 채운다.",
          "- data-slot 을 새로 만들지 마라.",
          "- class 를 바꾸거나 지우지 마라. 디자인과 버튼 동작이 class 에 걸려 있다.",
          "- id 를 지우거나 새로 만들지 마라. 화면 기능이 id 로 요소를 찾는다.",
          "- <button> 을 <a> 나 <div> 로 바꾸지 마라.",
          "- 원래 있던 이모지를 지우지 마라. 문구를 바꿀 때도 그대로 둔다.", ""]
    s += ["금지:",
          "- 요청받은 것만 바꿔라. href, class 같은 기존 속성은 그대로 둔다.",
          '- href="#" 는 그대로 둬라. 실제 주소를 만들어 넣지 마라.']
    s += _지어내기_금지()
    s.append("- 대괄호 자리표시자를 남기지 마라.")
    return "\n".join(s)


# ── 라우터 ────────────────────────────────────────────────────────
ROUTER_OPS = ["EDIT", "ADD", "DELETE", "STYLE"]


def router(arm: str = MIRROR) -> str:
    """라우터.

    ## MIRROR — 백엔드 `PromptBuilder.router()` 그대로

        {"op":"EDIT","target":"benefits"}

    op 하나 · target 하나다. 그래서 **두 가지를 표현할 수 없다**:

        되묻기      "혜택 하나 더 추가해줘" 에 내용이 없다는 걸 말할 자리가 없다
        복합 요청   "제목 바꾸고 혜택도 추가해줘" 를 담을 자리가 없다

    ## PROPOSAL — ops 배열 + content 추출

        {"ops":[{"op":"EDIT","target":"hero","content":"가을 대축제"},
                {"op":"EDIT","target":"benefits","content":null}]}

    ★ 결정 ③("라우터는 분류만, 거부는 서버") 을 **깨지 않는다.**
      라우터에게 "내용이 충분한지 판단해라" 를 시키면 판단이 라우터로 넘어간다.
      그래서 **추출만** 시킨다 — 있으면 쓰고 없으면 null.
      null 을 보고 되물을지 정하는 건 **서버**다.

    ★ 여기서 재는 것 셋
      ① 복합 요청을 ops 두 개로 쪼개는가
      ② 내용이 없을 때 **null 을 내는가** (지어내서 채우지 않는가)
         — 이게 안 되면 되묻기는 이 설계로 불가능하다
      ③ ROUTER 캡 256 토큰에 걸리는가 (content 에 사용자 문구가 들어간다)
    """
    if arm not in ARMS:
        raise ValueError(f"모르는 arm: {arm} (mirror | proposal)")
    names = ", ".join(b.key for b in R.BLOCKS)

    s = ["너는 사용자 요청을 분류하는 라우터다. JSON 하나만 출력한다.", "",
         f"영역 이름: {names}", "", "출력 형식:"]

    if arm == MIRROR:
        s.append('{"op":"<동작>","target":"<영역 이름 또는 null>"}')
    else:
        # ★ 실측으로 고친 것 (2026-09-23, 1차 라우터 실행)
        #   처음엔 "사용자가 직접 말한 내용만 그대로 옮긴다" 한 줄이었는데,
        #   모델이 **요청 문장을 통째로** content 에 넣었다 —
        #       "혜택 하나 더 추가해줘" → content: "혜택 하나 더 추가해줘"
        #   지어낸 게 아니라 "말한 내용" 을 요청문으로 해석한 것이다.
        #   내 프롬프트 결함이었다. 경계를 예시로 보여준다.
        s += ['{"ops":[{"op":"<동작>","target":"<영역 이름>","content":"<내용 또는 null>"}]}',
              "",
              "요청에 동작이 여러 개면 ops 에 여러 개를 넣는다.",
              "",
              "content 규칙:",
              "- 사용자가 따옴표로 준 문구나 구체적인 항목 이름만 넣는다.",
              "- 요청 문장 자체를 옮기지 마라.",
              "- 바꿀 **방향**만 말했으면(더 짧게, 더 친절하게) content 는 null 이다.",
              "- content 를 네가 지어내서 채우지 마라.",
              "",
              "예:",
              '  "제목을 \'가을 대축제\' 로 바꿔줘"       → content: "가을 대축제"',
              '  "혜택에 \'영화 관람권\' 을 추가해줘"     → content: "영화 관람권"',
              '  "혜택 하나 더 추가해줘"                 → content: null',
              '  "소개 문구를 더 힘있게 바꿔줘"           → content: null']

    # ★ ADD·DELETE 는 **아무 영역에나 되는 게 아니다.** 레지스트리가 이미 안다.
    #
    #   benefits.required = True  →  모든 유효한 문서에 항상 있다
    #   benefits.canCreate() = False → ADD 가 정의상 불가능
    #
    #   5개 중 ADD 가 되는 건 steps 하나뿐인데(유일한 required=False),
    #   MIRROR 프롬프트는 다섯을 **평평하게 나열**한다. 그래서 모델이
    #   "추가해줘" 를 듣고 ADD 를 고른다 — 1차 실측에서 8건 났다.
    #
    #   `generate()` 는 llmBlocks()·serverBlocks() 로 나눠 "만들면 안 되는
    #   영역" 을 명시하는데 `router()` 만 그걸 안 한다. PROPOSAL 은 한다.
    #
    #   ★ 목록을 손으로 적지 않는다. 레지스트리에서 뽑아야 백엔드가 required 를
    #     바꿔도 같이 따라간다.
    addable = [b.key for b in R.BLOCKS if b.can_create()]
    deletable = [b.key for b in R.BLOCKS if b.can_delete()]
    add_tail = del_tail = ""
    if arm == PROPOSAL:
        add_tail = f"  ({', '.join(addable)} 만 가능)" if addable else "  (해당 없음)"
        del_tail = f"  ({', '.join(deletable)} 만 가능)" if deletable else "  (해당 없음)"

    s += ["", "동작:",
          '- "EDIT"    특정 영역의 내용을 고친다',
          f'- "ADD"     없는 영역을 새로 넣는다{add_tail}',
          f'- "DELETE"  영역을 통째로 지운다{del_tail}',
          '- "STYLE"   색·크기·굵기 등 겉모양만 바꾼다']
    if arm == PROPOSAL:
        s.append("- 이미 있는 영역의 **내용**을 더하거나 빼는 것은 EDIT 이다.")
    s += ["", "JSON 외에는 아무것도 출력하지 마라."]
    return "\n".join(s)


def self_check():
    g = generate()
    assert '<section data-block="hero">' in g
    assert "주어지지 않은 혜택이나 수치를 만들어내지 마라" in g

    # ── edit: 두 arm 의 차이는 shape **하나뿐**이어야 한다
    b = R.of("benefits")
    m, p = edit(b, MIRROR), edit(b, PROPOSAL)
    assert f"형태: {b.shape}" not in m, "MIRROR 에 shape 가 들어갔습니다"
    assert f"형태: {b.shape}" in p, "PROPOSAL 에 shape 가 빠졌습니다"
    only = [ln for ln in p.split("\n") if ln not in m.split("\n")]
    assert only == [f"형태: {b.shape}"], f"arm 차이가 shape 말고 더 있습니다: {only}"

    # ★ v10 에 빠져 있던 것 — 두 arm 다 있어야 한다
    for txt in (m, p):
        assert "주어지지 않은 혜택이나 수치를 만들어내지 마라" in txt
        assert 'href="#" 는 그대로 둬라' in txt

    try:
        edit(R.of("notices"))
        raise AssertionError("notices 는 edit 프롬프트가 나오면 안 된다")
    except ValueError:
        pass

    # ── router
    rm, rp = router(MIRROR), router(PROPOSAL)
    assert '{"op":"<동작>","target":"<영역 이름 또는 null>"}' in rm
    assert '"ops"' in rp and "content 는 null 이다" in rp
    assert "요청 문장 자체를 옮기지 마라" in rp    # ★ 1차 실행에서 밟은 것

    # ★ ADD 가능 목록은 레지스트리에서 나와야 한다 (손으로 적으면 어긋난다)
    assert "(steps 만 가능)" in rp, "PROPOSAL 에 ADD 가능 목록이 없습니다"
    assert "이미 있는 영역의 **내용**" in rp
    assert "만 가능)" not in rm, "MIRROR 가 오염됐습니다 — 백엔드엔 이 줄이 없습니다"
    assert [b.key for b in R.BLOCKS if b.can_create()] == ["steps"]
    assert '"ops"' not in rm, "MIRROR 라우터가 오염됐습니다"
    for r in (rm, rp):
        for op in ROUTER_OPS:
            assert f'"{op}"' in r
        assert "notices" in r          # SERVER 블록도 목록에 있다 (거부는 서버가)
    print("  [prompts_v11] self_check 통과 — arm 2종")


if __name__ == "__main__":
    self_check()
