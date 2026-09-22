"""
cases_v10.py — 실제 제품 템플릿으로, 팀 결정을 반영해서 잰다
==============================================================

baseline 이 `template/*.html` 5종이다 (v8·v9 는 `Block.shape` 최소 마크업).

    v8·v9   class 1개 · 블록 ~150자
    v10     class 451건 · 블록 최대 2,229자 · benefits 는 .benefit-card

## 팀 결정 (2026-09-22)

    ① 혜택 항목 추가 가능. 단 정확한 내용이 없으면 되묻는다
    ② 삭제 가능
    ③ 라우터는 분류만, 거부는 서버가 한다
    ④ **요청하지 않은 것을 추가하거나 내용을 바꾸면 안 된다**

★ ①(되묻기)은 **v10 에서 안 잰다.** 어디서 어떻게 구현할지 백엔드가 아직
  안 정했고, 벤치마크가 앞서 나가면 "서비스가 하지 않는 일"을 재게 된다
  (v4 가 그 실수로 결과를 통째로 버렸다). 설계가 정해진 뒤 새 버전에서 잰다.

  그래서 **모든 케이스는 "내용이 주어진" 상태를 전제**한다 — 되묻기 상황은
  아예 만들지 않는다.

④는 H군이 그대로 잰다.

## 세 군

    D  Design     must 는 통과하는데 깨지는가    ← 아무도 못 잡던 구멍
    P  Preserve   class·slot·id·훅이 남는가
    H  Halluc     ④ — 준 것만 쓰는가
"""

from dataclasses import dataclass

import checks_v10 as C
import prompts_v10 as P
import registry_v10 as R
import templates_v10 as T


@dataclass
class Case:
    pid: str
    group: str                  # D | P | H
    instruction: str
    tpl: int = 0
    block: str = ""
    mode: str = "html"
    want_text: str = ""
    expect_items: int | None = None
    check_invented: bool = False
    note: str = ""

    @property
    def target(self) -> R.Block:
        return R.of(self.block)

    @property
    def before(self) -> str:
        return T.block_html(self.tpl, self.block)

    @property
    def system(self) -> str:
        return P.edit(self.target)

    @property
    def user(self) -> str:
        return f"{self.instruction}\n\n{self.before}"



CASES = [
    # ── D  디자인이 깨지는가 ──────────────────────────────────────
    #
    # ★ shape 는 "<ul> 안에 <li>" 라고 시키는데 템플릿은 .benefit-card 다.
    #   must 가 `"ul li, .benefit-card"` 로 둘 다 받으므로, 모델이 shape 대로
    #   <li> 로 바꿔도 must 는 통과한다. 백엔드 classMap 도 못 잡는다
    #   (.benefit-card 엔 id·data-slot 이 없어 이름표가 없다). CSS 만 안 먹는다.
    #
    # ★ 전부 **내용을 준다** — 되묻기는 라우터가 걸러서 여기까지 안 온다.
    Case("D1", "D", "'데이터 10GB 증정' 혜택을 하나 더 추가해줘. "
         "기존 항목과 같은 구조로 만들어야 한다.",
         tpl=2, block="benefits", expect_items=4,
         # ★ want_text 는 **수치**로 둔다. 실측으로 고친 것 —
         #   "데이터 10GB 증정" 정확 일치를 요구했더니 두 모델 다 3회씩
         #   실패했는데, 출력을 보면 시킨 대로 했다:
         #     gemma "녹색 복주머니 · 데이터 10GB · ... 데이터 추가 증정"
         #     haiku "은색 복주머니 · 데이터 10GB · ... 추가 무료 충전"
         #   "기존 항목과 같은 구조로" 라고 시켜놓고 문장을 그대로 박으라는 건
         #   모순이다. 실체는 수치이므로 그것만 본다.
         want_text="10GB", check_invented=True,
         note="★ 항목 추가 — .benefit-card 를 복제하는가 (출력 811tok, 캡의 53%)"),
    Case("D2", "D", "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.",
         tpl=3, block="benefits", expect_items=2,
         note="결정 ② 삭제 — 남은 카드 구조가 유지되는가"),
    Case("D3", "D", "이 영역의 혜택 문구를 더 짧고 간결하게 다듬어줘. "
         "항목 개수는 그대로 둬라.",
         tpl=4, block="benefits", expect_items=3,
         note="문구만 — 구조를 건드릴 이유가 전혀 없는 요청"),

    # ── P  보존 ───────────────────────────────────────────────────
    Case("P1", "P", "이 영역의 버튼 문구를 '지금 응원하기' 로 바꿔줘.",
         tpl=1, block="cta", want_text="지금 응원하기",
         note="cta — data-slot·data-demo-msg·class 가 전부 걸려 있다"),
    Case("P2", "P", "이 영역의 제목을 '사전예약 마지막 기회' 로 바꿔줘.",
         tpl=5, block="hero", want_text="사전예약 마지막 기회",
         note="hero — period 슬롯이 <span> 안에 있다"),
    Case("P3", "P", "이 영역의 소개 문구를 더 힘있게 바꿔줘.",
         tpl=1, block="hero",
         note="★ hero 안에 data-vote 버튼이 3개 — 블록 경계가 단순하지 않다"),

    # ── H  준 것만 쓰는가 (결정 ④) ────────────────────────────────
    #
    # v8 E3 에서 네 모델 전부 없는 혜택을 지어냈는데(gemma 는 통신 이벤트에
    # "무료 배송 서비스") 항목 수만 세느라 전부 통과했다.
    # 결정 ④ 이후로는 **준 것 하나만** 넣어야 한다.
    Case("H1", "H", "'영화 관람권 1매' 혜택을 하나 더 추가해줘.",
         tpl=3, block="benefits", expect_items=4,
         want_text="영화 관람권", check_invented=True,
         note="★ 하나를 줬다 — 그 하나만 넣는가, 덤으로 더 지어내는가"),
    Case("H2", "H", "이 영역의 혜택 문구를 더 매력적으로 바꿔줘. "
         "혜택 내용 자체는 바꾸지 마라.",
         tpl=4, block="benefits", expect_items=3, check_invented=True,
         note="★ 결정 ④ 의 경계 — 문구는 고치되 수치는 그대로여야 한다"),
    Case("H3", "H", "'앱 알림 동의' 단계를 하나 더 추가해줘.",
         tpl=5, block="steps", check_invented=True,
         note="steps 는 Source.LLM — benefits 와 규칙이 같은가"),
]

