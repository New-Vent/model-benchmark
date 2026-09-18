"""
cases_kcount.py — K-COUNT군: "삭제"라는 이름을 아예 안 쓰고 itemCount만 바꾼다
========================================================================
K-T5(`remove_item`, 텍스트 지목)·K-IDX(`remove_item`, 인덱스 지목) 둘 다
KT3("혜택 마지막 하나 삭제")에서 정확히 0%였다. raw 응답을 열어보면
"정확한 현재 문구 없이 지정해야 합니다"(exaone)처럼 지목 방법이 문제가
아니라, `remove_item`이라는 **"삭제" 이름이 붙은 오퍼레이션을 고르는
행위 자체**를 회피하는 것으로 보였다(인덱스를 줘도, 참고표를 줘도 그냥
"clarify"·"unsupported"로 도망감).

이 파일은 그 이름 자체를 없앤다. `set_field`는 이미 100%로 검증된
오퍼레이션이다(버튼 문구·제목 교체). `itemCount`도 결국 그 블록의 필드
하나일 뿐이므로, "혜택 하나 지워줘"를

    {"op":"remove_item", ...}          ← 4번 다 실패했던 표현
    {"op":"set_field","block_key":"benefits","field":"itemCount","value":2}
                                        ← 이번에 시도하는 표현. "삭제"라는
                                          단어가 스키마에도 모델의 출력
                                          어디에도 등장하지 않는다

로 바꿔서 표현하게 한다. 어떤 항목이 없어지는지는 이 군의 관심사가
아니다(그건 UI가 처리한다는 게 세션 결론) — "itemCount라는 숫자 하나를
바꾸는 걸 순순히 하는가"만 잰다.

## J-STRUCT와의 연결 — 왜 baseline이 "구조"뿐이고 실제 콘텐츠가 없는가

이 군은 K-T5/K-FS/K-IDX(실제 템플릿 콘텐츠를 baseline으로 씀,
`cases_se.py`/`templates.py`)와 **baseline 자체가 다르다.** 세션에서
정리된 다음 설계를 그대로 반영했다 — "신규 생성은 J-STRUCT(구조만) →
사람이 폼 채움 → 수정도 구조 변경만 LLM이 담당, 텍스트는 폼을 다시
열어 고침." 그래서 이 군의 baseline은 J-STRUCT가 실제로 만들어내는
그 "구조만" 표현(`{"blocks":[{"type":"hero"}, ...]}`, 문구 없음)이고,
K-T5처럼 실제 문구가 채워진 템플릿이 아니다.

**따라서 K-T5의 KT3/KT4와 요청 문구는 같게 맞췄지만(`self_check`가
검증) 완전한 pair는 아니다** — baseline의 성격 자체가 다르기 때문이다
(K-T5: 실제 콘텐츠 있음 / K-COUNT: 구조만). 통과율을 직접 빼서 비교하지
말고, "같은 요청인데 오퍼레이션 이름만 바꾸면 회피 반사가 사라지는가"
라는 질문에만 쓸 것.

engine.py 표준 mode="patch"는 base/checks.py의 check_patch를 하드코딩으로
쓰므로(이 파일의 좁은 전용 스키마를 못 꽂음), mode="custom"을 쓴다 —
patch_ops_v6.py와 같은 탈출구.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

import json
import re

from engine import Case
import engine

from registry import LLM_BLOCKS

GROUPS = ["K-COUNT"]

FENCE_RE = re.compile(r"```")

ITEM_BLOCK_KEYS = [b.key for b in LLM_BLOCKS if any("items" in v.fields for v in b.variants)]
MIN_ITEMS = {b.key: max(b.min_items, 1) for b in LLM_BLOCKS if b.key in ITEM_BLOCK_KEYS}

NUM_PREDICT_COUNT = 150  # {"action":"patch","ops":[{"op":"set_field",...}]} 수준 — 아주 짧다

# J-STRUCT가 실제로 만들어내는 것과 같은 모양의 "구조만" baseline.
# (cases_jstruct.py의 STRUCT1과 동일한 구조 — 문구는 전혀 없다.)
BASELINE_STRUCTURE = {
    "blocks": [
        {"type": "hero"},
        {"type": "benefits", "itemCount": 3},
        {"type": "steps", "itemCount": 3},
        {"type": "cta"},
    ],
}


def build_count_patch_schema() -> dict:
    """set_field 중에서도 field가 반드시 "itemCount"인 것만 허용하는 좁은
    스키마. block_key는 항목이 있는 블록(benefits/steps/faq/tabs)만,
    value는 정수 2~4만 — "삭제"·"추가" 같은 동사가 스키마 어디에도 없다."""
    op_variant = {
        "type": "object",
        "properties": {
            "op": {"const": "set_field"},
            "block_key": {"type": "string", "enum": ITEM_BLOCK_KEYS},
            "field": {"const": "itemCount"},
            "value": {"type": "integer", "minimum": 2, "maximum": 4},
        },
        "required": ["op", "block_key", "field", "value"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["patch", "clarify", "unsupported"]},
            "ops": {"type": "array", "items": op_variant},
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


COUNT_PATCH_SCHEMA = build_count_patch_schema()

SYSTEM = f"""너는 이벤트 페이지의 구성 계획(JSON)을 수정하는 도우미다.

