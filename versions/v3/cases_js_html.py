"""
cases_js_html.py — JS-HTML군: LLM이 <script> 코드를 직접 작성
================================================================
v3 README §2의 3-way 비교(JS-HTML vs JS-PLAN vs JS-PATCH) 중 "LLM이
인터랙션 코드를 직접 쓰게 하면 어떻게 되는가"를 재는 대조군이다.

v1/cases_js.py는 이 군의 스텁(SYSTEM_JS·check_js_structure만 있고
CASES는 비어있었음)이었다. 원본 versions/v1/benchmark_v1.py에는 이미
JS1~JS3이 구현·실행까지 돼 있었으므로(93%/68%/95%, v3 README §1 근거),
그 완성본을 이 파일로 그대로 이식한다 — v1 스텁을 고치지 않고 v3에
새로 두는 이유는 NUM_PREDICT 오버라이드(§5)처럼 v3에서만 유효한 조건을
얹기 위해서다(v1 파일은 v1이 실제로 실행됐을 때의 조건을 그대로 보존).

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

import re

from engine import Case

# v1 cases_e.py / benchmark_v1.py의 SHORT_DOC과 글자 그대로 동일해야
# 결과가 다른 버전 대비 참고 가능하다 — 프롬프트를 고칠 때는 반드시
# 세 파일(v1/cases_e.py, v1/benchmark_v1.py, 이 파일)을 다 확인할 것.
SHORT_DOC = """<section data-block="hero">
  <h1>여름 데이터 대방출</h1>
  <p>이번 여름 데이터 걱정 없이 마음껏 즐기세요</p>
</section>
<section data-block="benefits">
  <h2>혜택</h2>
  <ul><li>데이터 3GB 즉시 지급</li><li>월 요금 30% 할인</li></ul>
</section>
<section data-block="cta">
  <a href="#" class="btn">가입하기</a>
</section>"""

# 스크립트를 어디에 둘지 알려준다 — 없으면 모델이 <html><head><script>를
# 만든다(모델의 한계가 아니라 지시 누락이므로 명시한다).
JS_RULE = ("\n\n동작을 구현하는 <script> 는 마지막 <section> 안에 넣어라. "
           "<html>, <head>, <body> 를 만들지 마라. 나머지 영역은 그대로 유지해라.")

SYSTEM_JS = """너는 통신사 이벤트 페이지에 인터랙션을 추가하는 도우미다.
이번 요청에 한해서는 <script> 태그 사용이 허용된다.

출력 규칙:
- <section data-block="이름"> ... </section> 안에 필요하면 <script>를 포함해 출력한다.
- <html>, <head>, <body>, <style> 태그는 여전히 쓰지 마라.
- 코드블록으로 감싸지 마라. 설명/인사말 없이 결과만 출력하라.
- 요청받지 않은 영역(hero/benefits/cta)의 텍스트·속성은 그대로 유지한다.
- 대괄호 자리표시자를 남기지 마라. 이모지를 쓰지 마라."""

JS_TODO_RE = re.compile(r"//\s*(TODO|여기에|구현|작성)|\.\.\.")

# v3의 NUM_PREDICT 방침 (README §5) — html 모드 캡을 3072로 케이스
# 단위 오버라이드한다. 전역 NUM_PREDICT는 건드리지 않는다(engine.py
# Case.num_predict 참고 — v1·v2는 영향 없음).
V3_NUM_PREDICT_HTML = 3072


def check_js_structure(raw, html):
    """
    구조만 보고 실행은 안 한다(브라우저 실행 없이 정적 검사만).
      js_missing_script_tag  <script> 자체가 없음
      js_empty                <script>가 있는데 내용이 비어 있음
      js_no_code              addEventListener/function/const 등이 하나도 없음
      js_todo                 미완성 표시가 남아 있음
      js_unbalanced           중괄호·괄호 짝이 안 맞음
    """
    fails = []
    m = re.search(r"<script[^>]*>(.*?)</script>", html, re.S)
    if not m:
        fails.append("js_missing_script_tag")
        return fails

    js_code = m.group(1).strip()
    if not js_code:
        fails.append("js_empty")
        return fails

    if not re.search(r"addEventListener|function\s|=>\s*{|const\s|let\s|var\s", js_code):
        fails.append("js_no_code")
    if JS_TODO_RE.search(js_code):
        fails.append("js_todo")
    if js_code.count("{") != js_code.count("}") or js_code.count("(") != js_code.count(")"):
        fails.append("js_unbalanced")

    return fails


def check_js_or_details(raw, html):
    """JS2(접기펼치기) 전용 — details/summary 네이티브 구현도 정답으로
    인정한다. details가 있으면 그 안에 혜택 목록 li들이 실제로 들어갔는지
    확인하고(details_wrong_target), details가 아예 없으면 check_js_structure로
    폴백해 <script> 기반 구현을 검사한다."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    details_tags = soup.find_all("details")
    if details_tags:
        benefits = soup.select_one('[data-block="benefits"]')
        items = benefits.select("ul li") if benefits else []
        if benefits and items:
            for detail in details_tags:
                summary = detail.find("summary", recursive=False)
                if (summary and summary.get_text(strip=True)
                        and all(detail in item.parents and summary not in item.parents
                                for item in items)):
                    return []
        return ["details_wrong_target"]
    return check_js_structure(raw, html)


