"""
core.py — generate.py/edit.py/app.py(GUI)가 공유하는 핵심 로직.
CLI와 GUI가 같은 함수를 쓰므로, GUI에서 나온 결과와 CLI에서 나온 결과는
항상 동일하다(두 곳에 로직을 따로 유지하지 않음).
"""
import json

from bs4 import BeautifulSoup

from backend import call
from schemas import PLAN_SCHEMA, PATCH_SCHEMA
from util import parse_json_output
from registry import render_plan, render_theme_style, THEME_DEFAULTS
from checks import apply_patch, extract
from edit_lib import block_of, replace_block, build_block_edit_system

# v5 cases_st.py와 동일 — event.css가 실제로 정의하는 클래스라, S로
# 생성하면 J(합성 Tailwind)와 달리 미리보기에도 event.css를 적용할 수
# 있다(app.py에서 이 이름을 그대로 확인해서 분기한다).
BLOCK_CLASS_HINT = {
    "hero": "ev-block block-hero",
    "benefits": "ev-block block-benefits",
    "steps": "ev-block block-steps",
    "cta": "ev-block block-cta",
}

GEN_SYSTEM_S = "\n".join([
    "너는 이벤트 페이지를 처음부터 만드는 도우미다.",
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
    "- 날짜를 임의로 만들지 마라.",
    "- 주어지지 않은 내용을 지어내지 마라.",
    "- 대괄호 자리표시자를 절대 남기지 마라.",
    '- style="..." 를 넣지 마라. theme- 로 시작하는 클래스를 넣지 마라.',
    "- 이모지를 쓰지 마라.",
])


def blocks_in_html(html: str) -> list:
    """현재 HTML(J 렌더 결과든 S 생성 결과든 템플릿이든)에 실제로 있는
    data-block 이름을 문서 순서대로 뽑는다 — GUI의 '수정영역' 드롭다운을
    항상 실제 상태와 맞게 채우기 위한 공용 헬퍼."""
    soup = BeautifulSoup(html or "", "html.parser")
    return [el["data-block"] for el in soup.find_all(attrs={"data-block": True})]

GEN_SYSTEM = """너는 이벤트 페이지의 구성 계획(JSON)을 만드는 도우미다.

요청에 맞는 이벤트 페이지를 blocks 배열로 표현한다. 마크업은 서버가
만들므로 너는 내용(문구·항목)만 낸다.

포함할 블록:
- hero: 제목(title)과 소개(sub)
- benefits: 혜택 3개(items)
- steps: 참여 방법 3단계(items)
- cta: 버튼 문구(label)

규칙:
- notices 블록은 서버 전용이므로 절대 포함하지 마라.
- 값만 쓴다. HTML 태그를 넣지 마라 — 마크업은 서버가 만든다.
- 날짜를 임의로 만들지 마라.
- 대괄호 자리표시자를 남기지 마라.
- 주어지지 않은 내용을 지어내지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


def _edit_system(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성을 수정하는 도우미다.

[현재 계획]
{plan_json}

전체 계획을 다시 쓰지 마라. 요청과 관련된 부분만 오퍼레이션으로 표현하라.

사용 가능한 오퍼레이션:
- set_field: {{"op":"set_field","block_key":"cta","field":"label","value":"..."}}
- append_item: {{"op":"append_item","block_key":"benefits","value":"..."}}
- remove_block: {{"op":"remove_block","block_key":"steps"}}
- add_block(콘텐츠 포함): {{"op":"add_block","type":"poll","variant":"vote",
  "question":"...","items":["...","...","..."]}}
- set_theme(색상/폰트/크기): {{"op":"set_theme","field":"primaryColor","value":"#2d6cdf"}}
  또는 {{"op":"set_theme","field":"baseFontSize","value":"18px"}}
- apply_preset(테마 프리셋): {{"op":"apply_preset","name":"vivid"}}
  (vivid/cool/minimal/warm 중 하나)

출력 형식: {{"action":"patch","ops":[ ...오퍼레이션들... ]}}

규칙:
- 언급되지 않은 블록/필드는 오퍼레이션에 아예 포함하지 마라.
- 최소한의 오퍼레이션으로 요청을 처리하라.
- notices 블록은 서버 전용이므로 절대 건드리지 마라.
- baseFontSize는 반드시 "14px"/"16px"/"18px"/"20px" 중 하나로 쓴다.
- primaryColor/buttonColor는 반드시 "#RRGGBB" 형식의 HEX로 쓴다.
- JSON 외에는 아무것도 출력하지 마라."""


def render_fragment(plan: dict) -> str:
    return render_theme_style(plan.get("theme")) + "\n" + render_plan(plan)


def generate_page(prompt: str, model: str) -> dict:
    """반환: {plan, html} — html은 <style>+blocks 조각(문서 전체 아님)."""
    messages = [
        {"role": "system", "content": GEN_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    res = call(model, messages, mode="plan", as_json=True,
               json_schema=PLAN_SCHEMA, num_predict_override=3072)
    plan = parse_json_output(res["message"]["content"])
    plan.setdefault("theme", dict(THEME_DEFAULTS))
    return {"plan": plan, "html": render_fragment(plan)}


def generate_page_html(prompt: str, model: str) -> dict:
    """S 방식 생성(v5 cases_st.py와 동일) — LLM이 <section> HTML을 직접
    쓴다. plan이 없으므로 이후 수정은 S(edit_block_direct)로만 가능하다."""
    messages = [
        {"role": "system", "content": GEN_SYSTEM_S},
        {"role": "user", "content": prompt},
    ]
    res = call(model, messages, mode="html", num_predict_override=3072)
    html = extract(res["message"]["content"])
    return {"html": html}


def edit_page(current_plan: dict, instruction: str, model: str) -> dict:
    """반환: {patch, plan, html, rejected(bool)}.
    rejected=True면 모델이 patch를 거부(action이 clarify/unsupported)한 것이고
    plan/html은 변경 전 그대로 돌아온다."""
    messages = [
        {"role": "system", "content": _edit_system(current_plan)},
        {"role": "user", "content": instruction},
    ]
    res = call(model, messages, mode="patch", as_json=True,
               json_schema=PATCH_SCHEMA, num_predict_override=3072)
    patch = parse_json_output(res["message"]["content"])

    if patch.get("action") != "patch":
        return {"patch": patch, "plan": current_plan,
                "html": render_fragment(current_plan), "rejected": True}

    new_plan = apply_patch(current_plan, patch)
    return {"patch": patch, "plan": new_plan,
            "html": render_fragment(new_plan), "rejected": False}


def edit_block_direct(current_html: str, block_key: str, instruction: str, model: str) -> dict:
    """S 방식 — 실제 템플릿 블록의 outerHTML을 통째로 왕복 편집한다
    (edit_lib.build_block_edit_system과 동일한 v1/v4의 S·E 메커니즘).
    J/K처럼 JSON 스키마로 강제하지 않는다 — S 자체가 "모델이 HTML을
    직접 쓰는" 경로라 문법 강제가 원래 없다(§6~§8에서 확인한 대로 그래도
    안전한 모델을 쓰면 class_lost 없이 잘 나온다).
    """
    system = build_block_edit_system(block_key)
    baseline_block = block_of(current_html, block_key)
    user_msg = f"{instruction}\n\n{baseline_block}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    res = call(model, messages, mode="html", num_predict_override=1536)
    raw = res["message"]["content"]
    new_block_html = extract(raw)
    new_full_html = replace_block(current_html, block_key, new_block_html)
    return {
        "html": new_full_html,
        "block_before": baseline_block,
        "block_after": new_block_html,
    }
