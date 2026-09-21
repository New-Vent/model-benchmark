"""util.py — playground 공용 헬퍼: 세션 폴더, 전체 HTML 문서 래핑."""
import datetime
import json
import os
import re

_FENCE = re.compile(r"```(?:json)?")


def parse_json_output(raw: str) -> dict:
    """LLM 응답에서 JSON 객체만 뽑는다 — 코드펜스가 섞여 나와도 처리."""
    text = _FENCE.sub("", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"응답에서 JSON을 못 찾음:\n{raw}")
    return json.loads(text[start:end + 1])

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def new_session_dir(label: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{stamp}_{label}")
    os.makedirs(path, exist_ok=True)
    return path


def wrap_full_html(fragment: str, title: str = "playground") -> str:
    """versions/*의 케이스들은 <html>/<body> 태그를 LLM이 못 쓰게 막는다
    (마크업은 서버 소유) — 그래서 render_plan/assemble_page의 결과는
    <body> 안에 들어갈 조각뿐이다. 브라우저로 눈으로 확인하려면 이
    조각을 문서로 감싸야 하는데, 이건 채점 대상이 아니라 순수하게
    playground에서 보기 편하라고 추가하는 래퍼다."""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
{fragment}
</body>
</html>"""


def wrap_with_css(fragment: str, css_text: str, title: str = "playground", theme: str = "") -> str:
    """template_loader로 불러온 실제 템플릿 미리보기 전용 — event.css를
    <style>로 그대로 인라인한다(iframe srcdoc은 about:srcdoc 출처라
    상대경로 <link>가 서버 파일을 못 찾으므로 인라인이 제일 간단하다).
    fragment는 templates.container()의 결과라 <div class="ev-container">
    가 이미 포함돼 있으므로 여기서 또 감싸지 않는다.

    theme(예: "theme-sports")를 반드시 <body>에 붙여야 한다 — event.css의
    색상·레이아웃 규칙 대부분이 ".theme-sports .sp-hero"처럼 body의
    theme-* 클래스에 스코프돼 있다(event.css 상단 주석). 이걸 안 붙이면
    템플릿 5개가 전부 테마 없는 기본값으로 나와 똑같아 보인다."""
    body_class = f' class="{theme}"' if theme else ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css_text}
</style>
</head>
<body{body_class}>
{fragment}
</body>
</html>"""


def save_step(session_dir: str, step_no: int, label: str, plan: dict, html_fragment: str):
    base = os.path.join(session_dir, f"{step_no:02d}_{label}")
    with open(base + ".plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(wrap_full_html(html_fragment, title=label))
    return base + ".html"
