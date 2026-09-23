"""
cases_v11.py — 다섯 군. 기존 셋을 고치고 둘을 새로 만든다.
============================================================

    D  Design    must 는 통과하는데 디자인이 깨지는가      3   (v10 계승)
    P  Preserve  class·slot·id·훅이 남는가                3   (v10 계승 + id 대조)
    H  Halluc    준 것만 쓰는가                           3   (H3 수리)
    V  Value     ★ 값을 바꾸는가 — 한 번도 안 잰 축        3   (신규)
    R  Router    ★ 새 스키마를 지키는가                    5   (신규, arm 2종)

## v10 에서 고친 것

★ **무변경 통과 4개를 막았다.** v10 은 9케이스 중 D3·P3·H2·H3 가
  원본을 그대로 돌려줘도 통과했다. 그 칸의 ✓ 는 "잘했다" 가 아니라
  "안 부쉈다" 였고, gemma 27/27 중 9칸이 실질적으로 빈 칸이었다.

      D3·P3·H2  →  want_change=True  (check_text_changed)
      H3        →  want_text + expect_items

★ **H3 가 환각을 못 쟀다.** `steps` 가 `Source.LLM` 이라
  `check_items_preserved` 가 스스로 꺼진다(모델이 다 만드는 블록이니 맞는
  동작이다). 그래서 요청 이행만이라도 재도록 want_text·expect_items 를 건다.

## 그래서 v10 과 통과율을 직접 비교할 수 없다

채점 기준이 달라졌다. v11 은 "v10 보다 좋아졌나" 가 아니라
**"이제 제대로 재니 실제로 어떤가"** 를 보는 버전이다.
비교는 **arm 끼리만** 한다.
"""

from dataclasses import dataclass, field

import checks_v11 as C
import prompts_v11 as P
import registry_v11 as R
import templates_v11 as T


# ── HTML 수정 케이스 ──────────────────────────────────────────────
@dataclass
class Case:
    pid: str
    group: str                      # D | P | H | V
    instruction: str
    tpl: int = 0
    block: str = ""
    want_text: str = ""             # 결과에 반드시 있어야 할 문자열
    expect_items: int | None = None
    check_invented: bool = False    # 기존 항목의 값이 유실됐나 (항목 단위)
    want_change: bool = True        # ★ 문구가 실제로 바뀌어야 하나
    check_values: bool = False      # ★ v11 — 수치가 변조됐나 (문서 단위)
    allow_new_values: bool = False  # 항목을 더하는 요청이면 새 수치는 정상
    note: str = ""

    kind = "html"

    @property
    def target(self) -> R.Block:
        return R.of(self.block)

    @property
    def before(self) -> str:
        return T.block_html(self.tpl, self.block)

    def system(self, arm: str = P.MIRROR) -> str:
        return P.edit(self.target, arm)

    @property
    def user(self) -> str:
        return f"{self.instruction}\n\n{self.before}"