CASES = [
    Case("JSHTML1", "카운트다운_직접생성", "JS-HTML", SYSTEM_JS,
         "다음 HTML에 이벤트 종료까지 남은 시간을 보여주는 카운트다운을 넣어줘. "
         f"종료일은 2026년 8월 31일이야.{JS_RULE}\n\n{SHORT_DOC}",
         "html", keep=["hero", "benefits", "cta"], forbid=["notices"],
         allow_script=True, extra_check=check_js_structure,
         num_predict=V3_NUM_PREDICT_HTML),

    # 접기/펼치기는 <details><summary>로도 됨 — 둘 다 정답으로 본다.
    Case("JSHTML2", "접기펼치기_직접생성", "JS-HTML", SYSTEM_JS,
         "다음 HTML에서 혜택 목록을 접었다 펼 수 있게 해줘. "
         f"details/summary를 사용하면 script는 없어도 된다.{JS_RULE}\n\n{SHORT_DOC}",
         "html", keep=["hero", "benefits", "cta"], forbid=["notices"],
         allow_script=True, extra_check=check_js_or_details,
         num_predict=V3_NUM_PREDICT_HTML),

    Case("JSHTML3", "확인메시지_직접생성", "JS-HTML", SYSTEM_JS,
         f"다음 HTML에서 참여 버튼을 누르면 확인 메시지가 뜨게 해줘.{JS_RULE}\n\n{SHORT_DOC}",
         "html", keep=["hero", "benefits", "cta"], forbid=["notices"],
         allow_script=True, extra_check=check_js_structure,
         num_predict=V3_NUM_PREDICT_HTML),
]


def self_check():
    assert check_js_structure("", '<div><script>function f(){}</script></div>') == []
    assert "js_empty" in check_js_structure("", "<div><script></script></div>")
    assert "js_missing_script_tag" in check_js_structure("", "<div>스크립트 없음</div>")
    assert "js_todo" in check_js_structure(
        "", '<div><script>function f(){ // TODO 구현 }</script></div>')
    assert "js_unbalanced" in check_js_structure(
        "", '<div><script>function f(){ if(true) { }</script></div>')

    # benefits 섹션 자체를 details로 감싼 정상 구조는 통과해야 함
    wrapped = ('<section data-block="benefits"><details><summary>혜택 보기</summary>'
               '<ul><li>a</li><li>b</li></ul></details></section>')
    assert check_js_or_details("", wrapped) == []
    # details는 있지만 li를 감싸지 않은 엉뚱한 위치 — 잡아내야 함
    misplaced = ('<section data-block="benefits"><ul><li>a</li><li>b</li></ul></section>'
                 '<details><summary>딴 얘기</summary><p>내용</p></details>')
    assert "details_wrong_target" in check_js_or_details("", misplaced)
    assert check_js_or_details("", "<div>아무 구현 없음</div>") == ["js_missing_script_tag"]

    assert len(CASES) == 3
    for c in CASES:
        assert c.group == "JS-HTML"
        assert c.mode == "html"
        assert c.allow_script is True, f"{c.pid}는 allow_script=True가 필요"
        assert c.num_predict == V3_NUM_PREDICT_HTML, f"{c.pid}에 v3 num_predict 오버라이드 누락"
        assert JS_RULE.strip() in c.prompt or JS_RULE in c.prompt
