"""
cases_v9.py — 백엔드의 세 프롬프트에 1:1 대응하는 케이스
=========================================================

백엔드 `PromptBuilder` 는 프롬프트를 셋만 만든다. v8 의 군도 셋뿐이다.

    G  generate()   페이지 전체 생성
    E  edit(block)  블록 하나 수정
    R  router()     요청 분류 (op + target)

## 왜 R 이 제일 먼저인가

v1 에서 **R군이 가장 나빴다** — 최종 통과 기준으로도 최고가 60% 언저리였다
(exaone 95/240, qwen2.5 144/240). 그런데 백엔드 구조상 라우터는 **모든 기능의
입구**다. op 이나 target 을 틀리면 멀쩡한 블록을 지우거나 엉뚱한 데를 고친다.
생성·수정이 아무리 좋아도 라우터가 틀리면 제품이 안 된다.

게다가 라우터는 **제일 싸다**(ROUTER 캡 256, 출력 JSON 한 줄). 가장 위험한
축이 가장 싼 축이라 여기부터 재는 게 맞다.

## 왜 삭제 케이스(E4)를 넣는가

v2·v4·v6 에 걸쳐 "구조를 줄이는 조작"은 로컬 모델이 일관되게 회피했다
(K-T 삭제 0/5 전 모델). 백엔드는 JSON 패치 경로가 없고 HTML 직접 편집이라
조건이 다르지만, **같은 회피가 HTML 경로에서도 나오는지**는 확인된 적이 없다.
"""

from dataclasses import dataclass, field

import checks_v9 as C
import prompts_v9 as P
import registry_v9 as R


@dataclass
class Case:
    pid: str
    group: str          # G | E | R
    mode: str           # html | router
    system: str
    user: str
    # 수정 케이스만
    target: R.Block | None = None
    before: str = ""
    # 결과 판정 추가 조건
    want_text: str = ""            # 이 문자열이 결과에 있어야 한다
    want_op: str = ""              # 라우터 정답 동작
    want_target: str | None = None  # 라우터 정답 대상 (None 이면 null 이어야)
    expect_items: int | None = None  # must 로 센 항목 수가 정확히 이것이어야
    note: str = ""


# ── baseline — 레지스트리 shape 를 그대로 따른 최소 마크업
#   ★ 템플릿(template/*.html)을 쓰지 않는다. 백엔드가 모델에게 시키는 형태는
#     Block.shape 이고, 템플릿은 그것과 다른 물건이다(cta 가 <button>).
HERO_BEFORE = (
    '<section data-block="hero">'
    "<h1>여름 데이터 대방출</h1>"
    '<p>이번 여름 <span data-slot="period">2026.09.20 ~ 2026.10.05</span> 데이터 걱정 없이</p>'
    "</section>"
)

BENEFITS_BEFORE = (
    '<section data-block="benefits">'
    "<ul><li>데이터 10GB 추가 제공</li>"
    "<li>영화 관람권 1매</li>"
    "<li>제휴 카페 음료 쿠폰</li></ul>"
    "</section>"
)

CTA_BEFORE = (
    '<section data-block="cta">'
    '<a href="#" class="btn" data-slot="cta-link">응모하기</a>'
    "</section>"
)

STEPS_BEFORE = (
    '<section data-block="steps">'
    "<ol><li>앱에 로그인한다</li>"
    "<li>이벤트 배너를 누른다</li>"
    "<li>응모 버튼을 누른다</li></ol>"
    "</section>"
)

GEN_USER = (
    "여름 데이터 프로모션 페이지를 만들어줘.\n"
    "혜택은 데이터 10GB 추가 제공, 영화 관람권 1매, 제휴 카페 음료 쿠폰 세 가지야.\n"
    "참여 방법은 앱 로그인 후 배너를 눌러 응모하는 순서로 써줘."
)


def _gen(pid, user, note=""):
    return Case(pid, "G", "html", P.generate(), user, note=note)


def _edit(pid, key, user, before, want_text="", expect_items=None, note=""):
    b = R.of(key)
    return Case(pid, "E", "html", P.edit(b), f"{user}\n\n{before}",
                target=b, before=before, want_text=want_text,
                expect_items=expect_items, note=note)


def _route(pid, user, want_op, want_target, note=""):
    return Case(pid, "R", "router", P.router(), user,
                want_op=want_op, want_target=want_target, note=note)


