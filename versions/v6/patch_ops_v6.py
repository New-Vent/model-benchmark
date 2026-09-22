"""
patch_ops_v6.py — v6가 새로 필요로 하는 패치 오퍼레이션 + 실행 헬퍼
====================================================================
`base/checks.py`·`base/registry.py`는 그대로 둔다(팀 합의 없이 개인이
고치지 않는다는 원칙 — docs/common/methodology.md). 이 파일은 v4의 checks_v4.py와
같은 자리, 즉 "v6가 새로 요구하는 것만 얹는" 버전 전용 확장이다.

## 왜 새 오퍼레이션이 필요한가 (v4 KT3/KT5에서 실측으로 드러난 표현력 격차)

base/checks.py의 오퍼레이션 집합은 set_field·append_item·remove_block·
add_block·set_theme·apply_preset 여섯 가지다. 그런데:

  KT3 "혜택 항목 중 마지막 하나를 삭제해줘"
      → 배열에서 항목 하나만 지우는 오퍼레이션이 없다. remove_block은
        블록 전체를 지우고, set_field의 value는 스키마 상 문자열
        하나뿐이라(build_patch_json_schema) 배열을 통째로 못 담는다.
        "항목 하나만 지운다"를 문법적으로 표현할 방법이 아예 없었다.

  KT5 "각 단계 설명을 더 짧고 간결하게, 단계 개수는 그대로"
      → 기존 항목의 텍스트를 그 자리에서 바꾸는 오퍼레이션도 없다.
        append_item은 추가만 하고, remove_block+add_block으로 우회하면
        순서·다른 항목 보존을 전부 다시 책임져야 해서 "최소 패치"
        원칙에 어긋난다.

v4 README가 "K는 구조 변경을 못 한다"·"지배적 실패는 no_ops"라고 기록한
현상의 일부는 모델이 무능해서가 아니라, **애초에 스키마가 그 변경을
표현할 문법을 안 줬기 때문**일 수 있다는 게 이 파일의 가설이다. 그래서
remove_item·replace_item 두 개를 추가하고, v6는 이 가설 자체를
KT(구식 스키마 없이 그대로) 대비 K-T5(신식 스키마)로 직접 재본다.

## 매칭 규칙 — 두 가지 "지목" 방식을 나란히 둔다

**K-T5/K-FS/RK(기본, `_v6` 계열)는 value/old_value로, 즉 항목 텍스트로
가리킨다.** 모델이 자연어 요청("마지막 거 지워줘")을 받아도 현재
계획(JSON)에 항목 텍스트가 그대로 보이므로, 그 텍스트를 값으로 내는 게
인덱스를 세는 것보다 자연스러울 거라는 가정이었다. 서버는 정확히 일치 →
부분 일치(포함) 순으로 관대하게 찾고, 못 찾으면 `item_not_found_<block>`로
실패 처리한다.

**실측 결과 이 가정이 틀렸다** — remove_item(KT3)이 스키마 신설 이후에도
0%였는데, 원인을 열어보니 모델이 "정확한 현재 문구 없이 제거할 항목을
지정해야 합니다"라며 아예 시도조차 안 하는 경우가 태반이었다(원문 재현
자체에 대한 확신 부족). 그래서 **K-IDX(`_v6_idx` 계열)를 추가로 만들어
같은 요청을 "몇 번째 항목인지"(정수 index, 0부터)로만 지목하게 한다** —
프롬프트에 항목별 번호를 미리 매겨서 보여주면, 모델이 할 일은 "긴 문장을
토씨 하나 안 틀리고 베끼기"에서 "이미 번호 매겨진 목록에서 하나를
고르기"로 줄어든다. 두 방식 모두 대상을 못 찾으면(텍스트 불일치 /
범위 밖 index) 조용히 넘어가지 않고 각각 `item_not_found_<block>` /
`index_out_of_range_<block>`로 실패 처리한다 — "오퍼레이션 종류는
맞았는데 대상을 잘못 짚었다"를 놓치지 않기 위해서다(이런 의미 오류는
base/checks.py의 구조 검증만으로는 안 잡힌다).

## mode="custom"을 쓰는 이유

engine.py의 run_one()은 mode=="patch"일 때 base/checks.py의 check_patch를
하드코딩으로 부른다(순수 함수 인자로 바꿔주지 않는 한 v6 스키마를 못
꽂는다). base/engine.py는 공통 파일이라 개인이 고치지 않으므로, v3의
cases_chain.py가 이미 썼던 것과 같은 탈출구를 쓴다 — mode="custom" +
자체 재시도 루프. 이 파일의 run_patch_stage/run_router_stage가 그
재시도 루프이고, cases_kt.py·cases_route_patch.py가 이걸 공유해서 쓴다.
"""

