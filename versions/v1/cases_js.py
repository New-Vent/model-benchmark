"""
cases_js.py — JS군: 인터랙션 생성 — 부분 구현, 담당자가 마무리 필요
======================================================================
담당자만 이 파일을 건드리세요.

## 배경 (planning.md §7 JS군 참고)

기본 설계 방향은 "서버 컴포넌트"다 (registry.py의 countdown/tabs/faq가
이미 그 결과물). 이 파일의 JS1~JS3 케이스는 "그래도 LLM에게 직접 JS를
맡기면 어떻게 되는지 재본다"는 대조 실험이다 — 위험해 보여서 안 한 게
아니라 재봤더니 이랬다는 근거를 만드는 것이 목적.

|      | 요청 |
|------|------|
| JS1  | "이벤트 종료까지 남은 시간을 보여주는 카운트다운을 넣어줘" |
| JS2  | "유의사항을 접었다 펼 수 있게 해줘" |
| JS3  | "참여 버튼을 누르면 확인 메시지가 뜨게 해줘" |

**실행하지 않고 구조만 본다** — 아래 정규식 검사는 이미 구현되어
있으니 그대로 쓰면 된다.

## 아직 해야 할 것 (TODO)

1. SYSTEM_JS 프롬프트 다듬기 (지금은 초안) — "<script> 태그를 써도
   된다"고 명시적으로 허용해야 하고(다른 군은 전부 금지), 그 외
   규칙(설명 금지 등)은 기존 군과 동일하게 유지.
2. CASES 리스트 채우기 (지금은 비어있음) — 아래 SYSTEM_JS와
   check_js_structure를 사용해 Case 3개(JS1~JS3) 생성.
   allow_script=True를 반드시 지정할 것 (안 하면 check_html이
   <script> 자체를 bad_tag로 잡아버림).
3. self_check() 채우기 — 정규식이 실제로 정상/비정상 JS를
   구분하는지 최소 1개씩 검증 예시 추가 (cases_d.py의 self_check
   패턴 참고).
4. (선택, 시간 되면) raw_v1/에 저장된 결과 몇 개를 브라우저로 직접
   열어서 눈으로 확인 — 카운트다운의 날짜 계산이 실제로 맞는지는
   정규식으로 못 잡는다.

## 이미 구현된 것 — 그대로 가져다 쓰면 됨
"""

import re

from engine import Case

JS_TODO_RE = re.compile(r"//\s*(TODO|여기에|구현|작성)|\.\.\.")


def check_js_structure(raw, html):
    """
    구조만 보고 실행은 안 한다.
      js_empty        <script>가 있는데 내용이 비어 있음
      js_no_code      addEventListener/function/const가 하나도 없음
      js_todo         미완성 표시가 남아 있음
      js_unbalanced   중괄호·괄호 짝이 안 맞음
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

    if not re.search(r"addEventListener|function\s|=>\s*{|const\s|let\s", js_code):
        fails.append("js_no_code")

    if JS_TODO_RE.search(js_code):
        fails.append("js_todo")

    if js_code.count("{") != js_code.count("}") or js_code.count("(") != js_code.count(")"):
        fails.append("js_unbalanced")

    return fails


# TODO(JS군 담당자): allow_script=True를 명시하는 프롬프트로 다듬으세요.
SYSTEM_JS = """너는 통신사 이벤트 페이지에 인터랙션을 추가하는 도우미다.
이번 요청에 한해서는 <script> 태그 사용이 허용된다.

출력 규칙:
- <section data-block="이름"> ... </section> 안에 필요하면 <script>를 포함해 출력한다.
- <html>, <head>, <body>, <style> 태그는 여전히 쓰지 마라.
- 코드블록으로 감싸지 마라. 설명/인사말 없이 결과만 출력하라.
"""

# TODO: 아래 3개 요청으로 Case를 만들어 CASES에 채우세요.
# 예시:
# CASES = [
#     Case("JS1", "카운트다운_직접생성", "JS", SYSTEM_JS,
#          "이벤트 종료까지 남은 시간을 보여주는 카운트다운을 넣어줘.",
#          "html", keep=[], forbid=["notices"],
#          allow_script=True, extra_check=check_js_structure),
#     Case("JS2", "아코디언_직접생성", "JS", SYSTEM_JS,
#          "유의사항을 접었다 펼 수 있게 해줘.",
#          "html", keep=[], forbid=["notices"],
#          allow_script=True, extra_check=check_js_structure),
#     Case("JS3", "확인메시지_직접생성", "JS", SYSTEM_JS,
#          "참여 버튼을 누르면 확인 메시지가 뜨게 해줘.",
#          "html", keep=[], forbid=["notices"],
#          allow_script=True, extra_check=check_js_structure),
# ]
# 아직 CASES가 비어 있는 스텁이라 run.py가 군 이름을 못 찾는다.
# GROUPS를 선언해두면 `python base/run.py v1 JS` 로 지정은 할 수 있다
# (스크립트 직접 생성 — 구현되면 이 줄은 지워도 CASES에서 자동으로 뽑힌다).
GROUPS = ["JS"]

CASES: list = []


def self_check():
    # TODO: CASES를 채운 뒤 아래를 채우세요.
    # assert len(CASES) == 3
    # for c in CASES:
    #     assert c.allow_script is True, f"{c.pid}는 allow_script=True가 필요"

    # 정규식 자체는 지금 바로 검증 가능 (CASES가 비어있어도 이 부분은 통과해야 함)
    assert check_js_structure("", '<div><script>function f(){}</script></div>') == []
    assert "js_empty" in check_js_structure("", "<div><script></script></div>")
    assert "js_missing_script_tag" in check_js_structure("", "<div>스크립트 없음</div>")
    assert "js_todo" in check_js_structure(
        "", '<div><script>function f(){ // TODO 구현 }</script></div>')
    assert "js_unbalanced" in check_js_structure(
        "", '<div><script>function f(){ if(true) { }</script></div>')
