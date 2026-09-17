"""
cases_js_plan.py — JS-PLAN군: 인터랙션을 J(조합 계획) 방식으로 생성
======================================================================
v3 README §2의 3-way 비교 중 "인터랙션 블록의 콘텐츠 값만 JSON으로
내고, 실제 동작 JS는 서버 고정 스니펫(registry.assemble_page)이 붙이는"
안전한 경로를 잰다. registry.LLM_BLOCKS에는 이미 countdown/faq/tabs가
등록돼 있고 v2 cases_j.py의 build_plan_system()도 이미 이 블록들을
프롬프트에 나열하고 있었다 — 지금까지 이 블록을 실제로 "요청"하는
케이스가 하나도 없었을 뿐이다. 이 파일이 그 빈틈(v3 README §1)을 채운다.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택

GEN_SYSTEM/GEN_P1/PLAN_SCHEMA는 cases_chain.py의 CHAIN2/CHAIN6에서
"평범한 신규 생성" 1단계로 재사용한다(J 방식 자체는 이미 v2에서
검증됐으므로 새로 만들지 않고 여기서 한 벌만 정의해 공유한다).
"""

import json
import re

from engine import Case
from registry import LLM_BLOCKS, SERVER_BLOCKS, REQUIRED, build_plan_json_schema

FENCE = re.compile(r"```")


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
        "- countdown 블록의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.",
        '- faq/tabs 블록의 items는 각 항목을 "앞부분|뒷부분" 형식(구분자는 파이프 1개)으로 쓴다 '
        '(faq는 "질문|답변", tabs는 "탭이름|내용").',
        "- 날짜를 만들지 마라. 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 쓰지 마라. 이모지를 쓰지 마라.",
        "- JSON 외에는 아무것도 출력하지 마라.",
    ]
    return "\n".join(lines)


GEN_SYSTEM = build_plan_system()
PLAN_SCHEMA = build_plan_json_schema()

GEN_P1 = ("2026년 8월 1일부터 8월 31일까지 신규 가입자에게 데이터 쿠폰 3GB를 주는 "
          "이벤트 페이지를 만들어줘.")

P_COUNTDOWN = GEN_P1 + " 이벤트 마감까지 남은 시간을 보여주는 카운트다운도 넣어줘. 마감일은 2026년 8월 31일이야."
P_FAQ = GEN_P1 + " 자주 묻는 질문 2개도 포함해줘."
P_TABS = GEN_P1 + " 탭으로 전환되는 안내 콘텐츠(혜택 안내/유의사항 등) 2개도 넣어줘."

# v3 방침(README §5) — plan 모드 캡을 케이스 단위로 3072까지 올린다.
V3_NUM_PREDICT_PLAN = 3072

COUNTDOWN_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_plan_json(raw):
    """extra_check는 plan 모드에서 (raw, raw)를 받는다(engine.run_one 참고) —
    렌더링된 HTML이 아니라 LLM이 낸 JSON 원문 그대로다. 여기서 직접
    다시 파싱해서 필드 형식(날짜/파이프 구분자)을 검사한다."""
    text = FENCE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def _find_block(plan, block_type):
    if not plan:
        return None
    for item in plan.get("blocks", []):
        if isinstance(item, dict) and item.get("type") == block_type:
            return item
    return None


def check_countdown_value_format(raw, _):
    plan = _parse_plan_json(raw)
    block = _find_block(plan, "countdown")
    if block is None:
        return []  # keep=["countdown"]가 이미 lost_countdown으로 잡는다
    target = str(block.get("target_date", ""))
    if not COUNTDOWN_DATE.match(target):
        return ["countdown_bad_date_format"]
    return []


def _check_pipe_items(raw, block_type, fail_code):
    plan = _parse_plan_json(raw)
    block = _find_block(plan, block_type)
    if block is None:
        return []
    items = block.get("items")
    if not isinstance(items, list) or not items:
        return []  # few_<type>로 check_plan이 이미 잡음
    if any(not isinstance(x, str) or "|" not in x for x in items):
        return [fail_code]
    return []


def check_faq_item_format(raw, _):
    return _check_pipe_items(raw, "faq", "faq_item_missing_pipe")


def check_tabs_item_format(raw, _):
    return _check_pipe_items(raw, "tabs", "tabs_item_missing_pipe")


CASES = [
    Case("JSPLAN1", "카운트다운_조합계획", "JS-PLAN", GEN_SYSTEM, P_COUNTDOWN, "plan",
         keep=list(REQUIRED) + ["countdown"], forbid=["notices"],
         extra_check=check_countdown_value_format, json_schema=PLAN_SCHEMA,
         num_predict=V3_NUM_PREDICT_PLAN),

    Case("JSPLAN2", "아코디언_조합계획", "JS-PLAN", GEN_SYSTEM, P_FAQ, "plan",
         keep=list(REQUIRED) + ["faq"], forbid=["notices"],
         extra_check=check_faq_item_format, json_schema=PLAN_SCHEMA,
         num_predict=V3_NUM_PREDICT_PLAN),

    Case("JSPLAN3", "탭전환_조합계획", "JS-PLAN", GEN_SYSTEM, P_TABS, "plan",
         keep=list(REQUIRED) + ["tabs"], forbid=["notices"],
         extra_check=check_tabs_item_format, json_schema=PLAN_SCHEMA,
         num_predict=V3_NUM_PREDICT_PLAN),
]


def self_check():
    for b in LLM_BLOCKS:
        for v in b.variants:
            assert f'variant="{v.name}"' in GEN_SYSTEM, f"{b.key}/{v.name} 누락"

    good_countdown = json.dumps({"blocks": [
        {"type": "countdown", "variant": "digital", "title": "마감임박", "target_date": "2026-08-31"},
    ]}, ensure_ascii=False)
    assert check_countdown_value_format(good_countdown, "") == []
    bad_countdown = json.dumps({"blocks": [
        {"type": "countdown", "variant": "digital", "title": "마감임박", "target_date": "8월 31일"},
    ]}, ensure_ascii=False)
    assert "countdown_bad_date_format" in check_countdown_value_format(bad_countdown, "")

    good_faq = json.dumps({"blocks": [
        {"type": "faq", "variant": "native_details", "items": ["환불 되나요?|가능합니다."]},
    ]}, ensure_ascii=False)
    assert check_faq_item_format(good_faq, "") == []
    bad_faq = json.dumps({"blocks": [
        {"type": "faq", "variant": "native_details", "items": ["환불 되나요?"]},
    ]}, ensure_ascii=False)
    assert "faq_item_missing_pipe" in check_faq_item_format(bad_faq, "")

    assert len(CASES) == 3
    for c in CASES:
        assert c.group == "JS-PLAN"
        assert c.mode == "plan"
        assert c.json_schema is not None
        assert c.num_predict == V3_NUM_PREDICT_PLAN
    assert "countdown" in CASES[0].keep
    assert "faq" in CASES[1].keep
    assert "tabs" in CASES[2].keep