import json

import engine
from checks import SOFT_FAILS, check_html, diff_unintended_changes as _base_diff_unintended
from registry import BY_KEY, SERVER, LLM_BLOCKS, THEME_FIELDS, STYLE_PRESETS, render_plan

FENCE_RE = __import__("re").compile(r"```")

ITEM_BLOCK_KEYS = [b.key for b in LLM_BLOCKS if b.min_items > 0]
# 실측(레지스트리 기준): benefits, steps, faq, tabs — hero/cta는 items가 없다.

BASE_VALID_KINDS = {"set_field", "append_item", "remove_block", "add_block",
                     "set_theme", "apply_preset"}
V6_NEW_KINDS = {"remove_item", "replace_item"}
VALID_KINDS_V6 = BASE_VALID_KINDS | V6_NEW_KINDS


# ══════════════════════════════════════════════════════════════
#  스키마
# ══════════════════════════════════════════════════════════════

def build_patch_json_schema_v6() -> dict:
    """registry.build_patch_json_schema()와 같은 구조에 remove_item·
    replace_item 두 variant만 더한다. add_block은 v6 범위(문구/항목
    수준 편집)에 없으므로 base와 동일하게 variant 선택 없이 둔다
    (필요해지면 그때 add_block_variants를 CHAIN 방식으로 추가)."""
    block_keys = [b.key for b in LLM_BLOCKS]
    theme_fields = list(THEME_FIELDS)
    preset_names = list(STYLE_PRESETS)

    op_variants = [
        {"type": "object", "properties": {
            "op": {"const": "set_field"},
            "block_key": {"type": "string", "enum": block_keys},
            "field": {"type": "string"},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "append_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "replace_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "old_value": {"type": "string"},
            "new_value": {"type": "string"},
        }, "required": ["op", "block_key", "old_value", "new_value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_block"},
            "block_key": {"type": "string", "enum": block_keys},
        }, "required": ["op", "block_key"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "set_theme"},
            "field": {"type": "string", "enum": theme_fields},
            "value": {"type": "string"},
        }, "required": ["op", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "apply_preset"},
            "name": {"type": "string", "enum": preset_names},
        }, "required": ["op", "name"], "additionalProperties": False},
    ]

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["patch", "clarify", "unsupported"]},
            "ops": {"type": "array", "items": {"oneOf": op_variants}},
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


PATCH_SCHEMA_V6 = build_patch_json_schema_v6()


def build_patch_json_schema_v6_idx() -> dict:
    """build_patch_json_schema_v6()과 완전히 같지만, remove_item/replace_item이
    value/old_value(항목 텍스트) 대신 index(0부터 시작하는 정수)로 항목을
    지목한다 — K-IDX 가설(모듈 docstring 참고). 그 외 다섯 오퍼레이션은
    바이트 단위로 동일하다."""
    block_keys = [b.key for b in LLM_BLOCKS]
    theme_fields = list(THEME_FIELDS)
    preset_names = list(STYLE_PRESETS)

    op_variants = [
        {"type": "object", "properties": {
            "op": {"const": "set_field"},
            "block_key": {"type": "string", "enum": block_keys},
            "field": {"type": "string"},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "append_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "index": {"type": "integer", "minimum": 0},
        }, "required": ["op", "block_key", "index"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "replace_item"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "index": {"type": "integer", "minimum": 0},
            "new_value": {"type": "string"},
        }, "required": ["op", "block_key", "index", "new_value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_block"},
            "block_key": {"type": "string", "enum": block_keys},
        }, "required": ["op", "block_key"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "set_theme"},
            "field": {"type": "string", "enum": theme_fields},
            "value": {"type": "string"},
        }, "required": ["op", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "apply_preset"},
            "name": {"type": "string", "enum": preset_names},
        }, "required": ["op", "name"], "additionalProperties": False},
    ]

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["patch", "clarify", "unsupported"]},
            "ops": {"type": "array", "items": {"oneOf": op_variants}},
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


