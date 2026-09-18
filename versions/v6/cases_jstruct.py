"""
cases_jstruct.py — J-STRUCT군: 콘텐츠 없이 "구조만" 결정하게 시킨다
========================================================================
지금까지의 J(`versions/v5/cases_jt.py`)는 LLM이 블록 종류·개수는 물론
title/sub/items 같은 실제 문구까지 전부 냈다. 그런데 여기서 나온 실패
(placeholder 미채움·환각·tag_in_field·duplicate_data_block)는 전부
"내용을 지어내야 하는" 부분에서 나왔다 — 세션에서 exaone의 J-T 원문을
직접 열어서 확인함.

이 파일은 실험을 하나 더 좁힌다: LLM에게 **문구는 아예 안 시키고, "어떤
블록을 쓸지"와 "항목이 몇 개 필요한지"만** 결정하게 한다. 실제 문구는
서버가 이 구조를 보고 자동 생성한 폼에 사람이 입력한다는 게 제품
설계 방향이므로(세션 논의 참고), 이 케이스는 그 폼을 만들기 위한 첫
단계 — "구조 결정"만 따로 떼어서 정확도를 잰다.

`versions/v5/cases_jt.py`(= `cases_st.py`)와 **글자 그대로 같은 요청
문구**를 쓴다(pair 비교) — 문구가 같은데 스키마만 "문구 전부"에서
"type+itemCount만"으로 좁아지면 얼마나 나아지는지가 이 군의 질문이다.

⚠ **v5가 아니라 v6에 있는 이유·주의점**: 이 군은 J-T와 짝 비교되지만,
`discover_case_modules()`가 버전 폴더 안의 `cases_*.py`를 전부 자동
실행하므로 `cases_jt.py`/`cases_st.py`를 통째로 v6에 복사해 넣으면
`python base/run.py v6`를 그룹 지정 없이 돌릴 때 S-T/J-T까지 같이
실행돼버린다 — v6의 조건(K-T5/K-FS/K-IDX/RK/S-E)과 섞인다. 그래서
v2 `cases_j.py`가 v1 `cases_ns.py`와 같은 문구를 쓰면서도 import 없이
`pair="S1"` 문자열만 걸어뒀던 것과 같은 방식을 쓴다 — **문구를
`versions/v5/cases_jt.py`에서 그대로 복사해왔고, import로 자동 검증되지
않으니 어느 한쪽 문구를 고치면 반드시 둘 다 확인할 것.**

engine.py의 표준 mode="plan"은 registry.build_plan_json_schema()·
check_plan()을 하드코딩으로 쓰기 때문에(문구 필드가 필수라고 가정),
mode="custom"으로 자체 스키마·검증을 쓴다 — v6의 patch_ops_v6.py와
같은 탈출구.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택

## 1차 실행(STRUCT1~5) 이후 넓힌 범위 — 세션에서 지적된 두 구멍

STRUCT1~5는 전부 "hero+benefits(3)+steps(3)+cta"라는 똑같은 구조라, 다음
두 가지를 한 번도 못 쟀다는 지적이 있었다.

1. **선택 블록(countdown/faq/tabs)과 "개수가 요청에 안 나온" 애매한 경우**
   — STRUCT6~9로 추가했다. `keep_counts`에 새 값 `"any"`를 도입해서
   "itemCount가 있어야 하지만 몇 개인지는 요청 문구가 정하지 않았으니
   2~4 범위 안이면 뭐든 정답"을 표현한다(스키마 자체의 minimum/maximum이
   이미 2~4를 강제하므로, `"any"`는 그냥 정확한 개수 비교를 건너뛴다는
   뜻일 뿐이다).
2. **variant(디자인 스타일) 선택까지 LLM에 맡길지** — 이번 실험은
   `type`/`itemCount`만 시켰고 스타일은 아예 스키마에서 뺐다. 그게
   맞는 설계인지("스타일까지 시켜도 구조 결정 정확도가 안 떨어지는가")를
   직접 재기 위해 **J-STRUCT-V**(variant 포함판)를 별도 군으로 추가했다
   — STRUCT1~5와 글자 그대로 같은 요청을 쓰되, 스키마에 `variant`
   (그 블록의 실제 등록된 variant 이름 중 하나, enum)를 필수로 더한다.
   `J-STRUCT` 대 `J-STRUCT-V`를 비교하면 "구조 결정에 스타일 선택까지
   얹었을 때 정확도가 유지되는가"의 답이 나온다.
"""

