"""
cases_st.py — S-T군: 실제 크기 신규 생성, HTML 노선
=====================================================
v4는 "수정"(S-E vs K-T)만 실제 템플릿 크기로 쟀다 — "생성"(S-T vs J-T)은
출력 토큰이 1,985~2,443으로 html 캡(1536)을 넘어 v4 범위에서 뺐다
(v4 README §"왜 수정 경로만 다루나" 참고).

이 파일은 그 구멍을 채운다. v1의 S군("형태규칙 있음" 신규 생성)과 같은
메커니즘이지만, 요청 문구를 실제 템플릿 5종(template/template_1~5.html)의
주제·분량(혜택 3개·단계 3개)에 맞춰 다시 썼다 — v1 S군의 인공 문서
(370~590자) 대신 실제 제품이 요구하는 분량(약 4,300~5,300자 상당)을
요구한다.

baseline이 없으므로(신규 생성) 클래스 검사는 checks_v4.CONTRACT_CLASSES의
최소 계약(예: hero → ev-block, block-hero)을 쓴다 — 그래서 시스템
프롬프트에 이 클래스 이름을 명시적으로 박아둔다. 안 박아두면 모델이
알 수 없는 클래스 이름을 요구하는 꼴이라 class_lost가 전원 실패로
뜬다(자기 자신도 못 맞추는 기준은 기준이 아니다 — self_check가 이걸
회귀로 잡는다).

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

from engine import Case
from registry import REQUIRED

import checks_v4

GROUPS = ["S-T"]

# 실측(v4 README): 전체 페이지 생성 시 1,985~2,443 tok. html 기본 캡
# 1536으로는 중간에 잘린다 — v3에서 도입한 케이스 단위 오버라이드로
# 전역 NUM_PREDICT는 안 건드리고 이 그룹만 캡을 올린다.
NUM_PREDICT_T = 3072

# checks_v4.CONTRACT_CLASSES와 반드시 같은 값이어야 한다 — 시스템
# 프롬프트에 적은 클래스와 실제 채점 기준이 어긋나면 모델은 못 맞추는
# 기준을 요구받는 셈이다. self_check가 이 동기화를 검증한다.
BLOCK_CLASS_HINT = {
    "hero": "ev-block block-hero",
    "benefits": "ev-block block-benefits",
    "steps": "ev-block block-steps",
    "cta": "ev-block block-cta",
}


def _system() -> str:
    lines = [
        "너는 통신사 이벤트 페이지를 처음부터 만드는 도우미다.",
        "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름" class="..."> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body>, <style>, <script> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라. 설명·인사말·마무리 멘트를 붙이지 마라.",
        "",
        "반드시 만들 영역과 class (디자인이 여기 걸려 있으니 정확히 써라):",
        f'- data-block="hero" class="{BLOCK_CLASS_HINT["hero"]}" — 제목 <h1>, 소개 <p>',
        f'- data-block="benefits" class="{BLOCK_CLASS_HINT["benefits"]}" — <ul><li> 로 혜택 3개',
        f'- data-block="steps" class="{BLOCK_CLASS_HINT["steps"]}" — <ol><li> 로 참여 단계 3개',
        f'- data-block="cta" class="{BLOCK_CLASS_HINT["cta"]}" — <a href="#" class="btn"> 버튼 하나',
        "",
        '만들면 안 되는 영역:',
        '- data-block="notices" 는 절대 만들지 마라. 서버가 관리한다.',
        "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 절대 남기지 마라.",
        "- style=\"...\" 를 넣지 마라. theme- 로 시작하는 클래스를 넣지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


SYSTEM = _system()


def _make_check():
    def _check(raw, html):
        html = html or ""
        # 문서 전체 단위 검사(nested_section·inline_style·theme_leaked).
        # block=""이면 check_product_rules의 class_lost/data_block_changed는
        # 건너뛴다(REQUIRED) — 그건 아래에서 블록별로 따로 본다. 블록 존재
        # 자체는 engine의 기본 check_html(keep=REQUIRED)이 이미 검증한다.
        fails, _ = checks_v4.check_product_rules(html, block="", baseline_html="")

        # 블록별 class 계약 — CONTRACT_CLASSES를 블록 단위로 대조한다.
        # check_product_rules를 블록마다 다시 부르면 위 문서 단위 검사가
        # 중복 집계되므로, class_lost/data_block_changed만 골라 더한다.
        for block in BLOCK_CLASS_HINT:
            b_fails, _ = checks_v4.check_product_rules(html, block=block, baseline_html="")
            for f in ("class_lost", "data_block_changed"):
                if f in b_fails and f not in fails:
                    fails.append(f)
        return fails
    return _check


def _case(pid, kind, prompt):
    return Case(
        pid, kind, "S-T", SYSTEM, prompt, mode="html",
        keep=list(REQUIRED), forbid=["notices"],
        extra_check=_make_check(),
        num_predict=NUM_PREDICT_T,
    )


# 요청 문구는 template/template_1~5.html의 주제를 참고했지만, 그 문서를
# 그대로 베끼라는 게 아니라 같은 분량(혜택 3개·단계 3개)을 요구하는
# "정면 신규 생성" 요청이다. cases_jt.py와 pair를 이루므로, 문구를
# 고칠 때는 반드시 두 파일을 함께 고칠 것.
CASES = [
    _case("ST1", "신규생성_스포츠응원",
          "2026년 프로야구 시즌 응원 이벤트 페이지를 만들어줘. "
          "혜택 3개(굿즈, 할인, 포인트 적립), 참여 방법 3단계를 포함해줘."),
    _case("ST2", "신규생성_명절선물",
          "설 명절 선물 대축제 이벤트 페이지를 만들어줘. "
          "혜택 3개(상품권, 할인 쿠폰, 사은품), 참여 방법 3단계를 포함해줘."),
    _case("ST3", "신규생성_멤버십감사",
          "장기 고객 대상 멤버십 감사 이벤트 페이지를 만들어줘. "
          "혜택 3개(쿠폰, 등급 혜택, 특별 사은품), 참여 방법 3단계를 포함해줘."),
    _case("ST4", "신규생성_플래시세일",
          "24시간 한정 플래시 세일 이벤트 페이지를 만들어줘. "
          "혜택 3개(즉시 할인, 무료배송, 포인트 2배), 참여 방법 3단계를 포함해줘."),
    _case("ST5", "신규생성_사전예약",
          "신제품 사전예약 이벤트 페이지를 만들어줘. "
          "혜택 3개(얼리버드 할인, 한정 굿즈, 우선 출고), 참여 방법 3단계를 포함해줘."),
]


def self_check():
    assert len(CASES) == 5, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "S-T"
        assert c.mode == "html"
        assert c.num_predict == NUM_PREDICT_T, f"{c.pid} num_predict 오버라이드 누락"
        assert c.extra_check is not None

    # 프롬프트에 박아둔 class 힌트가 checks_v4.CONTRACT_CLASSES와
    # 어긋나면, 모델이 지시를 그대로 따라도 class_lost로 떨어진다.
    for block, classes in BLOCK_CLASS_HINT.items():
        contract = checks_v4.CONTRACT_CLASSES.get(block, set())
        for want in contract:
            assert want in classes, (
                f"{block}: 시스템 프롬프트의 class 힌트({classes})에 "
                f"CONTRACT_CLASSES가 요구하는 '{want}'가 없습니다")

    # 회귀 — 계약을 지킨 최소 HTML은 전부 통과해야 한다.
    good = (
        '<section data-block="hero" class="ev-block block-hero">'
        '<h1>제목</h1><p>소개</p></section>'
        '<section data-block="benefits" class="ev-block block-benefits">'
        '<ul><li>혜택1</li><li>혜택2</li><li>혜택3</li></ul></section>'
        '<section data-block="steps" class="ev-block block-steps">'
        '<ol><li>1단계</li><li>2단계</li><li>3단계</li></ol></section>'
        '<section data-block="cta" class="ev-block block-cta">'
        '<a href="#" class="btn">참여하기</a></section>'
    )
    from checks import check_html, extract
    html = extract(good)
    base_fails, _ = check_html(raw=good, html=html, keep=list(REQUIRED),
                                forbid=["notices"], strict_structure=True)
    assert not base_fails, f"최소 계약 HTML이 기본 채점에 걸림: {base_fails}"
    extra_fails = CASES[0].extra_check(good, html)
    assert not extra_fails, f"최소 계약 HTML이 제품 규격 검사에 걸림: {extra_fails}"

    # class를 하나 빼면 잡혀야 한다 (class_lost 회귀)
    broken = good.replace("block-hero", "x")
    broken_html = extract(broken)
    broken_fails = CASES[0].extra_check(broken, broken_html)
    assert "class_lost" in broken_fails, "class 유실을 못 잡음"

    print("  [cases_st] self_check 통과")