PATCH_SCHEMA_V6_IDX = build_patch_json_schema_v6_idx()


def build_router_schema_v6() -> dict:
    """라우터 전용, 아주 좁은 스키마 — op과 target(block_key)만 낸다.
    3.1(라우터 분리)의 핵심은 "판정"과 "값 채우기"를 물리적으로 다른
    호출로 쪼개는 것이므로, 1단계는 값(value)을 아예 요구하지 않는다."""
    block_keys = [b.key for b in LLM_BLOCKS]
    return {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": sorted(VALID_KINDS_V6 | {"rewrite_all", "unclear"})},
            "block_key": {"type": "string", "enum": block_keys + [""]},
        },
        "required": ["op", "block_key"],
        "additionalProperties": False,
    }


ROUTER_SCHEMA_V6 = build_router_schema_v6()


# ══════════════════════════════════════════════════════════════
#  병합 — apply_patch_v6 / apply_patch_v6_idx
# ══════════════════════════════════════════════════════════════

def _find_item_index(items: list, value: str):
    """정확히 일치 → 부분 일치(포함) 순으로 찾는다. 못 찾으면 None."""
    if not isinstance(items, list) or not value:
        return None
    for i, x in enumerate(items):
        if isinstance(x, str) and x == value:
            return i
    for i, x in enumerate(items):
        if isinstance(x, str) and value in x:
            return i
    return None


def _locate_by_value(items: list, op: dict):
    """K-T5/K-FS/RK가 쓰는 지목 방식 — remove_item은 value, replace_item은
    old_value(항목 텍스트)로 가리킨다. (인덱스, 실패 시 기록할 상세정보)를
    반환한다."""
    key = "value" if op.get("op") == "remove_item" else "old_value"
    detail = op.get(key, "")
    return _find_item_index(items, detail), detail


def _locate_by_index(items: list, op: dict):
    """K-IDX가 쓰는 지목 방식 — remove_item/replace_item 둘 다 index(정수,
    0부터)로 가리킨다. bool은 int의 서브클래스라 True/False가 0/1로
    새어들어오지 않도록 명시적으로 제외한다."""
    idx = op.get("index")
    if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(items):
        return idx, idx
    return None, idx