CASES = [
    # ── D  디자인이 깨지는가 ──────────────────────────────────────
    Case("D1", "D", "'데이터 10GB 증정' 혜택을 하나 더 추가해줘. "
         "기존 항목과 같은 구조로 만들어야 한다.",
         tpl=2, block="benefits", expect_items=4, want_text="10GB",
         check_invented=True, check_values=True, allow_new_values=True,
         note="항목 추가 — .benefit-card 를 복제하는가 (출력 811tok, 캡의 53%)"),
    Case("D2", "D", "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.",
         tpl=3, block="benefits", expect_items=2, want_change=True,
         note="결정 ② 삭제 — 남은 카드 구조가 유지되는가"),
    Case("D3", "D", "이 영역의 혜택 문구를 더 짧고 간결하게 다듬어줘. "
         "항목 개수는 그대로 둬라.",
         tpl=4, block="benefits", expect_items=3,
         check_invented=True, check_values=True,
         note="★ v10 무변경 통과 → want_change 로 막음"),

    # ── P  보존 ───────────────────────────────────────────────────
    Case("P1", "P", "이 영역의 버튼 문구를 '지금 응원하기' 로 바꿔줘.",
         tpl=1, block="cta", want_text="지금 응원하기",
         note="cta — data-slot·data-demo-msg·class 가 전부 걸려 있다"),
    Case("P2", "P", "이 영역의 제목을 '사전예약 마지막 기회' 로 바꿔줘.",
         tpl=5, block="hero", want_text="사전예약 마지막 기회",
         note="hero — period 슬롯이 <span> 안에 있다"),
    Case("P3", "P", "이 영역의 소개 문구를 더 힘있게 바꿔줘.",
         tpl=1, block="hero",
         note="★ hero 안에 data-vote 버튼 3개 + id 요소 · v10 무변경 통과 → want_change"),

    # ── H  준 것만 쓰는가 (결정 ④) ────────────────────────────────
    Case("H1", "H", "'영화 관람권 1매' 혜택을 하나 더 추가해줘.",
         tpl=3, block="benefits", expect_items=4, want_text="영화 관람권",
         check_invented=True, check_values=True, allow_new_values=True,
         note="★ 하나를 줬다 — 그 하나만 넣는가, 덤으로 더 지어내는가"),
    Case("H2", "H", "이 영역의 혜택 문구를 더 매력적으로 바꿔줘. "
         "혜택 내용 자체는 바꾸지 마라.",
         tpl=4, block="benefits", expect_items=3,
         check_invented=True, check_values=True,
         note="★ 결정 ④ 의 경계 · v10 무변경 통과 → want_change"),
    Case("H3", "H", "'앱 알림 동의' 단계를 하나 더 추가해줘.",
         tpl=5, block="steps", expect_items=4, want_text="앱 알림",
         note="★ v10 수리 — steps 는 Source.LLM 이라 환각 검사가 꺼진다. "
              "요청 이행만이라도 재도록 want_text·expect_items 를 걸었다"),

    # ── V  값을 바꾸는가 (★ 신규 — 한 번도 안 잰 축) ───────────────
    #
    # ★ 셋 다 **금지를 말하지 않는다.** 실제 사용자는 "숫자 바꾸지 마" 라고
    #   안 한다. 자연스러운 요청에서 값이 버티는지를 봐야 한다.
    #   (H2 는 "바꾸지 마라" 를 명시한 대조군이다 — 말해주면 달라지나?)
    #
    # ★ 셋의 유인이 서로 다르다
    #     V1  부풀리기   "크고 파격적" → 10GB 가 20GB 로              value_changed
    #     V2  탈락       "짧게 요약"   → 압축하며 수치가 떨어져 나감   value_changed
    #     V3  지어내기   "구체적으로"  → 없던 기간·개수를 만들어냄     value_added
    Case("V1", "V", "이 혜택들이 더 크고 파격적으로 들리게 문구를 바꿔줘.",
         tpl=4, block="benefits", expect_items=3,
         check_invented=True, check_values=True,
         note="★ 부풀리기 유인 — 할인율·금액이 버티는가"),
    Case("V2", "V", "이 혜택들을 한 줄씩 짧게 요약해줘.",
         tpl=2, block="benefits", expect_items=3,
         check_invented=True, check_values=True,
         note="★ 탈락 유인 — 압축하면서 수치를 떨어뜨리는가"),
    Case("V3", "V", "이 혜택들을 좀 더 구체적으로 설명해줘.",
         tpl=3, block="benefits", expect_items=3,
         check_invented=True, check_values=True,
         note="★ 지어내기 유인 — 없던 기간·개수를 만들어내는가"),
]


# ── 라우터 케이스 ─────────────────────────────────────────────────
#
# 라우터는 문서를 안 받는다. 사용자 문장 하나만 준다.
#
# ★ 그게 ADD/EDIT 혼동의 원인은 **아니다.** (실측 뒤 정정)
#   `benefits` 는 required=True 라 모든 유효한 문서에 항상 있고,
#   `Block.canCreate()` 가 이미 False 를 돌려준다 — 문서를 볼 필요가 없다.
#   5개 중 ADD 가 말이 되는 건 `steps` 하나뿐이다(유일한 required=False).
#   원인은 **라우터 프롬프트가 그 구분을 안 알려주는 것**이다.
@dataclass
class RouterCase:
    pid: str
    instruction: str
    # 기대: [(op, target, content_가_있어야_하나)] — 요청 순서대로
    expect: list = field(default_factory=list)
    # ★ op 까지 채점하나. 일부 케이스는 **target 만** 보는 게 맞다 — R5 참고.
    check_op: bool = True
    note: str = ""

    group = "R"
    kind = "router"

    def system(self, arm: str = P.MIRROR) -> str:
        return P.router(arm)

    @property
    def user(self) -> str:
        return self.instruction

    @property
    def multi(self) -> bool:
        return len(self.expect) > 1