import json
import re

from engine import Case
import engine

from registry import LLM_BLOCKS, REQUIRED

GROUPS = ["J-STRUCT", "J-STRUCT-V"]

FENCE_RE = re.compile(r"```")

# 구조만 내면 되므로 출력이 아주 짧다 — {"blocks":[{"type":"hero"},
# {"type":"benefits","itemCount":3}, ...]} 수준. 넉넉히 200으로 잡는다.
NUM_PREDICT_STRUCT = 200

ITEM_BLOCK_KEYS = {b.key for b in LLM_BLOCKS if any("items" in v.fields for v in b.variants)}
# 실측(레지스트리 기준): benefits, steps, faq, tabs — hero/cta/countdown은 itemCount가 없다.

ALL_LLM_BLOCK_KEYS = {b.key for b in LLM_BLOCKS}
MIN_ITEMS = {b.key: max(b.min_items, 1) for b in LLM_BLOCKS if b.key in ITEM_BLOCK_KEYS}

# J-STRUCT-V(variant 포함판)가 스키마 enum과 프롬프트 설명 둘 다에 쓴다.
BLOCK_VARIANT_NAMES = {b.key: [v.name for v in b.variants] for b in LLM_BLOCKS}
ANY_COUNT = "any"  # keep_counts 값 — "itemCount는 필요하지만 정확한 개수는 요청에 없음"