def _merge_ops(current_plan: dict, patch: dict, locate) -> tuple:
    """apply_patch_v6/apply_patch_v6_idx가 공유하는 몸통. remove_item·
    replace_item을 어떻게 지목하는지(locate)만 다르고, 그 외 다섯
    오퍼레이션(set_field·append_item·remove_block·add_block·set_theme·
    apply_preset)은 지목 방식과 무관하게 완전히 동일하다. 반환값은
    (merged_plan, not_found) — not_found는 remove_item/replace_item이
    가리킨 항목을 못 찾은 (block_key, 상세정보) 목록이다."""
    import copy
    blocks = copy.deepcopy(current_plan.get("blocks", []))
    theme = copy.deepcopy(current_plan.get("theme", {}))
    not_found = []

    def find_block(key):
        return next((i for i, b in enumerate(blocks) if b.get("type") == key), None)

    for op in patch.get("ops", []):
        if not isinstance(op, dict):
            continue
        kind = op.get("op")

        if kind == "set_field":
            i = find_block(op.get("block_key"))
            if i is not None and isinstance(op.get("field"), str):
                blocks[i][op["field"]] = op.get("value", "")

        elif kind == "append_item":
            i = find_block(op.get("block_key"))
            if i is not None:
                blocks[i].setdefault("items", [])
                if isinstance(blocks[i]["items"], list):
                    blocks[i]["items"].append(op.get("value", ""))

        elif kind in ("remove_item", "replace_item"):
            i = find_block(op.get("block_key"))
            if i is not None and isinstance(blocks[i].get("items"), list):
                items = blocks[i]["items"]
                j, detail = locate(items, op)
                if j is None:
                    not_found.append((op.get("block_key"), detail))
                elif kind == "remove_item":
                    items.pop(j)
                else:
                    items[j] = op.get("new_value", "")

        elif kind == "remove_block":
            i = find_block(op.get("block_key"))
            if i is not None:
                blocks.pop(i)

        elif kind == "add_block":
            new_block = {k: v for k, v in op.items() if k != "op"}
            if BY_KEY.get(new_block.get("type")) is not None:
                blocks.append(new_block)

        elif kind == "set_theme":
            field = op.get("field")
            if field in THEME_FIELDS:
                _, validator = THEME_FIELDS[field]
                if validator(op.get("value")):
                    theme[field] = op.get("value")

        elif kind == "apply_preset":
            preset = STYLE_PRESETS.get(op.get("name"))
            if preset is not None:
                theme.update(preset)

    return {"blocks": blocks, "theme": theme}, not_found


def apply_patch_v6(current_plan: dict, patch: dict) -> tuple:
    """base/checks.py의 apply_patch와 같은 계약(딥카피·부작용 없음)에
    remove_item·replace_item 두 분기만 더한다 — 항목은 텍스트(value/
    old_value)로 지목한다. not_found는 check_patch_v6가 item_not_found_*
    실패를 매기는 데 쓴다."""
    return _merge_ops(current_plan, patch, _locate_by_value)


def apply_patch_v6_idx(current_plan: dict, patch: dict) -> tuple:
    """apply_patch_v6와 계약은 같지만 remove_item·replace_item을 텍스트 대신
    index(정수)로 지목한다 — K-IDX 가설. not_found는 check_patch_v6_idx가
    index_out_of_range_* 실패를 매기는 데 쓴다."""
    return _merge_ops(current_plan, patch, _locate_by_index)


def diff_unintended_changes_v6(current_plan: dict, merged: dict, ops: list) -> list:
    """base checks.diff_unintended_changes와 같은 취지지만, remove_item·
    replace_item도 "그 블록을 정당하게 건드렸다"로 인정한다. 이게 없으면
    remove_item으로 benefits를 정상 수정해도 diff가 "선언 안 된 변경"으로
    오판한다 — base 함수는 remove_item/replace_item을 모르기 때문이다."""
    extra_touched = {op.get("block_key") for op in ops
                     if isinstance(op, dict) and op.get("op") in ("remove_item", "replace_item")}
    ops_without_v6 = [op for op in ops
                       if not (isinstance(op, dict) and op.get("op") in ("remove_item", "replace_item"))]
    unexpected = _base_diff_unintended(current_plan, merged, ops_without_v6)
    return [t for t in unexpected if t not in extra_touched]


# ══════════════════════════════════════════════════════════════
#  검증 — check_patch_v6 / check_patch_v6_idx
# ══════════════════════════════════════════════════════════════

