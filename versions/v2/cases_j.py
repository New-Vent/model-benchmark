"""
cases_j.py — J군: 조합 계획 JSON
=================================
담당자(예: B)만 이 파일을 건드리세요.

이 파일이 반드시 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택

※ J/K만 쓰는 축소판 패키지에서는 이 파일이 cases_ns.py에 의존하지
  않도록 프롬프트를 자체적으로 갖고 있다(P1/P2/P8/P9). 원래 전체
  패키지에서는 N/S와 요청 문구를 동일하게 맞춰 공정 비교하는 게
  목적이었는데, 여기서는 J군 자체 검증용으로만 쓴다.
"""

from engine import Case
from registry import LLM_BLOCKS, SERVER_BLOCKS, REQUIRED, build_plan_json_schema

P1 = ("2026년 8월 1일부터 8월 31일까지 신규 가입자에게 데이터 쿠폰 3GB를 주는 "
      "이벤트 페이지를 만들어줘.")
P2 = "가을 느낌 나는 멤버십 이벤트 페이지 하나 만들어줘."
P8 = ("10만원 상품권을 추첨 증정하는 이벤트 페이지를 만들어줘. "
      "혜택 3개, 참여방법 3단계를 포함해줘.")
P9 = ("여름 시즌에 맞춰 시원한 느낌으로 만들어줘. 20대 타겟이고, "
      "데이터 혜택 위주로 가되 혜택은 3개만. 참여 방법은 2단계로 간결하게. "
      "기간은 2026년 8월 1일 ~ 8월 31일.")


def check_p9_counts(raw, html):
    """P9(긴 서술형)의 '지시 여러 개 동시 준수' 여부 확인."""
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


def build_plan_system() -> str:
    lines = [
        "너는 이벤트 페이지의 구성을 정하는 도우미다.",
        "HTML 을 만들지 마라. 아래 형식의 JSON 만 출력한다.",
        "",
        "사용할 수 있는 블록과 변형:",
    ]
    for b in LLM_BLOCKS:
        req = "필수" if b.required else "선택"
        for v in b.variants:
            lines.append(f'- type="{b.key}" variant="{v.name}" ({req}) — {v.desc}, '
                         f'필요한 값: {", ".join(v.fields)}')
    example_hero = next((v.name for b in LLM_BLOCKS if b.key == "hero" for v in b.variants), "a")
    example_benefits = next((v.name for b in LLM_BLOCKS if b.key == "benefits" for v in b.variants), "list")
    example_cta = next((v.name for b in LLM_BLOCKS if b.key == "cta" for v in b.variants), "primary")
    lines += [
        "",
        "출력 형식:",
        '{"blocks":[',
        f'  {{"type":"hero","variant":"{example_hero}","title":"제목","sub":"한 줄 소개"}},',
        f'  {{"type":"benefits","variant":"{example_benefits}","items":["혜택1","혜택2"]}},',
        f'  {{"type":"cta","variant":"{example_cta}","label":"버튼 문구"}}',
        "]}",
        "",
        "규칙:",
        "- blocks 는 화면에 나타날 순서대로 넣는다.",
        f"- 필수 블록: {', '.join(b.key for b in LLM_BLOCKS if b.required)}",
        "- items 는 문자열 배열이며 2개 이상 4개 이하.",
        f"- {', '.join(b.key for b in SERVER_BLOCKS)} 는 넣지 마라. 서버가 채운다.",
        "- 사용자 요청에 명시적으로 언급되지 않은 선택 블록"
        f"({', '.join(b.key for b in LLM_BLOCKS if not b.required)})은 "
        "추가하지 마라. 필요하지도 않은데 넣었다가 필드를 다 못 채우면 실패로 처리된다.",
        "- 날짜를 만들지 마라. 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 쓰지 마라. 이모지를 쓰지 마라.",
        "- JSON 외에는 아무것도 출력하지 마라.",
    ]
    return "\n".join(lines)


SYSTEM_PLAN = build_plan_system()
PLAN_SCHEMA = build_plan_json_schema()

CASES = [
    Case("J1", "신규생성_조합계획", "J", SYSTEM_PLAN, P1, "plan",
         keep=list(REQUIRED), forbid=["notices"], pair="S1", json_schema=PLAN_SCHEMA),
    Case("J2", "정보부족_조합계획", "J", SYSTEM_PLAN, P2, "plan",
         keep=list(REQUIRED), forbid=["notices"], pair="S2", json_schema=PLAN_SCHEMA),
    Case("J8", "긴출력_조합계획", "J", SYSTEM_PLAN, P8, "plan",
         keep=list(REQUIRED), forbid=["notices"], pair="S8", json_schema=PLAN_SCHEMA),
    Case("J9", "긴서술형_조합계획", "J", SYSTEM_PLAN, P9, "plan",
         keep=list(REQUIRED), forbid=["notices"], extra_check=check_p9_counts, pair="S9",
         json_schema=PLAN_SCHEMA),
]


def self_check():
    for b in LLM_BLOCKS:
        for v in b.variants:
            assert f'variant="{v.name}"' in SYSTEM_PLAN, f"{b.key}/{v.name} 누락"
    assert len(CASES) == 4
    for c in CASES:
        assert c.group == "J"
        assert c.mode == "plan"
        assert c.pair, f"{c.pid}는 N/S와 짝(pair)이 지정돼야 공정 비교가 됨"
        assert c.json_schema is not None, (
            f"{c.pid}에 json_schema가 없음 — format='json'(느슨한 검증)으로만 "
            f"돌면 unknown_type/unknown_variant/missing_필드 실패가 실측으로 "
            f"확인된 만큼 반드시 스키마를 넣어야 함")
    # 스키마 자체가 최소한의 구조를 갖췄는지
    assert PLAN_SCHEMA["type"] == "object"
    assert "blocks" in PLAN_SCHEMA["properties"]
    assert PLAN_SCHEMA["additionalProperties"] is False