ROUTER_CASES = [
    RouterCase("R1", "혜택에 '데이터 10GB 증정' 을 하나 추가해줘",
               expect=[("EDIT", "benefits", True)],
               note="단일 + 내용 있음 — content 를 정확히 뽑는가"),
    RouterCase("R2", "혜택 하나 더 추가해줘",
               expect=[("EDIT", "benefits", False)],
               note="★★ 단일 + 내용 **없음** — content=null 을 내는가. "
                    "지어내서 채우면 되묻기는 이 설계로 불가능하다"),
    RouterCase("R3", "제목을 '가을 대축제' 로 바꾸고 혜택도 하나 추가해줘",
               expect=[("EDIT", "hero", True), ("EDIT", "benefits", False)],
               note="★ 복합 — MIRROR 는 op 가 하나뿐이라 **표현 자체가 불가능**하다"),
    RouterCase("R4", "버튼 문구를 '지금 참여' 로 바꾸고 참여 방법도 더 친절하게 다듬어줘",
               expect=[("EDIT", "cta", True), ("EDIT", "steps", False)],
               note="★ 복합 — 한쪽만 내용이 있다"),
    # ★ op 을 안 본다 (2026-09-23 실측으로 고침)
    #   1차 실행에서 mirror 는 EDIT, proposal 은 STYLE 을 냈다 — 같은 요청에
    #   다른 답이 나온 시점에서 케이스가 애매한 것이다("부드럽게" 가 STYLE
    #   어휘와 겹친다).
    #
    #   그런데 이 케이스의 목적은 **"notices 로 분류하는가"** 하나다.
    #   서버 `Block.denyReason(op)` 은 SERVER 블록이면 EDIT·ADD·DELETE 를
    #   **전부 거부**한다. 즉 op 이 뭐든 target 만 맞으면 서버가 막는다.
    #   결정 ③("라우터는 분류만, 거부는 서버") 을 그대로 잰다.
    RouterCase("R5", "유의사항 문구를 좀 부드럽게 바꿔줘",
               expect=[("EDIT", "notices", False)], check_op=False,
               note="결정 ③ — 라우터는 notices 로 **분류만** 한다. "
                    "op 은 안 본다 (서버가 op 무관하게 거부하므로)"),
]

ALL = CASES + ROUTER_CASES
BY_GROUP = {}
for _c in ALL:
    BY_GROUP.setdefault(_c.group, []).append(_c)
BY_PID = {c.pid: c for c in ALL}


def self_check():
    T.self_check()
    P.self_check()

    seen = set()
    for c in ALL:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)

    for c in CASES:
        assert c.group in ("D", "P", "H", "V")
        assert c.tpl and c.block, f"{c.pid} 템플릿/블록 누락"
        assert c.before in c.user, f"{c.pid} 프롬프트에 원본이 안 들어감"
        # 두 arm 다 프롬프트가 만들어져야 한다
        for arm in P.ARMS:
            assert c.system(arm), f"{c.pid}/{arm} 프롬프트 생성 실패"

    for r in ROUTER_CASES:
        assert r.expect, f"{r.pid} 기대값 없음"
        for op, tgt, _ in r.expect:
            assert op in P.ROUTER_OPS, (r.pid, op)
            R.of(tgt)          # 없는 블록이면 여기서 터진다

    # ── 회귀 ① 원본 무변경·무실패 (v4 가 여기서 결과를 통째로 버렸다)
    for c in CASES:
        before = c.before
        assert C.sanitize_edited(before) == before, f"{c.pid}: 정화가 원본을 바꿉니다"
        got = [k for k, _ in C.validate_edited(c.target, before, before)]
        assert not got, f"{c.pid}: 원본이 검증에 걸림 {got}"
        if c.want_text:
            assert c.want_text not in before, f"{c.pid}: want_text 가 원본에 이미 있다"

    # ── 회귀 ② ★ **시킨 대로 한 출력이 통과해야 한다**
    #   v10 은 이걸 안 넣어서 검사 셋이 전부 오탐을 냈고, 그 오탐이
    #   되먹임을 타고 모델을 실제로 망가뜨렸다(D2 시도1 통과 → 시도2·3 훅 전멸).
    import run_v11 as RUN
    d2 = BY_PID["D2"]
    trimmed = C._soup(d2.before)
    trimmed.select(".benefit-card")[-1].decompose()
    got = [k for k, _ in RUN.score(d2, C.sanitize_edited(str(trimmed)))]
    assert not got, f"D2: 마지막 항목을 지운 결과가 불합격 {got}"

    d1 = BY_PID["D1"]
    added = d1.before.replace(
        "</section>",
        '<div class="benefit-card hl-pouch-card">데이터 10GB 증정</div></section>')
    got = [k for k, _ in RUN.score(d1, C.sanitize_edited(added))]
    assert not got, f"D1: 항목을 하나 더한 결과가 불합격 {got}"

    # ── 회귀 ③ ★ v11 의 핵심 — **무변경 통과가 없어야 한다**
    #   v10 은 9개 중 4개가 그냥 통과했다. 하나라도 남으면 안 된다.
    free = [c.pid for c in CASES if not RUN.score(c, c.before)]
    assert not free, (
        f"원본을 그대로 돌려줘도 통과하는 케이스가 남았습니다: {free}\n"
        f"그 케이스의 ✓ 는 '잘했다' 가 아니라 '안 부쉈다' 는 뜻입니다.")

    counts = {g: len(v) for g, v in BY_GROUP.items()}
    assert counts == {"D": 3, "P": 3, "H": 3, "V": 3, "R": 5}, counts
    print(f"  [cases_v11] self_check 통과 — "
          f"D3 · P3 · H3 · V3 · R5  (무변경 통과 0개)")


if __name__ == "__main__":
    self_check()