def _check_patch_common(raw, current_plan, keep, forbid, assume_supported,
                         apply_fn, not_found_fail):
    """check_patch_v6/check_patch_v6_idx가 공유하는 몸통. apply_fn(텍스트
    매칭이냐 인덱스냐)과 not_found_fail(실패 이름 접두사)만 다르고, 문법
    검증·렌더링·unintended 검사는 완전히 동일하다.

    assume_supported: 이 케이스가 요청하는 편집이 VALID_KINDS_V6로 표현
    가능하다는 걸 호출자가 이미 알고 있을 때(K-T5/K-FS/RK/K-IDX처럼
    remove_item·replace_item을 시험하려고 만든 케이스는 전부 여기 해당)
    True로 넘긴다. True면 action=="unsupported"는 reason 내용과 무관하게
    항상 하드 실패다 — "왜 거부했는지" 텍스트를 해석해서 판정하지 않는다."""
    text = FENCE_RE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], "JSON을 찾을 수 없습니다.", None, ""
    try:
        patch = json.loads(text[s:e + 1])
    except Exception as ex:
        return ["bad_json"], f"JSON 파싱 실패: {ex}", None, ""

    fails, notes = [], []
    action = patch.get("action")
    if action is None and isinstance(patch.get("ops"), list):
        action = "patch"
    if action not in ("patch", "clarify", "unsupported"):
        return ["unknown_action"], "action이 patch/clarify/unsupported 중 하나여야 합니다.", None, ""

    if action == "clarify":
        if not patch.get("question") or not isinstance(patch.get("options"), list) \
                or len(patch["options"]) < 2:
            fails.append("bad_clarify")
        return fails, " ".join(notes), None, ""
    if action == "unsupported":
        reason = patch.get("reason") or ""
        if not reason:
            fails.append("missing_reason")
        elif assume_supported:
            # reason에 아무 문자열이나(심지어 사실과 다른 "이미 지웠습니다" 같은
            # 주장을) 적으면 통과시키던 원래 규칙(base/checks.py check_patch와
            # 동일)은 v4까지는 맞았다 — remove_item/replace_item이 없었을 때는
            # "구조 변경은 지원 안 함"이 사실이었기 때문이다. v6가 그 오퍼레이션을
            # 추가한 뒤에도 이 규칙을 그대로 두면, 모델이 새 오퍼레이션을 쓰지
            # 않고 그냥 반려해도(reason이 "remove_item"이라는 이름만 대든,
            # "이미 삭제했습니다"처럼 텍스트만으로 완료를 주장하든) hard_ok=1로
            # 잡힌다 — 실측에서 둘 다 실제로 발생했다. 이름 언급 여부로 판정하는
            # 방식은 이름을 안 쓰고 자연어로만 거짓 주장하는 경우를 놓쳐서(실측
            # 3건), 이 케이스군에서는 텍스트 해석 없이 "unsupported 자체가 항상
            # 틀렸다"로 못박는다 — 호출자가 이 편집이 스키마로 표현 가능하다고
            # 이미 보장했기 때문이다(assume_supported 문서 참고).
            fails.append("unsupported_rejected")
            notes.append("이 요청은 remove_item/replace_item으로 표현 가능합니다. "
                         "unsupported로 거부하지 말고 실제 패치를 내세요.")
        return fails, " ".join(notes), None, ""

    ops = patch.get("ops")
    if not isinstance(ops, list) or not ops:
        return fails + ["no_ops"], "ops 배열이 없습니다.", patch, ""

    item_block_keys = {b.get("type") for b in current_plan.get("blocks", [])
                        if isinstance(b.get("items"), list)}
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in VALID_KINDS_V6:
            fails.append("unknown_op")
            continue
        if op.get("op") in ("set_field", "append_item", "remove_block",
                             "remove_item", "replace_item"):
            bk = op.get("block_key")
            if bk not in [b["type"] for b in current_plan.get("blocks", [])]:
                fails.append("unknown_block_key")
            if bk in [k for k, b in BY_KEY.items() if b.source == SERVER]:
                fails.append("touched_server_block")
        if op.get("op") in ("append_item", "remove_item", "replace_item"):
            bk = op.get("block_key")
            if bk is not None and bk not in item_block_keys and bk in [
                    b["type"] for b in current_plan.get("blocks", [])]:
                fails.append(f"not_item_block_{bk}")

    merged, not_found = apply_fn(current_plan, patch)
    for block_key, detail in not_found:
        fails.append(f"{not_found_fail}_{block_key}")
        notes.append(f"{block_key}에서 지정한 항목({detail!r})을 찾지 못했습니다.")

    rendered = render_plan(merged)
    rf, rn = check_html(rendered, rendered, keep, forbid, True)
    fails += rf
    if rn:
        notes.append(rn)

    unexpected = diff_unintended_changes_v6(current_plan, merged, ops)
    for t in unexpected:
        fails.append(f"unintended_side_effect_{t}")

    if len([o for o in ops if isinstance(o, dict)]) >= 2:
        fails.append("excess_ops_review")

    return fails, " ".join(notes), merged, rendered


