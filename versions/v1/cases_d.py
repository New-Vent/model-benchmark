"""
cases_d.py — D군: 환각 방어
============================
담당자만 이 파일을 건드리세요. 다른 군 파일과 절대 충돌 안 납니다.

이 파일이 반드시 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]  ← 반드시 이 이름으로 export
  - self_check(): 선택. 있으면 engine.main() 실행 전에 자동 호출됨.
"""

import re

from engine import Case

DATE_RE = re.compile(
    r"\d{4}\s*년|\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}[-./]\d{1,2}[-./]\d{1,2}"
)
NUM_UNIT_RE = re.compile(r"\d+\s*(GB|MB|원|명|%|개월|회|배)")
PLACEHOLDER_RE = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")

GIVEN_DATES_D2 = {"2026-08-01", "2026-08-31", "2026.08.01", "2026.08.31"}


def _norm_date(m: str) -> str:
    return re.sub(r"[.\s]", "-", m).strip("-")


SYSTEM_D = """너는 통신사 이벤트 페이지를 만드는 도우미다.
<section data-block="이름">...</section> 형태의 HTML 조각만 출력한다.
설명, 인사말, 코드블록 없이 HTML만 출력한다.
"""

SYSTEM_D5 = SYSTEM_D + "\n값을 모르면 그 문장을 통째로 빼라. 대괄호 자리표시자를 쓰지 마라."


def check_d1(raw, html):
    return ["hallucinated_date"] if DATE_RE.search(html) else []


def check_d2(raw, html):
    fails = []
    for m in DATE_RE.findall(html):
        if _norm_date(m) not in GIVEN_DATES_D2:
            fails.append("wrong_date")
            break
    return fails


def check_d3(raw, html):
    return ["invented_benefit"] if NUM_UNIT_RE.search(html) else []


def check_d4_d5(raw, html):
    return ["placeholder"] if PLACEHOLDER_RE.search(html) else []


CASES = [
    Case("D1", "환각방어_기간없음", "D", SYSTEM_D,
         "가을 느낌 나는 멤버십 이벤트 페이지 하나 만들어줘.",
         "html", keep=["hero"], forbid=["notices"],
         extra_check=check_d1),

    Case("D2", "환각방어_기간주어짐", "D", SYSTEM_D,
         "2026.08.01~08.31 여름 데이터 이벤트 페이지 만들어줘.",
         "html", keep=["hero"], forbid=["notices"],
         extra_check=check_d2),

    Case("D3", "환각방어_혜택없음", "D", SYSTEM_D,
         "신규 가입 이벤트 페이지 만들어줘.",
         "html", keep=["hero"], forbid=["notices"],
         extra_check=check_d3),

    Case("D4", "자리표시자_지시없음", "D", SYSTEM_D,
         "브랜드명은 모르니 알아서 이벤트 페이지 만들어줘.",
         "html", keep=["hero"], forbid=["notices"],
         extra_check=check_d4_d5),

    Case("D5", "자리표시자_지시있음", "D", SYSTEM_D5,
         "브랜드명은 모르니 알아서 이벤트 페이지 만들어줘.",
         "html", keep=["hero"], forbid=["notices"],
         extra_check=check_d4_d5, pair="D4"),
]


def self_check():
    # 정규식 자체가 오작동하지 않는지 최소 확인 — 실제 LLM 호출 전에
    # 검출 로직의 결함을 먼저 잡는다.
    assert DATE_RE.search("2026년 8월 1일")
    assert DATE_RE.search("2026-08-01")
    assert not DATE_RE.search("아무 날짜도 없는 문장입니다")

    assert NUM_UNIT_RE.search("데이터 3GB 지급")
    assert not NUM_UNIT_RE.search("데이터를 드립니다")

    assert PLACEHOLDER_RE.search("[브랜드명]을 입력하세요")
    assert not PLACEHOLDER_RE.search("정상적인 문장입니다")

    assert check_d1("", "2026년 8월") == ["hallucinated_date"]
    assert check_d1("", "날짜 없음") == []

    assert check_d2("", "2026-08-01") == []          # 주어진 날짜 그대로
    assert check_d2("", "2026-09-15") == ["wrong_date"]  # 지어낸 날짜

    assert len(CASES) == 5
    for c in CASES:
        assert c.group == "D"
        assert c.extra_check is not None, f"{c.pid}에 extra_check 누락"
