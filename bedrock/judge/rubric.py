"""
rubric.py — LLM-as-a-Judge 프롬프트 + 점수 스키마
====================================================================
`docs/bedrock/v2-pipeline.md` §12~§22, §27의 평가 항목·0~5점 척도를 그대로
Judge 프롬프트로 옮긴다.

§36.3 원칙을 지킨다 — "data-block이 존재하는가?" 같은 결정적 항목은
Judge에게 묻지 않는다(그건 deterministic_html.py/deterministic_json.py가
이미 코드로 판정한다). 여기서 Judge에게 묻는 것은 오직 §27 표에서
"Judge" 또는 "Code + Judge"로 표시된, 의미 판단이 필요한 항목뿐이다.
"""

import json

SCORE_SCALE = """0점 = 완전히 깨짐 / 전혀 반영 안 됨
1점 = 대부분 반영되지 않음
2점 = 일부만 반영됨
3점 = 주요 요구사항은 반영되었으나 눈에 띄는 오류·누락 존재
4점 = 거의 모든 요구사항을 정확히 반영
5점 = 요구사항을 완전히, 정확히 반영"""

_COMMON_RULES = f"""너는 이벤트 페이지 생성 결과를 채점하는 평가자다.
아래 척도로만 점수를 매긴다(정수 0~5):

{SCORE_SCALE}

반드시 지킬 것:
- 문자열이 완전히 같은지가 아니라 "의미가 같은지"로 판단한다.
  예: "데이터 10GB 추가 제공" 과 "추가 데이터 10GB 제공"은 동일하게 취급한다.
- 사용자가 명시하지 않은 값(날짜·수치·혜택)을 모델이 지어냈다면
  requirement_accuracy를 감점한다.
- 구조가 올바른지(태그, data-block 존재 등)는 이미 별도 코드로 검증했으므로
  너는 그 판단을 하지 않는다. 오직 "내용이 요구사항과 프롬프트에 맞는가"만 본다.
- 반드시 JSON 객체 하나만 출력한다. 설명·인사말·코드블록을 붙이지 마라.
"""

JSON_JUDGE_SYSTEM_GENERATION = _COMMON_RULES + """
출력 스키마:
{
  "requirement_accuracy": 0-5,
  "content_accuracy": 0-5,
  "schema_compliance_semantic": 0-5,
  "rationale": "한국어 한두 문장"
}

schema_compliance_semantic 은 구조 문법(코드가 이미 검사함)이 아니라
"Component 구성이 요구사항 표현에 적절한가"(예: 혜택 3개를 요구했는데
Section에 Component가 1개만 있다면 감점)를 본다.
"""

JSON_JUDGE_SYSTEM_EDIT = _COMMON_RULES + """
출력 스키마:
{
  "requirement_accuracy": 0-5,
  "content_accuracy": 0-5,
  "modification_accuracy": 0-5,
  "rationale": "한국어 한두 문장"
}

modification_accuracy 는 "요청한 Component/Section만 정확히 바뀌고 나머지는
의미상 그대로인가"를 본다. 대상이 아닌 곳의 내용이 바뀌었다면 감점한다.
"""

HTML_JUDGE_SYSTEM_GENERATION = _COMMON_RULES + """
출력 스키마:
{
  "requirement_accuracy": 0-5,
  "content_accuracy": 0-5,
  "rationale": "한국어 한두 문장"
}

HTML 태그 구조 자체(section, data-block, 최소 항목 수)는 이미 코드가
검증했으니 너는 보지 않는다. 오직 h1/p/li 등 안에 든 "문구 내용"이
요구사항과 일치하는지만 본다.
"""

HTML_JUDGE_SYSTEM_EDIT = _COMMON_RULES + """
출력 스키마:
{
  "requirement_accuracy": 0-5,
  "content_accuracy": 0-5,
  "modification_accuracy": 0-5,
  "rationale": "한국어 한두 문장"
}

modification_accuracy 는 "요청한 문구만 정확히 바뀌고, 요청하지 않은 문구
(href, class 등 속성이 아니라 '문구 의미')는 그대로인가"를 본다.
"""