def check_patch_v6(raw, current_plan, keep, forbid, assume_supported=False):
    """base/checks.py의 check_patch와 같은 반환 계약
    (fails, notes, merged, rendered)이지만 v6 오퍼레이션·스키마를 안다.
    remove_item/replace_item은 항목 텍스트(value/old_value)로 지목한다
    (K-T5/K-FS/RK가 씀)."""
    return _check_patch_common(raw, current_plan, keep, forbid, assume_supported,
                                apply_patch_v6, "item_not_found")


def check_patch_v6_idx(raw, current_plan, keep, forbid, assume_supported=False):
    """check_patch_v6와 계약은 같지만 remove_item/replace_item을 index(정수)로
    지목한다(K-IDX가 씀). 텍스트 매칭 실패(item_not_found) 대신 범위 밖
    인덱스(index_out_of_range)만 문제가 된다."""
    return _check_patch_common(raw, current_plan, keep, forbid, assume_supported,
                                apply_patch_v6_idx, "index_out_of_range")


# ══════════════════════════════════════════════════════════════
#  실행 헬퍼 — mode="custom" 케이스가 공유하는 단일 스테이지 러너
#  (v3 cases_chain.py의 _run_stage를 patch/router 전용으로 특화한 것)
# ══════════════════════════════════════════════════════════════

def run_patch_stage(model, runner, digest, backend, repeat_no, seed, rows, out_dir,
                     pid, kind, group, pair, system, prompt, current_plan,
                     keep=(), forbid=(), extra_check=None, num_predict=None,
                     max_retry=3, assume_supported=False,
                     patch_schema=None, check_fn=None):
    """check_fn(기본 check_patch_v6)으로 채점하는 patch 1단계를 돌린다.
    assume_supported는 그대로 check_fn에 전달된다(check_patch_v6 docstring 참고).
    patch_schema/check_fn을 생략하면 PATCH_SCHEMA_V6/check_patch_v6(텍스트 매칭,
    K-T5/K-FS/RK가 씀) — K-IDX처럼 다른 스키마·검증 함수를 쓰려면 둘 다
    명시적으로 넘긴다(PATCH_SCHEMA_V6_IDX/check_patch_v6_idx).
    반환: (merged_plan_or_None, first_hard_ok, final_hard_ok)"""
    patch_schema = patch_schema if patch_schema is not None else PATCH_SCHEMA_V6
    check_fn = check_fn if check_fn is not None else check_patch_v6
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    first_hard_ok = None

    for attempt in range(1, max_retry + 1):
        try:
            res = engine.call(model, messages, mode="patch", as_json=True, seed=seed,
                               json_schema=patch_schema, num_predict_override=num_predict)
        except Exception:
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group=group, prompt_id=pid, kind=kind, pair=pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error"))
            return None, first_hard_ok or 0, 0

        raw = res["message"]["content"]
        fails, note, merged, rendered = check_fn(
            raw, current_plan, keep, forbid, assume_supported=assume_supported)
        out_len, html_len = len(raw.strip()), len(rendered)

        if extra_check is not None:
            fails += extra_check(raw, merged)

        if res.get("done_reason") == "length":
            fails.append("truncated")

        soft = [f for f in fails if f in SOFT_FAILS]
        hard = [f for f in fails if f not in SOFT_FAILS]
        hard_ok = int(not hard)
        if first_hard_ok is None:
            first_hard_ok = hard_ok

        pc, ec = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
        pd, ed = res.get("prompt_eval_duration", 1), res.get("eval_duration", 1)
        rows.append(engine._empty_row(
            runner=runner, model=model, digest=digest, backend=backend,
            group=group, prompt_id=pid, kind=kind, pair=pair,
            repeat_no=repeat_no, seed=seed, attempt=attempt,
            hard_ok=hard_ok, all_ok=int(not fails),
            fails="|".join(hard), soft_fails="|".join(soft),
            wall_sec=res["_wall_sec"],
            load_ms=res.get("load_duration", 0) // 1_000_000,
            prompt_ms=pd // 1_000_000, eval_ms=ed // 1_000_000,
            prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
            prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
            eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
            out_len=out_len, html_len=html_len,
            done_reason=res.get("done_reason", "")))

        safe = model.replace(":", "_")
        base = f"{out_dir}/{safe}_{pid}_r{repeat_no}_s{seed}_try{attempt}"
        with open(f"{base}.txt", "w", encoding="utf-8") as f:
            f.write(raw)
        if rendered:
            with open(f"{base}.rendered.html", "w", encoding="utf-8") as f:
                f.write(rendered)

        if hard_ok:
            return merged, first_hard_ok, 1

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                          "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

    return None, first_hard_ok or 0, 0