아래가 현재 구조다. 문구는 없고 블록 종류·개수만 있다.

현재 구조:
{json.dumps(BASELINE_STRUCTURE, ensure_ascii=False, indent=2)}

요청에 맞게 바뀌어야 할 블록의 itemCount만 set_field로 바꾼다. 다른
블록은 절대 건드리지 마라.

{{"op":"set_field","block_key":"benefits","field":"itemCount","value":2}}

규칙:
- field는 항상 "itemCount"다.
- value는 새로운 항목 개수(정수, 2~4)다.
- 요청받은 블록 하나만 바꾼다. 여러 블록을 동시에 바꾸지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


def check_count_patch(raw: str, block_key: str, want_count: int,
                       assume_supported: bool = True) -> tuple:
    """반환: (fails, note). assume_supported=True(기본, 이 군이 실제로 씀)면
    action=="unsupported"/"clarify"는 reason 유무와 무관하게 항상 하드
    실패다 — itemCount 변경은 이 스키마로 항상 표현 가능하다고 호출자가
    이미 보장했기 때문이다(patch_ops_v6.check_patch_v6의 assume_supported와
    같은 계약)."""
    text = FENCE_RE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], "JSON을 찾을 수 없습니다."
    try:
        patch = json.loads(text[s:e + 1])
    except Exception as ex:
        return ["bad_json"], f"JSON 파싱 실패: {ex}"

    action = patch.get("action")
    if action is None and isinstance(patch.get("ops"), list):
        action = "patch"
    if action not in ("patch", "clarify", "unsupported"):
        return ["unknown_action"], "action이 patch/clarify/unsupported 중 하나여야 합니다."

    if action in ("clarify", "unsupported"):
        if assume_supported:
            return ["unsupported_rejected"], (
                f"이 요청은 set_field로 {block_key}의 itemCount를 바꾸면 표현 가능합니다. "
                f"거부하지 말고 실제 패치를 내세요.")
        if action == "unsupported" and not patch.get("reason"):
            return ["missing_reason"], "reason이 없습니다."
        if action == "clarify" and (not patch.get("question")
                                     or not isinstance(patch.get("options"), list)
                                     or len(patch["options"]) < 2):
            return ["bad_clarify"], "question/options가 부족합니다."
        return [], ""

    ops = patch.get("ops")
    if not isinstance(ops, list) or not ops:
        return ["no_ops"], "ops 배열이 없습니다."

    fails, notes = [], []
    target_ops = [o for o in ops if isinstance(o, dict) and o.get("block_key") == block_key]
    other_ops = [o for o in ops if isinstance(o, dict) and o.get("block_key") != block_key]

    if not target_ops:
        fails.append(f"missing_op_{block_key}")
        notes.append(f"{block_key}의 itemCount를 바꾸는 오퍼레이션이 없습니다.")
    else:
        got = target_ops[0].get("value")
        if got != want_count:
            fails.append(f"wrong_item_count_{block_key}_want{want_count}_got{got}")
            notes.append(f"{block_key}의 itemCount가 {want_count}이어야 하는데 {got}입니다.")

    for o in other_ops:
        fails.append(f"unintended_side_effect_{o.get('block_key')}")
        notes.append(f"요청하지 않은 블록({o.get('block_key')})을 건드렸습니다.")

    if len(target_ops) > 1:
        fails.append("excess_ops_review")

    return fails, " ".join(notes)