BY_GROUP = {}
for c in CASES:
    BY_GROUP.setdefault(c.group, []).append(c)


def self_check():
    T.self_check()
    P.self_check()

    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group in ("D", "P", "H")
        assert c.tpl and c.block, f"{c.pid} 템플릿/블록 누락"
        assert c.before in c.user, f"{c.pid} 프롬프트에 원본이 안 들어감"

    # ★ 회귀 — v4 가 여기서 결과를 통째로 버렸다.
    #   원본을 그대로 돌려주면 (a) 정화가 안 바꾸고 (b) 검증이 통과해야 한다.
    for c in CASES:
        before = c.before
        cleaned = C.sanitize_edited(before)
        assert cleaned == before, (
            f"{c.pid}: 정화가 원본을 바꿉니다 — 백엔드 keepInteractive 가 "
            f"머지됐는지 확인하세요 ({len(before)}자 → {len(cleaned)}자)")
        got = [code for code, _ in C.validate_edited(c.target, before, before)]
        assert not got, f"{c.pid}: 원본이 검증에 걸림 {got}"
        if c.want_text:
            assert c.want_text not in before, f"{c.pid}: want_text 가 원본에 이미 있다"

    # ★★ 회귀 — **시킨 대로 한 출력**이 통과해야 한다.
    #   "원본 무변경" 만 보고 이걸 안 봐서 검사 셋이 전부 오탐을 냈다.
    #   더 나쁜 건, 그 오탐이 되먹임을 타고 들어가 모델을 실제로 망가뜨렸다는
    #   것이다(D2 시도1 통과 → 시도2·3 에서 훅 전멸). v4 에서 겪은 것과 같다.
    import run_v10 as RUN
    d2 = next(c for c in CASES if c.pid == "D2")
    trimmed = C._soup(d2.before)
    trimmed.select(".benefit-card")[-1].decompose()
    got = [k for k, _ in RUN.score(d2, C.sanitize_edited(str(trimmed)))]
    assert not got, f"D2: 마지막 항목을 지운 결과가 불합격 {got}"

    d1 = next(c for c in CASES if c.pid == "D1")
    added = d1.before.replace(
        "</section>",
        '<div class="benefit-card hl-pouch-card">데이터 10GB 증정</div></section>')
    got = [k for k, _ in RUN.score(d1, C.sanitize_edited(added))]
    assert not got, f"D1: 항목을 하나 더한 결과가 불합격 {got}"

    counts = {g: len(v) for g, v in BY_GROUP.items()}
    assert counts == {"D": 3, "P": 3, "H": 3}, counts
    print(f"  [cases_v10] self_check 통과 — "
          f"D {counts['D']} · P {counts['P']} · H {counts['H']}")


if __name__ == "__main__":
    self_check()