def run_router_stage(model, runner, digest, backend, repeat_no, seed, rows, out_dir,
                      pid, kind, group, pair, system, prompt, expected_op=None,
                      expected_block_key=None, num_predict=None, max_retry=1):
    """1단계(라우팅)만 돈다 — 렌더링 없이 op/block_key JSON만 검증한다.
    max_retry 기본값 1 — 라우팅은 재시도로 답을 바꾸게 유도하지 않고
    "한 번에 맞히는가"를 그대로 잰다(3.1의 취지: 판정 자체의 신뢰도 측정).
    반환: (decision_dict_or_None, first_hard_ok, final_hard_ok)"""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    first_hard_ok = None

    for attempt in range(1, max_retry + 1):
        try:
            res = engine.call(model, messages, mode="router", as_json=True, seed=seed,
                               json_schema=ROUTER_SCHEMA_V6, num_predict_override=num_predict)
        except Exception:
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group=group, prompt_id=pid, kind=kind, pair=pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error"))
            return None, first_hard_ok or 0, 0

        raw = res["message"]["content"]
        fails = []
        decision = None
        try:
            decision = json.loads(raw.strip())
        except Exception:
            fails.append("router_bad_json")

        if decision is not None:
            if expected_op is not None and decision.get("op") != expected_op:
                fails.append(f"router_wrong_op_want_{expected_op}_got_{decision.get('op')}")
            if expected_block_key is not None and decision.get("block_key") != expected_block_key:
                fails.append(f"router_wrong_target_want_{expected_block_key}_"
                             f"got_{decision.get('block_key')}")

        if res.get("done_reason") == "length":
            fails.append("truncated")

        hard = fails  # 라우터군은 soft/hard 구분 없음 — 전부 hard
        hard_ok = int(not hard)
        if first_hard_ok is None:
            first_hard_ok = hard_ok

        pc, ec = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
        pd, ed = res.get("prompt_eval_duration", 1), res.get("eval_duration", 1)
        rows.append(engine._empty_row(
            runner=runner, model=model, digest=digest, backend=backend,
            group=group, prompt_id=pid, kind=kind, pair=pair,
            repeat_no=repeat_no, seed=seed, attempt=attempt,
            hard_ok=hard_ok, all_ok=hard_ok,
            fails="|".join(hard),
            wall_sec=res["_wall_sec"],
            load_ms=res.get("load_duration", 0) // 1_000_000,
            prompt_ms=pd // 1_000_000, eval_ms=ed // 1_000_000,
            prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
            prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
            eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
            out_len=len(raw.strip()), html_len=len(raw.strip()),
            done_reason=res.get("done_reason", "")))

        safe = model.replace(":", "_")
        base = f"{out_dir}/{safe}_{pid}_r{repeat_no}_s{seed}_try{attempt}"
        with open(f"{base}.txt", "w", encoding="utf-8") as f:
            f.write(raw)

        if hard_ok:
            return decision, first_hard_ok, 1

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": "형식이 올바르지 않습니다. JSON만 다시 출력하세요."})

    return None, first_hard_ok or 0, 0