SYSTEM = """너는 이벤트 페이지에 어떤 구성 요소가 몇 개씩 필요한지만 정하는 도우미다.

내용(제목·문구·항목 텍스트)은 전혀 쓰지 않는다 — 그건 나중에 사람이 폼으로 채운다.
너는 오직 "어떤 블록을 쓸지"와 "항목이 몇 개 필요한지"만 정한다.

사용 가능한 블록:
- hero: 제목/소개 (항목 없음)
- benefits: 혜택 목록 (항목 있음)
- steps: 참여 방법 목록 (항목 있음)
- cta: 참여 버튼 (항목 없음)
- countdown: 마감 카운트다운 (항목 없음)
- faq: 자주 묻는 질문 목록 (항목 있음)
- tabs: 탭으로 나눈 콘텐츠 목록 (항목 있음)
(notices는 서버 전용이니 절대 포함하지 마라)

"항목 있음" 블록(benefits·steps·faq·tabs)은 itemCount(정수, 2~4)를 반드시
낸다. 요청에 정확한 개수가 안 나와 있으면 2~4 중 적절히 하나를 골라서
낸다 — itemCount 자체를 생략하면 안 된다.
"항목 없음" 블록(hero·cta·countdown)은 itemCount를 쓰지 마라 — **그렇다고
blocks 목록에서 빼면 안 된다.** "결정할 게 없다"는 이유로 생략하지 마라.
요청에 있는 블록이면 파라미터가 없어도 {"type":"hero"}처럼 type만 있는
항목으로 반드시 포함시켜라.

규칙:
- 요청에 없는 블록을 추가로 만들어내지 마라.
- 요청에 있는 블록은 파라미터가 없어도(hero·cta·countdown) 절대 빠뜨리지 마라.
- 각 블록 종류는 반드시 한 번만 나열한다 — 예를 들어 혜택이 3개 필요하면
  {"type":"benefits","itemCount":3} 하나만 낸다. benefits 블록을 3번
  만드는 식으로 항목 수를 표현하지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


def build_structure_json_schema() -> dict:
    """LLM_BLOCKS로부터 "type(+itemCount)"만 있는 좁은 스키마를 만든다.
    항목이 있는 블록은 itemCount(2~4)를 필수로, 없는 블록은 type만
    허용한다(additionalProperties:false라서 문구 필드 자체를 낼 문법이
    없다 — "지어낼 방법이 없다"를 스키마 레벨에서 보장한다)."""
    one_of = []
    for b in LLM_BLOCKS:
        if b.key in ITEM_BLOCK_KEYS:
            one_of.append({
                "type": "object",
                "properties": {
                    "type": {"const": b.key},
                    "itemCount": {"type": "integer",
                                  "minimum": MIN_ITEMS[b.key], "maximum": 4},
                },
                "required": ["type", "itemCount"],
                "additionalProperties": False,
            })
        else:
            one_of.append({
                "type": "object",
                "properties": {"type": {"const": b.key}},
                "required": ["type"],
                "additionalProperties": False,
            })
    return {
        "type": "object",
        "properties": {
            "blocks": {"type": "array", "items": {"oneOf": one_of}, "minItems": 1},
        },
        "required": ["blocks"],
        "additionalProperties": False,
    }


STRUCTURE_SCHEMA = build_structure_json_schema()


def check_structure(raw: str, keep_counts: dict, variant_names: dict = None) -> tuple:
    """keep_counts: {block_key: 기대값}. 기대값은 세 종류다 —
      None        itemCount가 없어야 하는 블록(hero/cta/countdown)
      정수         itemCount가 정확히 이 값이어야 함(요청에 개수가 명시된 경우)
      ANY_COUNT    itemCount가 있어야 하지만 정확한 개수는 요청에 없어서
                   2~4 범위(스키마가 이미 강제)면 뭐든 정답 — 그래서 이
                   값일 때는 정확히 비교하지 않고 "itemCount가 있는지"만 본다.
    keep_counts에 없는 블록 종류는 전부 틀린 것으로 본다 — notices는
    forbidden_block로, 그 외(countdown/faq/tabs 등 요청 안 한 선택
    블록)는 unexpected_block로 구분해서 잡는다(v3 GEN_FORBID와 같은 취지:
    "요청 안 한 선택 블록을 추가하면 원인 위치에서 바로 하드 실패로 잡는다").

    variant_names: {block_key: [허용된 variant 이름들]} — 넘기면(J-STRUCT-V만
    씀) 각 블록에 variant가 있는지·그 블록에 실제로 등록된 이름인지까지
    검사한다. None(기본, J-STRUCT)이면 variant는 아예 안 본다 — 애초에
    스키마에 그 필드가 없어서 낼 방법도 없다.
    반환: (fails, note)"""
    text = FENCE_RE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], "JSON을 찾을 수 없습니다."
    try:
        plan = json.loads(text[s:e + 1])
    except Exception as ex:
        return ["bad_json"], f"JSON 파싱 실패: {ex}"

    blocks = plan.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return ["no_blocks"], "blocks 배열이 없습니다."

    fails, notes = [], []
    seen_types = []
    for b in blocks:
        if not isinstance(b, dict) or "type" not in b:
            fails.append("bad_block_entry")
            continue
        t = b["type"]
        seen_types.append(t)
        if t not in keep_counts:
            if t == "notices":
                fails.append("forbidden_block_notices")
                notes.append("notices는 서버 전용이라 절대 포함하면 안 됩니다.")
            else:
                fails.append(f"unexpected_block_{t}")
                notes.append(f"요청하지 않은 블록({t})을 추가했습니다.")

    dup_seen = set()
    for t in seen_types:
        if seen_types.count(t) > 1:
            dup_seen.add(t)
    for t in sorted(dup_seen):
        fails.append(f"duplicate_type_{t}")
        notes.append(f"{t} 블록을 여러 번 나열했습니다 — itemCount 하나로 표현하세요.")

    for key, expect in keep_counts.items():
        matches = [b for b in blocks if isinstance(b, dict) and b.get("type") == key]
        if not matches:
            fails.append(f"missing_block_{key}")
            notes.append(f"{key} 블록이 없습니다.")
            continue
        got = matches[0].get("itemCount")
        if expect == ANY_COUNT:
            if not isinstance(got, int) or isinstance(got, bool):
                fails.append(f"missing_item_count_{key}")
                notes.append(f"{key}는 itemCount가 필요합니다(개수는 2~4 중 적절히).")
        elif expect is not None:
            if got != expect:
                fails.append(f"wrong_item_count_{key}_want{expect}_got{got}")
                notes.append(f"{key}의 itemCount가 {expect}이어야 하는데 {got}입니다.")

        if variant_names is not None:
            v = matches[0].get("variant")
            allowed = variant_names.get(key, [])
            if not v:
                fails.append(f"missing_variant_{key}")
                notes.append(f"{key}에 variant가 없습니다.")
            elif v not in allowed:
                fails.append(f"invalid_variant_{key}")
                notes.append(f"{key}의 variant({v})가 등록된 이름이 아닙니다: {allowed}")

    return fails, " ".join(notes)


def _custom_run(pid, kind, prompt, keep_counts, group="J-STRUCT", system=None,
                 schema=None, variant_names=None, max_retry=3):
    system = system if system is not None else SYSTEM
    schema = schema if schema is not None else STRUCTURE_SCHEMA

    def _run(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        first_hard_ok = None

        for attempt in range(1, max_retry + 1):
            try:
                res = engine.call(model, messages, mode="plan", as_json=True, seed=seed,
                                   json_schema=schema,
                                   num_predict_override=NUM_PREDICT_STRUCT)
            except Exception:
                rows.append(engine._empty_row(
                    runner=runner, model=model, digest=digest, backend=backend,
                    group=group, prompt_id=pid, kind=kind, pair=case.pair,
                    repeat_no=repeat_no, seed=seed, attempt=attempt,
                    hard_ok=0, all_ok=0, fails="request_error"))
                return first_hard_ok or 0, 0

            raw = res["message"]["content"]
            fails, note = check_structure(raw, keep_counts, variant_names=variant_names)
            out_len = len(raw.strip())

            if res.get("done_reason") == "length":
                fails.append("truncated")

            hard_ok = int(not fails)
            if first_hard_ok is None:
                first_hard_ok = hard_ok

            pc, ec = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
            pd, ed = res.get("prompt_eval_duration", 1), res.get("eval_duration", 1)
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group=group, prompt_id=pid, kind=kind, pair=case.pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=hard_ok, all_ok=hard_ok, fails="|".join(fails),
                wall_sec=res["_wall_sec"],
                load_ms=res.get("load_duration", 0) // 1_000_000,
                prompt_ms=pd // 1_000_000, eval_ms=ed // 1_000_000,
                prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
                prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
                eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
                out_len=out_len, html_len=out_len,
                done_reason=res.get("done_reason", "")))

            safe = model.replace(":", "_")
            with open(f"{out_dir}/{safe}_{pid}_r{repeat_no}_s{seed}_try{attempt}.txt",
                      "w", encoding="utf-8") as f:
                f.write(raw)

            if hard_ok:
                return first_hard_ok, 1

            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                              "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

        return first_hard_ok or 0, 0
    return _run


def _case(pid, kind, prompt, keep_counts, pair=""):
    return Case(
        pid, kind, "J-STRUCT", "", prompt, "custom",
        keep=list(keep_counts), forbid=["notices"], pair=pair,
        custom_run=_custom_run(pid, kind, prompt, keep_counts),
    )


# 모든 요청이 "혜택 3개 · 참여 방법 3단계"로 통일돼 있다(cases_jt.py SYSTEM
# 참고) — 그래서 keep_counts는 5개 케이스가 전부 동일하다.
_KEEP = {"hero": None, "benefits": 3, "steps": 3, "cta": None}

# 요청 문구는 cases_jt.py(=cases_st.py)와 글자 그대로 같아야 한다.
CASES = [
    _case("STRUCT1", "구조결정_스포츠응원",
          "2026년 프로야구 시즌 응원 이벤트 페이지를 만들어줘. "
          "혜택 3개(굿즈, 할인, 포인트 적립), 참여 방법 3단계를 포함해줘.",
          _KEEP, pair="JT1"),
    _case("STRUCT2", "구조결정_명절선물",
          "설 명절 선물 대축제 이벤트 페이지를 만들어줘. "
          "혜택 3개(상품권, 할인 쿠폰, 사은품), 참여 방법 3단계를 포함해줘.",
          _KEEP, pair="JT2"),
    _case("STRUCT3", "구조결정_멤버십감사",
          "장기 고객 대상 멤버십 감사 이벤트 페이지를 만들어줘. "
          "혜택 3개(쿠폰, 등급 혜택, 특별 사은품), 참여 방법 3단계를 포함해줘.",
          _KEEP, pair="JT3"),
    _case("STRUCT4", "구조결정_플래시세일",
          "24시간 한정 플래시 세일 이벤트 페이지를 만들어줘. "
          "혜택 3개(즉시 할인, 무료배송, 포인트 2배), 참여 방법 3단계를 포함해줘.",
          _KEEP, pair="JT4"),
    _case("STRUCT5", "구조결정_사전예약",
          "신제품 사전예약 이벤트 페이지를 만들어줘. "
          "혜택 3개(얼리버드 할인, 한정 굿즈, 우선 출고), 참여 방법 3단계를 포함해줘.",
          _KEEP, pair="JT5"),

    # ── STRUCT6~9 : 선택 블록(countdown/faq/tabs) + 개수 미지정 케이스.
    #    STRUCT1~5와 달리 pair가 없다 — v5에 대응하는 요청이 없어서(JT1~5는
    #    이 네 시나리오를 다루지 않는다) 신규 케이스이지 pair 비교용이 아니다.
    _case("STRUCT6", "구조결정_선택블록_카운트다운",
          "24시간 한정 플래시 세일 이벤트 페이지를 만들어줘. "
          "혜택 2개, 마감까지 남은 시간을 보여주는 카운트다운도 넣어줘.",
          {"hero": None, "benefits": 2, "cta": None, "countdown": None}),
    _case("STRUCT7", "구조결정_선택블록_FAQ",
          "행사 참가 신청 페이지를 만들어줘. 자주 묻는 질문 3개, 참여 버튼을 포함해줘.",
          {"hero": None, "faq": 3, "cta": None}),
    _case("STRUCT8", "구조결정_선택블록_탭",
          "여러 상품 정보를 탭으로 나눠 보여주는 페이지를 만들어줘. "
          "탭 3개, 참여 버튼을 포함해줘.",
          {"hero": None, "tabs": 3, "cta": None}),
    _case("STRUCT9", "구조결정_개수미지정",
          "행사 혜택을 소개하는 페이지를 만들어줘. 혜택 목록과 참여 버튼을 포함해줘.",
          {"hero": None, "benefits": ANY_COUNT, "cta": None}),
]


# ══════════════════════════════════════════════════════════════
# J-STRUCT-V — variant(디자인 스타일)까지 LLM이 고르게 한 비교판.
# STRUCT1~5와 글자 그대로 같은 요청 문구를 재사용한다(같은 파일 안이라
# import 없이도 직접 비교 가능 — cases_jt.py와 달리 pair 무결성을
# self_check에서 실제로 검증한다).
# ══════════════════════════════════════════════════════════════

def build_structure_json_schema_with_variant() -> dict:
    """build_structure_json_schema()와 같지만 각 블록에 variant(enum, 그
    블록에 실제 등록된 이름 중 하나)를 필수로 더한다."""
    one_of = []
    for b in LLM_BLOCKS:
        props = {
            "type": {"const": b.key},
            "variant": {"type": "string", "enum": BLOCK_VARIANT_NAMES[b.key]},
        }
        required = ["type", "variant"]
        if b.key in ITEM_BLOCK_KEYS:
            props["itemCount"] = {"type": "integer",
                                   "minimum": MIN_ITEMS[b.key], "maximum": 4}
            required.append("itemCount")
        one_of.append({
            "type": "object", "properties": props,
            "required": required, "additionalProperties": False,
        })
    return {
        "type": "object",
        "properties": {
            "blocks": {"type": "array", "items": {"oneOf": one_of}, "minItems": 1},
        },
        "required": ["blocks"],
        "additionalProperties": False,
    }


STRUCTURE_SCHEMA_V = build_structure_json_schema_with_variant()


def _variant_menu() -> str:
    """LLM_BLOCKS의 Variant.desc로 "이 블록엔 이런 스타일이 있다"를 프롬프트에
    붙인다 — 이름만 던지면 뭘 고를지 판단할 근거가 없어서(v1 결론:
    "안 알려주면 모델이 맞힐 수 없는 기준"), registry에 이미 있는 설명을
    그대로 재사용한다."""
    lines = []
    for b in LLM_BLOCKS:
        lines.append(f"- {b.key}:")
        for v in b.variants:
            lines.append(f"    {v.name} — {v.desc}")
    return "\n".join(lines)


SYSTEM_V = SYSTEM.replace(
    "너는 오직 \"어떤 블록을 쓸지\"와 \"항목이 몇 개 필요한지\"만 정한다.",
    "너는 \"어떤 블록을 쓸지\"·\"항목이 몇 개 필요한지\"·\"어떤 디자인"
    " 스타일(variant)을 쓸지\"를 정한다."
).replace(
    "- JSON 외에는 아무것도 출력하지 마라.",
    "- 모든 블록에 variant를 반드시 낸다 — 아래 목록에 있는 이름 중"
    " 요청 분위기에 맞는 것 하나를 그대로 쓴다(새로 지어내지 마라).\n"
    "- JSON 외에는 아무것도 출력하지 마라.\n\n"
    f"사용 가능한 variant:\n{_variant_menu()}"
)


def _case_v(pid, kind, prompt, keep_counts, pair):
    return Case(
        pid, kind, "J-STRUCT-V", "", prompt, "custom",
        keep=list(keep_counts), forbid=["notices"], pair=pair,
        custom_run=_custom_run(pid, kind, prompt, keep_counts, group="J-STRUCT-V",
                                system=SYSTEM_V, schema=STRUCTURE_SCHEMA_V,
                                variant_names=BLOCK_VARIANT_NAMES),
    )


# STRUCT1~5와 글자 그대로 같은 요청 문구 — pair가 "이 파일 안의 다른 케이스
# pid"를 직접 가리키므로(cases_jt.py 때와 달리 cross-file이 아님)
# self_check가 문구 일치까지 실제로 검증한다.
CASES_V = [
    _case_v("STRUCTV1", "구조결정_variant_스포츠응원", CASES[0].prompt, _KEEP, pair="STRUCT1"),
    _case_v("STRUCTV2", "구조결정_variant_명절선물", CASES[1].prompt, _KEEP, pair="STRUCT2"),
    _case_v("STRUCTV3", "구조결정_variant_멤버십감사", CASES[2].prompt, _KEEP, pair="STRUCT3"),
    _case_v("STRUCTV4", "구조결정_variant_플래시세일", CASES[3].prompt, _KEEP, pair="STRUCT4"),
    _case_v("STRUCTV5", "구조결정_variant_사전예약", CASES[4].prompt, _KEEP, pair="STRUCT5"),
]

CASES = CASES + CASES_V


def self_check():
    assert len(CASES) == 14, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group in GROUPS, f"{c.pid}의 group({c.group})이 GROUPS에 없음"
        assert c.mode == "custom"
        assert c.custom_run is not None
        assert "notices" not in c.keep

    # ★ pair 무결성 — STRUCT1~5는 v5 cases_jt.py와 짝지어진다. v6에는
    #   versions/v5/cases_jt.py가 없어서(같은 폴더에 두면
    #   discover_case_modules()가 J-T/S-T까지 v6 실행에 끼워 넣는다) v2
    #   cases_j.py가 v1 cases_ns.py와 짝지을 때 쓴 것과 같은 방식이다 —
    #   import로 자동 비교하지 않고, pair가 지정됐는지만 확인한다. 실제
    #   문구는 파일 상단 경고대로 versions/v5/cases_jt.py에서 그대로
    #   복사해왔으니, 어느 한쪽을 고치면 반드시 둘 다 확인할 것.
    for c in CASES[:5]:
        assert c.pair.startswith("JT"), f"{c.pid}는 J-T와 짝(pair)이 지정돼야 공정 비교가 됨"

    # STRUCT6~9는 v5에 대응 요청이 없는 신규 케이스라 pair가 없다.
    for c in CASES[5:9]:
        assert c.pid.startswith("STRUCT"), c.pid

    # ★ STRUCTV1~5는 STRUCT1~5와 "같은 파일 안"이라 cross-file 문제가 없다 —
    #   실제로 요청 문구까지 동일한지 직접 대조한다(cases_jt.py 때와 달리
    #   여기선 게으르게 pair 문자열만 믿지 않는다).
    struct_by_pid = {c.pid: c for c in CASES[:9]}
    for c in CASES_V:
        assert c.group == "J-STRUCT-V"
        assert c.pair in struct_by_pid, f"{c.pid}의 pair({c.pair})가 STRUCT1~5에 없음"
        assert c.prompt == struct_by_pid[c.pair].prompt, (
            f"{c.pid}와 {c.pair}의 요청 문구가 다릅니다. pair 비교가 무너집니다.")

    # ★ 스키마 — 항목 블록은 itemCount 필수, 값(문구) 필드는 아예 못 낸다.
    variants = {v["properties"]["type"]["const"]: v for v in
                STRUCTURE_SCHEMA["properties"]["blocks"]["items"]["oneOf"]}
    assert "itemCount" in variants["benefits"]["properties"], "benefits에 itemCount가 없음"
    assert "title" not in variants["hero"]["properties"], (
        "hero 스키마에 title이 남아있음 — 구조 전용 스키마가 아님")
    assert variants["hero"]["additionalProperties"] is False

    # ★ 회귀 — 정상 구조는 통과해야 한다.
    good = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 3},
        {"type": "steps", "itemCount": 3}, {"type": "cta"},
    ]}, ensure_ascii=False)
    fails, _ = check_structure(good, _KEEP)
    assert fails == [], f"정상 구조가 실패로 잡힘: {fails}"

    # ★ 회귀 — exaone이 실제로 저질렀던 실수: 개수 대신 블록을 반복
    dup = json.dumps({"blocks": [
        {"type": "hero"},
        {"type": "benefits", "itemCount": 1}, {"type": "benefits", "itemCount": 1},
        {"type": "benefits", "itemCount": 1},
        {"type": "steps", "itemCount": 3}, {"type": "cta"},
    ]}, ensure_ascii=False)
    dup_fails, _ = check_structure(dup, _KEEP)
    assert "duplicate_type_benefits" in dup_fails, f"블록 반복을 못 잡음: {dup_fails}"

    # ★ 회귀 — 누락된 필수 블록
    missing = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 3}, {"type": "cta"},
    ]}, ensure_ascii=False)
    missing_fails, _ = check_structure(missing, _KEEP)
    assert "missing_block_steps" in missing_fails, f"블록 누락을 못 잡음: {missing_fails}"

    # ★ 회귀 — itemCount가 요청과 다름
    wrong_count = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 2},
        {"type": "steps", "itemCount": 3}, {"type": "cta"},
    ]}, ensure_ascii=False)
    wc_fails, _ = check_structure(wrong_count, _KEEP)
    assert "wrong_item_count_benefits_want3_got2" in wc_fails, f"잘못된 itemCount를 못 잡음: {wc_fails}"

    # ★ 회귀 — notices는 forbidden, 그 외 요청 안 한 블록은 unexpected로 구분
    notices_leak = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 3},
        {"type": "steps", "itemCount": 3}, {"type": "cta"}, {"type": "notices"},
    ]}, ensure_ascii=False)
    nl_fails, _ = check_structure(notices_leak, _KEEP)
    assert "forbidden_block_notices" in nl_fails, f"notices 유입을 못 잡음: {nl_fails}"

    extra_block = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 3},
        {"type": "steps", "itemCount": 3}, {"type": "cta"},
        {"type": "countdown"},
    ]}, ensure_ascii=False)
    eb_fails, _ = check_structure(extra_block, _KEEP)
    assert "unexpected_block_countdown" in eb_fails, f"요청 안 한 블록 추가를 못 잡음: {eb_fails}"

    # ★ 회귀 — 선택 블록(countdown/faq/tabs)이 keep_counts에 있으면 정상 채점된다.
    countdown_keep = {"hero": None, "benefits": 2, "cta": None, "countdown": None}
    countdown_good = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 2},
        {"type": "cta"}, {"type": "countdown"},
    ]}, ensure_ascii=False)
    assert check_structure(countdown_good, countdown_keep)[0] == [], \
        "countdown이 포함된 정상 구조가 실패로 잡힘"
    countdown_with_count = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 2},
        {"type": "cta"}, {"type": "countdown", "itemCount": 3},
    ]}, ensure_ascii=False)
    cc_fails, _ = check_structure(countdown_with_count, countdown_keep)
    assert "unexpected_block_countdown" not in cc_fails  # 존재 자체는 정상
    # countdown 스키마엔 itemCount 자리가 아예 없으므로(additionalProperties:false),
    # 실제 LLM 호출에서는 이 조합이 애초에 문법적으로 생성 불가능하다 — 여기서는
    # check_structure가 "있으면 안 되는데 있다"를 문제 삼지 않는다는 계약만 문서화한다
    # (스키마가 이미 원천 차단하므로 이중 검사를 안 만든 것).

    # ★ 회귀 — ANY_COUNT: 정확한 개수 비교 없이 "itemCount가 있는지"만 본다.
    any_keep = {"hero": None, "benefits": ANY_COUNT, "cta": None}
    any_good = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 2}, {"type": "cta"},
    ]}, ensure_ascii=False)
    assert check_structure(any_good, any_keep)[0] == [], "ANY_COUNT인데 2~4 범위 값을 실패로 잡음"
    any_good2 = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits", "itemCount": 4}, {"type": "cta"},
    ]}, ensure_ascii=False)
    assert check_structure(any_good2, any_keep)[0] == [], "ANY_COUNT인데 다른 유효값(4)을 실패로 잡음"
    any_missing_count = json.dumps({"blocks": [
        {"type": "hero"}, {"type": "benefits"}, {"type": "cta"},
    ]}, ensure_ascii=False)
    amc_fails, _ = check_structure(any_missing_count, any_keep)
    assert "missing_item_count_benefits" in amc_fails, \
        f"ANY_COUNT인데 itemCount 자체가 없는 걸 못 잡음: {amc_fails}"

    # ★ 회귀 — J-STRUCT-V 스키마: variant가 실제로 enum(등록된 이름만)인지.
    v_variants = {v["properties"]["type"]["const"]: v for v in
                  STRUCTURE_SCHEMA_V["properties"]["blocks"]["items"]["oneOf"]}
    assert "variant" in v_variants["hero"]["properties"], "J-STRUCT-V에 variant 필드가 없음"
    assert set(v_variants["benefits"]["properties"]["variant"]["enum"]) == \
        set(BLOCK_VARIANT_NAMES["benefits"]), "benefits variant enum이 레지스트리와 어긋남"
    assert "variant" in v_variants["hero"]["required"]

    # ★ 회귀 — check_structure의 variant 검사(누락/미등록 이름)
    v_keep = {"hero": None, "benefits": 3, "steps": 3, "cta": None}
    v_good = json.dumps({"blocks": [
        {"type": "hero", "variant": "flowbite_split"},
        {"type": "benefits", "variant": "flowbite_cards", "itemCount": 3},
        {"type": "steps", "variant": "hyperui_numbered", "itemCount": 3},
        {"type": "cta", "variant": "flowbite_banner"},
    ]}, ensure_ascii=False)
    assert check_structure(v_good, v_keep, variant_names=BLOCK_VARIANT_NAMES)[0] == [], \
        "정상 variant 조합이 실패로 잡힘"

    v_missing = json.dumps({"blocks": [
        {"type": "hero"},
        {"type": "benefits", "variant": "flowbite_cards", "itemCount": 3},
        {"type": "steps", "variant": "hyperui_numbered", "itemCount": 3},
        {"type": "cta", "variant": "flowbite_banner"},
    ]}, ensure_ascii=False)
    vm_fails, _ = check_structure(v_missing, v_keep, variant_names=BLOCK_VARIANT_NAMES)
    assert "missing_variant_hero" in vm_fails, f"variant 누락을 못 잡음: {vm_fails}"

    v_invalid = json.dumps({"blocks": [
        {"type": "hero", "variant": "made_up_style"},
        {"type": "benefits", "variant": "flowbite_cards", "itemCount": 3},
        {"type": "steps", "variant": "hyperui_numbered", "itemCount": 3},
        {"type": "cta", "variant": "flowbite_banner"},
    ]}, ensure_ascii=False)
    vi_fails, _ = check_structure(v_invalid, v_keep, variant_names=BLOCK_VARIANT_NAMES)
    assert "invalid_variant_hero" in vi_fails, f"등록 안 된 variant를 못 잡음: {vi_fails}"

    print("  [cases_jstruct] self_check 통과")