BEHAVIOR_JUDGE_SYSTEM = _COMMON_RULES + """
출력 스키마:
{
  "behavior_correctness": 0-5,
  "rationale": "한국어 한두 문장"
}

behavior_correctness 는 "설명된 시나리오(예: 클릭하면 API 호출 후 성공
모달 표시)의 event/action(s)/target/endpoint/순서가 의미상 정확히
표현되었는가"를 본다. allowlist 위반 여부(허용 안 된 action, 외부
endpoint)는 이미 코드가 검증했으니 너는 "의도가 정확히 표현됐는가"만 본다.
"""


def build_user_prompt(*, prompt: str, requirements: dict | None,
                       output_text: str, before: str | None = None,
                       deterministic_summary: list | None = None) -> str:
    parts = [f"[사용자 요구사항]\n{prompt}"]
    if requirements:
        parts.append(f"[정량 요구사항]\n{json.dumps(requirements, ensure_ascii=False, indent=2)}")
    if before:
        parts.append(f"[수정 전 원본]\n{before}")
    parts.append(f"[모델 출력]\n{output_text}")
    if deterministic_summary:
        parts.append("[코드 검증에서 이미 잡힌 항목 — 구조 문제이니 참고만 하고 "
                      "네 점수 기준(내용/의미)에서는 중복 감점하지 마라]\n"
                      + ", ".join(deterministic_summary))
    parts.append("위 내용을 스키마에 맞는 JSON 하나로만 채점하라.")
    return "\n\n".join(parts)


def system_for(fmt: str, category: str) -> str:
    """fmt: 'json' | 'html' 어느 방식의 출력인가.
    category: 'generation' | 'edit' | 'behavior'"""
    if category == "behavior":
        return BEHAVIOR_JUDGE_SYSTEM
    table = {
        ("json", "generation"): JSON_JUDGE_SYSTEM_GENERATION,
        ("json", "edit"): JSON_JUDGE_SYSTEM_EDIT,
        ("html", "generation"): HTML_JUDGE_SYSTEM_GENERATION,
        ("html", "edit"): HTML_JUDGE_SYSTEM_EDIT,
    }
    key = (fmt, category)
    if key not in table:
        raise ValueError(f"모르는 (fmt, category) 조합: {key}")
    return table[key]


def parse_judge_json(raw: str) -> dict:
    """Judge 모델 출력에서 JSON만 뽑는다. 실패하면 error 필드로 표시."""
    text = (raw or "").replace("```json", "").replace("```", "")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {"error": "no_json_in_judge_output", "raw": raw}
    try:
        parsed = json.loads(text[s:e + 1])
    except Exception as ex:
        return {"error": f"bad_json_in_judge_output: {ex}", "raw": raw}
    if not isinstance(parsed, dict):
        return {"error": "judge_output_not_object", "raw": raw}
    return parsed


def self_check():
    assert system_for("html", "generation") == HTML_JUDGE_SYSTEM_GENERATION
    assert system_for("json", "edit") == JSON_JUDGE_SYSTEM_EDIT
    assert system_for("html", "behavior") == BEHAVIOR_JUDGE_SYSTEM
    try:
        system_for("xml", "generation")
        raise AssertionError("모르는 fmt를 걸러내지 못함")
    except ValueError:
        pass

    prompt = build_user_prompt(prompt="여름 이벤트 만들어줘",
                                requirements={"benefit": "데이터 10GB"},
                                output_text="<section>...</section>",
                                deterministic_summary=["placeholder"])
    assert "여름 이벤트 만들어줘" in prompt
    assert "placeholder" in prompt

    good = parse_judge_json('설명입니다\n```json\n{"requirement_accuracy":5,'
                             '"content_accuracy":4,"rationale":"좋음"}\n```')
    assert good["requirement_accuracy"] == 5

    bad = parse_judge_json("이건 JSON이 아님")
    assert "error" in bad

    print("  [rubric] self_check 통과")


if __name__ == "__main__":
    self_check()