CASES = [
    # ── G 생성 ────────────────────────────────────────────────────
    _gen("G1", GEN_USER,
         note="기본 생성 — 필수 블록 3종 + 선택 blocks, notices 는 만들면 안 됨"),
    _gen("G2", GEN_USER + "\n참여 방법은 넣지 말고 간단하게 만들어줘.",
         note="선택 블록(steps) 생략 — 필수만 내는가"),

    # ── E 수정 ────────────────────────────────────────────────────
    _edit("E1", "cta", "이 영역의 버튼 문구를 '지금 응모하기' 로 바꿔줘.",
          CTA_BEFORE, want_text="지금 응모하기",
          note="문구만 교체. href·class·data-slot 이 살아야 한다"),
    _edit("E2", "hero", "이 영역의 제목을 '가을 데이터 대축제' 로 바꿔줘.",
          HERO_BEFORE, want_text="가을 데이터 대축제",
          note="기간 슬롯을 건드리면 안 된다"),
    _edit("E3", "benefits", "이 영역에 혜택 항목을 하나 더 추가해줘. "
          "기존 항목과 같은 구조로 만들어야 한다.",
          BENEFITS_BEFORE, expect_items=4,
          note="구조 늘리기"),
    _edit("E4", "benefits", "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.",
          BENEFITS_BEFORE, expect_items=2,
          note="★ 구조 줄이기 — 로컬 모델이 일관되게 회피한 축"),

    # ── R 라우터 ──────────────────────────────────────────────────
    _route("R1", "혜택에 데이터 쿠폰 하나 더 넣어줘", "EDIT", "benefits",
           note="ADD 로 오답 내기 쉬움 — 블록 추가가 아니라 내용 수정이다"),
    _route("R2", "참여 방법 단계를 통째로 빼줘", "DELETE", "steps",
           note="선택 블록이라 실제로 지울 수 있다"),
    _route("R3", "제목 글씨를 더 크고 빨갛게 해줘", "STYLE", "hero",
           note="EDIT 과 헷갈리는 축 — 겉모양만 바꾸는 요청"),
    _route("R4", "참여 방법 영역이 없는데 새로 넣어줘", "ADD", "steps",
           note="ADD 정답 — R1 과 짝"),
    _route("R5", "버튼 문구를 '지금 참여' 로 바꿔줘", "EDIT", "cta"),
    _route("R6", "유의사항 문구를 우리가 직접 고칠게", "EDIT", "notices",
           note="★ SERVER 블록 — 라우터는 target 을 맞혀야 하고, "
                "거절은 Block.denyReason 이 한다(모델 책임 아님)"),
    _route("R7", "이벤트 제목이랑 소개 문구 좀 다듬어줘", "EDIT", "hero"),
    _route("R8", "혜택 영역을 아예 없애줘", "DELETE", "benefits",
           note="★ 필수 블록이라 실제로는 거절되어야 한다 — "
                "라우터는 의도대로 분류하고, 막는 건 서버"),
]

# ── C 누적 수정 ───────────────────────────────────────────────────
#
# 백엔드 실사용은 한 턴으로 안 끝난다. 사용자는 계속 고친다.
#
#     router → edit(block) → sanitize → merge → (또 고침) → router → ...
#
# G·E·R 은 전부 **1턴**만 본다. v7 에서 4단계 체인이 0~100% 로 갈린 걸 보면
# 이 축은 따로 재야 한다. v1 의 C군(누적 5단계)이 재던 것과 같은 질문이다.
#
# ★ 여기서만 볼 수 있는 것 — **정화 손상의 누적**
#   정화는 턴마다 걸린다. 1턴에서 cta 의 href 가 잘려나간 채 문서에 병합되면
#   그 손상은 문서에 **영구히 남는다.** 3턴을 돌면 손상이 쌓인다.
#   1턴짜리 E군으로는 "한 번 잘린다"까지만 보이고, 쌓이는 건 안 보인다.
#
# ★ 부분 재생성(블록 하나만)이 기본이다.
#   매 턴 `edit(block)` 프롬프트에 **그 블록만** 넣어 보낸다. 전체 문서를
#   보내지 않는다 — 백엔드가 확정한 방식이고, 토큰도 그쪽이 훨씬 싸다.

START_DOC = (
    HERO_BEFORE + BENEFITS_BEFORE + STEPS_BEFORE + CTA_BEFORE
)


@dataclass
class Turn:
    block_key: str
    user: str
    want_text: str = ""
    expect_items: int | None = None


@dataclass
class ChainCase:
    pid: str
    turns: list
    note: str = ""
    group: str = "C"

    def system_for(self, turn: Turn) -> str:
        return P.edit(R.of(turn.block_key))


CHAIN_CASES = [
    ChainCase(
        "C1",
        [
            Turn("cta", "이 영역의 버튼 문구를 '지금 응모하기' 로 바꿔줘.",
                 want_text="지금 응모하기"),
            Turn("hero", "이 영역의 제목을 '가을 데이터 대축제' 로 바꿔줘.",
                 want_text="가을 데이터 대축제"),
            Turn("benefits", "이 영역에 혜택 항목을 하나 더 추가해줘. "
                 "기존 항목과 같은 구조로 만들어야 한다.",
                 expect_items=4),
        ],
        note="서로 다른 블록 3턴 — 앞 턴의 변경이 끝까지 남는가",
    ),
    ChainCase(
        "C2",
        [
            Turn("benefits", "이 영역에 혜택 항목을 하나 더 추가해줘.", expect_items=4),
            Turn("benefits", "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.", expect_items=3),
            Turn("benefits", "이 영역의 혜택 문구를 더 짧고 간결하게 다듬어줘.",
                 expect_items=3),
        ],
        note="★ 같은 블록 3턴 — 늘렸다 줄였다. 구조를 줄이는 축이 누적에서도 버티는가",
    ),
]

