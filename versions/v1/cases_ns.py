"""
cases_ns.py — N/S군: 순수 HTML 생성 (형태규칙 없음/있음)
=========================================================
담당자(예: A)만 이 파일을 건드리세요.

이 파일이 반드시 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

from engine import Case
from registry import LLM_BLOCKS, SERVER_BLOCKS, REQUIRED


def build_system(with_shape: bool) -> str:
    lines = [
        "너는 통신사 이벤트 페이지를 만드는 도우미다.",
        "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body>, <style>, <script> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명, 인사말, 마무리 멘트를 붙이지 마라.",
        "",
        "만들 영역:",
    ]
    for b in LLM_BLOCKS:
        tail = "" if b.required else "  (선택)"
        line = f'- data-block="{b.key}" : {b.desc}{tail}'
        if with_shape and b.shape:
            line += f"\n    형태: {b.shape}"
        lines.append(line)
    if SERVER_BLOCKS:
        lines += ["", "만들면 안 되는 영역:"]
        for b in SERVER_BLOCKS:
            lines.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')
    if with_shape:
        lines += ["", "태그를 반드시 쓴다. 맨 텍스트만 두지 마라."]
    lines += [
        "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 절대 남기지 마라.",
        "- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


SYSTEM_PLAIN = build_system(with_shape=False)
SYSTEM_SHAPE = build_system(with_shape=True)

P1 = ("2026년 8월 1일부터 8월 31일까지 신규 가입자에게 데이터 쿠폰 3GB를 주는 "
      "이벤트 페이지를 만들어줘.")
P2 = "가을 느낌 나는 멤버십 이벤트 페이지 하나 만들어줘."
P8 = ("10만원 상품권을 추첨 증정하는 이벤트 페이지를 만들어줘. "
      "혜택 3개, 참여방법 3단계를 포함해줘.")
P9 = ("여름 시즌에 맞춰 시원한 느낌으로 만들어줘. 20대 타겟이고, "
      "데이터 혜택 위주로 가되 혜택은 3개만. 참여 방법은 2단계로 간결하게. "
      "기간은 2026년 8월 1일 ~ 8월 31일.")


def check_p9_counts(raw, html):
    """P9(긴 서술형)의 '지시 여러 개 동시 준수' 여부 — 담당자가
    실제 렌더링 결과를 보고 개수를 세는 방식으로 구현 예정.
    지금은 뼈대만 — BeautifulSoup으로 실제 li 개수를 세도록 채울 것."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    fails = []
    benefits = soup.select_one('[data-block="benefits"]')
    if benefits and len(benefits.select("li")) != 3:
        fails.append("exact_benefits_3_fail")
    steps = soup.select_one('[data-block="steps"]')
    if steps and len(steps.select("li")) != 2:
        fails.append("exact_steps_2_fail")
    return fails


CASES = [
    Case("N2", "정보부족_형태규칙없음", "N", SYSTEM_PLAIN, P2, "html",
         keep=list(REQUIRED), forbid=["notices"]),
    Case("N9", "긴서술형_형태규칙없음", "N", SYSTEM_PLAIN, P9, "html",
         keep=list(REQUIRED), forbid=["notices"], extra_check=check_p9_counts),

    Case("S1", "신규생성_형태규칙", "S", SYSTEM_SHAPE, P1, "html",
         keep=list(REQUIRED), forbid=["notices"], pair="J1"),
    Case("S2", "정보부족_형태규칙", "S", SYSTEM_SHAPE, P2, "html",
         keep=list(REQUIRED), forbid=["notices"], pair="J2"),
    Case("S8", "긴출력_형태규칙", "S", SYSTEM_SHAPE, P8, "html",
         keep=list(REQUIRED), forbid=["notices"], pair="J8"),
    Case("S9", "긴서술형_형태규칙", "S", SYSTEM_SHAPE, P9, "html",
         keep=list(REQUIRED), forbid=["notices"], extra_check=check_p9_counts, pair="J9"),
]


def self_check():
    for b in LLM_BLOCKS:
        assert bool(b.shape) == bool(b.must), f"{b.key}: shape와 must가 짝이 아님"
        assert b.shape in SYSTEM_SHAPE, f"{b.key}: shape가 프롬프트에 없음"
    assert len(CASES) == 6
    for c in CASES:
        assert c.group in ("N", "S")
        assert c.mode == "html"