def _custom_run(pid, kind, prompt, block_key, want_count, max_retry=3):
    def _run(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        first_hard_ok = None

        for attempt in range(1, max_retry + 1):
            try:
                res = engine.call(model, messages, mode="patch", as_json=True, seed=seed,
                                   json_schema=COUNT_PATCH_SCHEMA,
                                   num_predict_override=NUM_PREDICT_COUNT)
            except Exception:
                rows.append(engine._empty_row(
                    runner=runner, model=model, digest=digest, backend=backend,
                    group="K-COUNT", prompt_id=pid, kind=kind, pair=case.pair,
                    repeat_no=repeat_no, seed=seed, attempt=attempt,
                    hard_ok=0, all_ok=0, fails="request_error"))
                return first_hard_ok or 0, 0

            raw = res["message"]["content"]
            fails, note = check_count_patch(raw, block_key, want_count)
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
                group="K-COUNT", prompt_id=pid, kind=kind, pair=case.pair,
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


def _case(pid, kind, prompt, block_key, want_count, pair=""):
    return Case(
        pid, kind, "K-COUNT", "", prompt, "custom",
        keep=[block_key], forbid=[], pair=pair,
        custom_run=_custom_run(pid, kind, prompt, block_key, want_count),
    )


# KCOUNT1/2는 cases_kt.py의 KT3/KT4와 같은 요청 문구를 쓴다(완전한 pair는
# 아님 — 모듈 docstring 참고). KCOUNT3/4는 steps로 같은 방향(삭제/추가)을
# 한 번 더 본다.
CASES = [
    _case("KCOUNT1", "개수변경_혜택삭제", "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘.",
          "benefits", 2, pair="KT3"),
    _case("KCOUNT2", "개수변경_혜택추가", "이 영역에 혜택 항목을 하나 더 추가해줘.",
          "benefits", 4, pair="KT4"),
    _case("KCOUNT3", "개수변경_단계삭제", "이 영역의 참여 단계 중 마지막 하나를 삭제해줘.",
          "steps", 2),
    _case("KCOUNT4", "개수변경_단계추가", "이 영역에 참여 단계를 하나 더 추가해줘.",
          "steps", 4),
]


def self_check():
    assert len(CASES) == 4, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "K-COUNT"
        assert c.mode == "custom"
        assert c.custom_run is not None

    # ★ 스키마 — "삭제"·"추가" 같은 동사가 스키마 어디에도 없어야 한다.
    #   field는 "itemCount" 하나로 고정(const), op은 set_field 하나뿐이다.
    op_props = COUNT_PATCH_SCHEMA["properties"]["ops"]["items"]["properties"]
    assert op_props["op"]["const"] == "set_field"
    assert op_props["field"]["const"] == "itemCount"
    assert op_props["value"]["type"] == "integer"

    # ★ 회귀 — 정상 patch는 통과해야 한다.
    good = json.dumps({"action": "patch", "ops": [
        {"op": "set_field", "block_key": "benefits", "field": "itemCount", "value": 2}]},
        ensure_ascii=False)
    fails, _ = check_count_patch(good, "benefits", 2)
    assert fails == [], f"정상 patch가 실패로 잡힘: {fails}"

    # ★ 회귀 — 값이 요청과 다르면 잡혀야 한다.
    wrong = json.dumps({"action": "patch", "ops": [
        {"op": "set_field", "block_key": "benefits", "field": "itemCount", "value": 3}]},
        ensure_ascii=False)
    wrong_fails, _ = check_count_patch(wrong, "benefits", 2)
    assert "wrong_item_count_benefits_want2_got3" in wrong_fails, f"잘못된 값을 못 잡음: {wrong_fails}"

    # ★ 회귀 — 요청 안 한 다른 블록을 건드리면 unintended로 잡혀야 한다.
    side_effect = json.dumps({"action": "patch", "ops": [
        {"op": "set_field", "block_key": "benefits", "field": "itemCount", "value": 2},
        {"op": "set_field", "block_key": "steps", "field": "itemCount", "value": 2},
    ]}, ensure_ascii=False)
    se_fails, _ = check_count_patch(side_effect, "benefits", 2)
    assert "unintended_side_effect_steps" in se_fails, f"비대상 변경을 못 잡음: {se_fails}"

    # ★ 회귀 — ops가 아예 없으면 no_ops.
    no_ops = json.dumps({"action": "patch", "ops": []}, ensure_ascii=False)
    no_ops_fails, _ = check_count_patch(no_ops, "benefits", 2)
    assert "no_ops" in no_ops_fails

    # ★ 회귀 — 이 군의 핵심 계약: assume_supported=True(기본)라 이유가 있어도
    #   unsupported/clarify는 항상 하드 실패다(K-T5/K-IDX에서 실제로 터졌던
    #   "reason만 채우면 통과" 버그의 재발 방지 — 처음부터 이 계약으로 짬).
    refusal = json.dumps({"action": "unsupported", "reason": "itemCount"}, ensure_ascii=False)
    refusal_fails, _ = check_count_patch(refusal, "benefits", 2)
    assert "unsupported_rejected" in refusal_fails, f"거부를 못 잡음: {refusal_fails}"

    clarify = json.dumps({"action": "clarify", "question": "몇 개를 지울까요?",
                           "options": ["1개", "2개"]}, ensure_ascii=False)
    clarify_fails, _ = check_count_patch(clarify, "benefits", 2)
    assert "unsupported_rejected" in clarify_fails, f"clarify 거부를 못 잡음: {clarify_fails}"

    # assume_supported=False로 명시하면 정당한 거부는 통과해야 한다(재사용 대비 계약 문서화).
    assert check_count_patch(refusal, "benefits", 2, assume_supported=False)[0] == []

    print("  [cases_kcount] self_check 통과")