BY_GROUP = {}
for c in CASES:
    BY_GROUP.setdefault(c.group, []).append(c)
BY_GROUP["C"] = CHAIN_CASES


def uses_slots(case) -> bool:
    """이 케이스의 baseline 에 data-slot 이 들어 있나.

    ★ v8 에서는 이게 "돌리면 안 되는 케이스" 표시였다. 정화가 수정 경로에서도
      슬롯을 지워서, 모델이 완벽해도 `slot_lost` 로 떨어졌기 때문이다
      (`--skip-slot-cases` 로 통째로 뺐다).

      **v9 에서는 반대다.** 정화 2종 분리가 머지돼서 슬롯이 보존되므로,
      이 케이스들이 오히려 **v9 가 새로 재려는 것**이다 — 슬롯 보존이
      드디어 모델 능력으로 측정된다. `--skip-slot-cases` 는 회귀 확인용으로만
      남겨둔다(v8 조건을 재현해서 비교할 때).
    """
    if isinstance(case, ChainCase):
        return any("data-slot" in _baseline_of(t.block_key) for t in case.turns)
    return "data-slot" in (case.before or "")


def _baseline_of(block_key: str) -> str:
    """C군은 START_DOC 에서 블록을 꺼내 쓰므로 거기서 본다."""
    el = C._soup(START_DOC).select_one(R.of(block_key).selector())
    return str(el) if el is not None else ""


def self_check():
    P.self_check()

    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group in ("G", "E", "R")
        assert c.mode in ("html", "router")
        if c.group == "E":
            assert c.target is not None and c.before, f"{c.pid} 수정 케이스인데 before 가 없다"
            assert c.before in c.user, f"{c.pid} 프롬프트에 원본이 안 들어감"
        if c.group == "R":
            assert c.want_op in P.ROUTER_OPS, f"{c.pid} 모르는 동작 {c.want_op}"
            if c.want_target is not None:
                R.of(c.want_target)   # 없는 블록이면 여기서 죽는다

    # ★ 회귀 — baseline 이 검증을 통과해야 한다. 원본이 불합격이면
    #   모델이 뭘 해도 실패로 찍힌다 (v4 에서 이걸 안 해서 결과를 버렸다).
    for key, before in (("hero", HERO_BEFORE), ("benefits", BENEFITS_BEFORE),
                        ("cta", CTA_BEFORE), ("steps", STEPS_BEFORE)):
        fails = [c for c, _ in C.validate_edited(R.of(key), before, before)]
        assert not fails, f"{key} baseline 이 불합격: {fails}"

    # ★ 누적 문서(START_DOC)도 회귀 검사 — 서버가 들고 있는 문서가
    #   애초에 불합격이면 C군은 첫 턴부터 의미가 없다.
    #   슬롯은 서버가 심은 것이므로 check_slots=False.
    doc_fails = [c for c, _ in C.validate_generated(START_DOC)]
    assert not doc_fails, f"START_DOC 이 불합격: {doc_fails}"
    for s in ("period", "cta-link"):
        assert f'data-slot="{s}"' in START_DOC, f"START_DOC 에 {s} 슬롯이 없다"

    for cc in CHAIN_CASES:
        assert cc.turns, f"{cc.pid} 턴이 없다"
        for t in cc.turns:
            b = R.of(t.block_key)          # 없는 블록이면 여기서 죽는다
            assert b.can_edit(), f"{cc.pid}: {t.block_key} 는 수정 대상이 아니다"
            assert C._soup(START_DOC).select_one(b.selector()) is not None, (
                f"{cc.pid}: START_DOC 에 {t.block_key} 블록이 없다")

    # 슬롯 케이스 판별 — --skip-slot-cases 가 이걸 믿고 거른다
    slot_pids = {c.pid for c in CASES + CHAIN_CASES if uses_slots(c)}
    assert slot_pids == {"E1", "E2", "C1"}, slot_pids

    counts = {g: len(v) for g, v in BY_GROUP.items()}
    assert counts == {"G": 2, "E": 4, "R": 8, "C": 2}, counts
    turns = sum(len(c.turns) for c in CHAIN_CASES)
    print(f"  [cases_v9] self_check 통과 — G {counts['G']} · E {counts['E']} · "
          f"R {counts['R']} · C {counts['C']}({turns}턴)")


if __name__ == "__main__":
    self_check()
