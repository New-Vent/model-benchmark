"""
cases_chain.py — v3 CHAIN2~6: 생성×수정×JS 3축을 실제로 이어 붙인 파이프라인 검증
=====================================================================================
v2의 CHAIN1(J로 생성 → 그 결과를 K로 패치)은 "생성→수정" 2단계만 봤다.
실제 서비스 흐름은 생성→수정→JS(인터랙션 추가)→JS 수정 4단계로 이어지고,
축마다 "HTML 직접" 노선과 "JSON 안전" 노선을 고를 수 있다(v3 README §3).

이 파일이 구현하는 것 — 생성/수정 축과 JS 축을 4가지 조합으로 전부 붙여봤다:

  CHAIN2  J 생성 → K 패치(문구) → JS-PATCH(카운트다운 add_block) → K로 날짜 수정
          — 순수 JSON 노선 4단계
  CHAIN3  S 생성 → E 블록왕복(문구) → JS-HTML(카운트다운 직접작성) → 전체재작성으로 날짜 수정
          — 순수 HTML 노선 4단계
  CHAIN4  J 생성 → K로 구조적 수정(steps 추가) 시도 → 실패하면 E(전체재작성)로 재시도
  CHAIN5  J 생성 → K 패치(문구) → JS-HTML(카운트다운 직접작성) → 전체재작성으로 날짜 수정
          — JSON 생성/수정 + HTML 인터랙션 (교차 조합 1)
  CHAIN6  S 생성 → E 블록왕복(문구) → JS-PATCH류(카운트다운을 JSON 블록으로 "새로 추가")
          → 그 블록만 K로 날짜 수정 — HTML 생성/수정 + JSON 인터랙션 (교차 조합 2)

(옛 CHAIN5/6이던 "E×5/K×5 누적" 실험은 제거했다 — 지금 우선순위는 JS 인터랙션이
"추가"뿐 아니라 "추가된 뒤 수정"까지 파이프라인 전체에서 버티는지 확인하는 쪽이다.)

## CHAIN6이 실제로 막혔던 지점과 우회 방법

S/E는 HTML만 다루고 J/K는 JSON("계획") 위에서 돈다. "S→E로 만든 HTML 위에 JS-PATCH를
잇는다"는 건 원래 그 HTML 전체를 JSON 계획으로 되돌리는 역변환 파서가 있어야 하는데
(v3 README §3 우선순위2 "혼합 노선"이 바로 이 이유로 보류됐다), 그런 파서는 없고 새로
만드는 것도 이번 범위가 아니다.

대신 이 파일은 "새로 추가되는 블록 하나"만 JSON으로 받고, 그 블록만 registry로 렌더링해서
기존 HTML 문서에 이어붙이는 방식(`_run_add_single_block_stage`)으로 우회한다 — add_block은
애초에 "기존 걸 이해"할 필요 없이 "새 걸 하나 더 놓는" 오퍼레이션이라 페이지 전체를 JSON으로
알 필요가 없다. 그렇게 새로 붙인 블록은 우리가 그 JSON을 직접 쥐고 있으므로, 그 다음 단계
(날짜 수정)는 페이지 전체가 아니라 "그 블록 하나짜리 미니 계획"에 대한 평범한 K 패치로
표현할 수 있다.

engine.run_one()은 검증에 성공한 최종 콘텐츠(파싱된 plan, 렌더링된 html)를 호출자에게
돌려주지 않으므로(내부에서 CSV 행과 raw 파일 저장까지 전담하고 불리언 성공 여부만 반환),
체인은 그 콘텐츠를 다음 단계로 넘겨야 해서 run_one의 핵심 루프를 복제하되 성공한 콘텐츠까지
반환하는 `_run_stage()`를 둔다(html/plan/patch 세 모드 공용).

각 체인의 "성공 판정"은 CHAIN1과 동일한 관례를 따른다 — 단계마다 별도의 CSV 행
(prompt_id에 접미사)을 남기고, 앞 단계가 실패하면 뒷 단계는 실행하지 않고
"chain_blocked_by_previous_stage_failure"로 명시적으로 기록한다(조용히 건너뛰지
않는다 — docs/methodology.md §4).

Case.mode == "custom"이라 engine.py 수정 없이 동작한다.
"""

import json
import re

import engine
from engine import Case
import edit_lib
from checks import check_html, check_plan, check_patch, extract, SOFT_FAILS
from registry import REQUIRED, LLM_BLOCKS, BY_KEY, render_plan

import cases_js_plan
import cases_js_patch
import cases_js_html

V3_NUM_PREDICT = 3072
MAX_RETRY = 3
FENCE = re.compile(r"```")

CHAIN_CTA_REQUEST = "CTA 버튼 문구를 '지금 신청하기'로 바꿔줘."
EDIT_REQUEST_TEXT = "버튼 문구만 '지금 신청하기'로 바꿔줘."
EDIT_WANT_TEXT = "지금 신청하기"

CHAIN_STEPS_ADD_PATCH_REQUEST = "참여 방법(steps) 영역을 3단계로 추가해줘."
CHAIN_STEPS_ADD_WHOLE_PREFIX = ("다음 HTML에 참여 방법(steps) 영역을 3단계로 추가해줘. "
                                "나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n")

# 카운트다운 날짜 — 추가할 때 2026-08-31, 그 다음 수정 단계에서 2026-09-15로 바꾸라고
# 요청한다. "추가"만이 아니라 "추가된 걸 다시 고치는 것"까지 되는지가 이번 확장의 핵심.
INITIAL_DATE_ISO = "2026-08-31"
MODIFIED_DATE_ISO = "2026-09-15"
OLD_DATE_TOKENS = [INITIAL_DATE_ISO, "2026년 8월 31일", "8월 31일"]

CHAIN_COUNTDOWN_ADD_REQUEST_JSON = ("이벤트 마감까지 남은 시간을 보여주는 카운트다운을 추가해줘. "
                                    f"마감일은 {INITIAL_DATE_ISO}이야.")
CHAIN_COUNTDOWN_ADD_REQUEST_HTML = (
    "다음 HTML에 이벤트 종료까지 남은 시간을 보여주는 카운트다운을 넣어줘. "
    f"종료일은 {INITIAL_DATE_ISO}(YYYY-MM-DD 형식)이야." + cases_js_html.JS_RULE + "\n\n")
CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON = f"카운트다운 마감일을 {MODIFIED_DATE_ISO}로 바꿔줘."
CHAIN_COUNTDOWN_MODIFY_REQUEST_HTML = (
    f"다음 HTML에서 카운트다운 마감일을 {MODIFIED_DATE_ISO}(YYYY-MM-DD 형식 그대로 유지)로 바꿔줘. "
    "나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n")


# ══════════════════════════════════════════════════════════════
#  S(형태규칙 HTML 생성) 시스템 프롬프트 — v1/cases_ns.py의 build_system
#  (with_shape=True)와 문구가 동일해야 한다. 버전 폴더는 서로 import하지
#  않는 게 기존 관례(run.py 참고)라 이 파일 안에서 자체적으로 갖는다.
# ══════════════════════════════════════════════════════════════

def _build_shape_system() -> str:
    from registry import SERVER_BLOCKS
    lines = [
        "너는 통신사 이벤트 페이지를 만드는 도우미다.",
        "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body>, <style>, <script> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명, 인사말, 마무리 멘트를 붙이지 마라.",
        "",
        "만들 영역:",
    ]
    for b in LLM_BLOCKS:
        tail = "" if b.required else "  (선택)"
        line = f'- data-block="{b.key}" : {b.desc}{tail}'
        if b.shape:
            line += f"\n    형태: {b.shape}"
        lines.append(line)
    if SERVER_BLOCKS:
        lines += ["", "만들면 안 되는 영역:"]
        for b in SERVER_BLOCKS:
            lines.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')
    lines += [
        "", "태그를 반드시 쓴다. 맨 텍스트만 두지 마라.",
        "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 절대 남기지 마라.",
        "- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


SYSTEM_SHAPE = _build_shape_system()
SYSTEM_WHOLE_EDIT = ("너는 기존 이벤트 HTML을 수정하는 도우미다. "
                     "요청한 변경만 하고 나머지 텍스트, 태그, 속성, 영역 순서는 그대로 유지한다. "
                     "입력의 section 조각 전체만 출력한다. 설명, 코드펜스, html/head/body는 출력하지 않는다.")
GEN_P1_HTML = cases_js_plan.GEN_P1  # J와 글자 그대로 동일한 요청 문구 — S/J 비교 가능하게 유지


# ══════════════════════════════════════════════════════════════
#  content 필드까지 포함하는 확장 패치 스키마 — set_theme/apply_preset까지
#  포함해 cases_js_patch보다 한 단계 더 넓다(CHAIN4가 steps add_block에,
#  CHAIN2/5/6의 날짜 수정 단계가 set_field에 이 스키마를 함께 쓴다).
# ══════════════════════════════════════════════════════════════

def _build_full_patch_schema() -> dict:
    block_keys = [b.key for b in LLM_BLOCKS]
    theme_fields = ["primaryColor", "buttonColor", "fontFamily", "headlineWeight"]
    preset_names = ["vivid", "cool", "minimal", "warm"]

    add_block_variants = []
    for b in LLM_BLOCKS:
        for v in b.variants:
            props = {"op": {"const": "add_block"}, "type": {"const": b.key},
                      "variant": {"const": v.name}}
            required = ["op", "type", "variant"]
            for f in v.fields:
                if f == "items":
                    props["items"] = {"type": "array",
                                       "items": {"type": "string", "minLength": 1},
                                       "minItems": max(b.min_items, 1)}
                    required.append("items")
                elif f == "sub":
                    props["sub"] = {"type": "string"}
                else:
                    props[f] = {"type": "string", "minLength": 1}
                    required.append(f)
            add_block_variants.append({"type": "object", "properties": props,
                                        "required": required, "additionalProperties": False})

    op_variants = [
        {"type": "object", "properties": {
            "op": {"const": "set_field"}, "block_key": {"type": "string", "enum": block_keys},
            "field": {"type": "string"}, "value": {"type": "string"},
        }, "required": ["op", "block_key", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "append_item"}, "block_key": {"type": "string", "enum": block_keys},
            "value": {"type": "string"},
        }, "required": ["op", "block_key", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "remove_block"}, "block_key": {"type": "string", "enum": block_keys},
        }, "required": ["op", "block_key"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "set_theme"}, "field": {"type": "string", "enum": theme_fields},
            "value": {"type": "string"},
        }, "required": ["op", "field", "value"], "additionalProperties": False},
        {"type": "object", "properties": {
            "op": {"const": "apply_preset"}, "name": {"type": "string", "enum": preset_names},
        }, "required": ["op", "name"], "additionalProperties": False},
    ] + add_block_variants

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


FULL_PATCH_SCHEMA = _build_full_patch_schema()


def _patch_system_full(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성을 수정하는 도우미다.

[현재 계획]
{plan_json}

전체 계획을 다시 쓰지 마라. 요청과 관련된 부분만 오퍼레이션으로 표현하라.

사용 가능한 오퍼레이션:
- set_field: {{"op":"set_field","block_key":"cta","field":"label","value":"..."}}
- append_item: {{"op":"append_item","block_key":"benefits","value":"..."}}
- remove_block: {{"op":"remove_block","block_key":"steps"}}
- set_theme: {{"op":"set_theme","field":"buttonColor","value":"#2f9e44"}}
- add_block(예 — steps): {{"op":"add_block","type":"steps","variant":"hyperui_numbered",
  "items":["1단계 내용","2단계 내용"]}}
- add_block(예 — 카운트다운): {{"op":"add_block","type":"countdown","variant":"digital",
  "title":"...","target_date":"YYYY-MM-DD"}}

출력 형식: {{"ops":[ ...오퍼레이션들... ]}}

규칙:
- 언급되지 않은 블록/필드는 오퍼레이션에 아예 포함하지 마라.
- 최소한의 오퍼레이션으로 요청을 처리하라.
- notices 블록은 서버 전용이므로 절대 건드리지 마라.
- 색상은 #으로 시작하는 6자리 16진수로 표현하라.
- countdown의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- JSON 외에는 아무것도 출력하지 마라."""


def check_block_text_edit(baseline_block_html: str, edited_html: str, key: str, want_text: str) -> list:
    """v1 cases_e.py의 check_cta_text_edit을 edit_lib 기반으로 일반화한
    버전 — CHAIN3/5/6처럼 '이번 실행에서 실제로 생성된' 블록을 baseline으로
    삼아야 하는 경우를 위해 baseline을 인자로 받는다."""
    fails = []
    a = edit_lib.safe_soup(baseline_block_html)
    b = edit_lib.safe_soup(edited_html)
    aa = a.select_one(f'[data-block="{key}"]')
    bb = b.select_one(f'[data-block="{key}"]')
    if bb is None:
        return ["edit_target_missing"]
    if not edit_lib.outside_preserved(baseline_block_html, edited_html, key):
        fails.append("diff_unintended")

    old_a, new_a = (aa.find("a") if aa else None), bb.find("a")
    if new_a is None or new_a.get_text(strip=True) != want_text:
        fails.append("request_not_applied")
    if old_a is not None and new_a is not None:
        old_copy, new_copy = edit_lib.safe_soup(str(aa)), edit_lib.safe_soup(str(bb))
        oa, na = old_copy.find("a"), new_copy.find("a")
        if oa and na:
            oa.clear(); oa.append("__EDIT_TEXT__")
            na.clear(); na.append("__EDIT_TEXT__")
            if edit_lib.canonical(old_copy) != edit_lib.canonical(new_copy):
                fails.append("diff_unintended")
    return list(dict.fromkeys(fails))


def check_date_updated(text_or_raw: str, _unused=None) -> list:
    """자유형식 HTML(JS-HTML 노선)에서 '날짜가 실제로 바뀌었는지'를 보는
    최소한의 텍스트 검사 — 구조를 몰라도(스크립트 안에 박혀있어도) 새
    날짜 문자열이 나타나고 옛 날짜 문자열이 사라졌는지만 본다."""
    fails = []
    if MODIFIED_DATE_ISO not in text_or_raw:
        fails.append("date_not_updated")
    if any(tok in text_or_raw for tok in OLD_DATE_TOKENS):
        fails.append("old_date_still_present")
    return fails


def _parse_patch_ops(raw):
    text = FENCE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s:e + 1]).get("ops", [])
    except Exception:
        return None


def check_countdown_setfield_date(raw, _):
    """K로 '카운트다운 날짜를 바꿔달라'고 했을 때, 실제로
    set_field(block_key=countdown, field=target_date, value=새 날짜)를
    냈는지 확인한다. add_block으로 카운트다운을 통째로 새로 내거나
    엉뚱한 필드를 건드리면 잡아낸다."""
    ops = _parse_patch_ops(raw) or []
    for op in ops:
        if not isinstance(op, dict):
            continue
        if (op.get("op") == "set_field" and op.get("block_key") == "countdown"
                and op.get("field") == "target_date"):
            return [] if op.get("value") == MODIFIED_DATE_ISO else ["countdown_date_not_updated"]
    return ["countdown_setfield_missing"]


# ══════════════════════════════════════════════════════════════
#  단일 단계 실행 — engine.run_one()과 동일한 계약이지만, 다음 단계로
#  넘길 실제 콘텐츠(html 문자열 또는 파싱된 plan dict)까지 반환한다.
# ══════════════════════════════════════════════════════════════

def _run_stage(model, runner, digest, backend, repeat_no, seed, rows, out_dir,
               pid, kind, pair, system, prompt, mode, keep=(), forbid=(),
               extra_check=None, json_schema=None, num_predict=None,
               current_plan=None, allow_script=False, max_retry=MAX_RETRY):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    first_hard_ok = None

    for attempt in range(1, max_retry + 1):
        try:
            res = engine.call(model, messages, mode=mode,
                               as_json=(mode in ("plan", "patch")), seed=seed,
                               json_schema=json_schema, num_predict_override=num_predict)
        except Exception:
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error"))
            return None, first_hard_ok or 0, 0

        raw = res["message"]["content"]
        rendered = None
        candidate = None

        if mode == "plan":
            fails, note, plan, rendered = check_plan(raw, keep, forbid)
            out_len, html_len = len(raw.strip()), len(rendered)
            candidate = plan
        elif mode == "patch":
            fails, note, merged, rendered = check_patch(raw, current_plan, keep, forbid)
            out_len, html_len = len(raw.strip()), len(rendered)
            candidate = merged
        else:  # html
            html = extract(raw)
            fails, note = check_html(raw, html, keep, forbid, True, allow_script=allow_script)
            out_len = html_len = len(html)
            candidate = html

        if extra_check is not None:
            fails += extra_check(raw, raw if mode != "html" else candidate)

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
            group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
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
            return candidate, first_hard_ok, 1

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                          "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

    return None, first_hard_ok or 0, 0


def _run_add_single_block_stage(model, runner, digest, backend, repeat_no, seed, rows, out_dir,
                                 pid, kind, pair, current_html, block_key, block_request,
                                 extra_check=None, num_predict=V3_NUM_PREDICT, max_retry=MAX_RETRY):
    """S/E처럼 페이지가 HTML로만 존재할 때 JSON 블록 하나를 '추가'만
    하는 전용 단계. 모듈 docstring의 "CHAIN6이 실제로 막혔던 지점" 참고
    — 기존 페이지를 JSON으로 되돌리는 파서 없이도, 새로 추가하는 블록
    하나만 JSON으로 받아 registry로 렌더링한 뒤 기존 HTML에 이어붙이면
    되므로 동작한다. 반환값은 (병합된 전체 HTML, 그 블록의 JSON, first_ok, final_ok).
    """
    b = BY_KEY[block_key]
    variants = []
    for v in b.variants:
        props = {"type": {"const": b.key}, "variant": {"const": v.name}}
        required = ["type", "variant"]
        for f in v.fields:
            if f == "items":
                props["items"] = {"type": "array", "items": {"type": "string", "minLength": 1},
                                   "minItems": max(b.min_items, 1)}
                required.append("items")
            elif f == "sub":
                props["sub"] = {"type": "string"}
            else:
                props[f] = {"type": "string", "minLength": 1}
                required.append(f)
        variants.append({"type": "object", "properties": props,
                          "required": required, "additionalProperties": False})
    schema = variants[0] if len(variants) == 1 else {"oneOf": variants}

    menu = "\n".join(
        f'- type="{block_key}" variant="{v.name}" — {v.desc}, 필요한 값: {", ".join(v.fields)}'
        for v in b.variants)
    system = f"""너는 이미 만들어진 이벤트 페이지에 새 영역 하나를 추가하는 도우미다.

[현재 페이지 — 참고만 하고 다시 출력하지 마라]
{current_html}

추가할 수 있는 블록:
{menu}

새로 추가할 영역 하나만 JSON으로 출력한다.

규칙:
- countdown의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- faq/tabs의 items는 각 항목을 "앞부분|뒷부분" 형식(파이프 1개)으로 쓴다.
- JSON 외에는 아무것도 출력하지 마라."""

    messages = [{"role": "system", "content": system}, {"role": "user", "content": block_request}]
    first_hard_ok = None

    for attempt in range(1, max_retry + 1):
        try:
            res = engine.call(model, messages, mode="plan", as_json=True, seed=seed,
                               json_schema=schema, num_predict_override=num_predict)
        except Exception:
            rows.append(engine._empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error"))
            return None, None, first_hard_ok or 0, 0

        raw = res["message"]["content"]
        fails, note = [], ""
        merged_html, block_item = None, None
        text = FENCE.sub("", raw).strip()
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e == -1:
            fails, note = ["no_json"], "JSON을 찾을 수 없습니다."
        else:
            try:
                block_item = json.loads(text[s:e + 1])
            except Exception as ex:
                fails, note = ["bad_json"], f"JSON 파싱 실패: {ex}"

        if block_item is not None:
            if block_item.get("type") != block_key:
                fails.append("wrong_block_type")
                note = f'{block_key} 대신 "{block_item.get("type")}"를 냈습니다.'
            else:
                rendered_block = render_plan({"blocks": [block_item]})
                if not rendered_block:
                    fails.append("empty_render")
                    note = "필드가 비어 렌더링되지 않았습니다."
                else:
                    merged_html = edit_lib.replace_block(current_html, block_key, rendered_block)
                    hf, hn = check_html(merged_html, merged_html,
                                         list(REQUIRED) + [block_key], ["notices"], True)
                    fails += hf
                    if hn:
                        note = (note + " " + hn).strip()

        if extra_check is not None and block_item is not None:
            fails += extra_check(raw, raw)

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
            group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
            repeat_no=repeat_no, seed=seed, attempt=attempt,
            hard_ok=hard_ok, all_ok=int(not fails),
            fails="|".join(hard), soft_fails="|".join(soft),
            wall_sec=res["_wall_sec"],
            load_ms=res.get("load_duration", 0) // 1_000_000,
            prompt_ms=pd // 1_000_000, eval_ms=ed // 1_000_000,
            prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
            prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
            eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
            out_len=len(raw.strip()), html_len=len(merged_html) if merged_html else 0,
            done_reason=res.get("done_reason", "")))

        safe = model.replace(":", "_")
        base = f"{out_dir}/{safe}_{pid}_r{repeat_no}_s{seed}_try{attempt}"
        with open(f"{base}.txt", "w", encoding="utf-8") as f:
            f.write(raw)
        if merged_html:
            with open(f"{base}.rendered.html", "w", encoding="utf-8") as f:
                f.write(merged_html)

        if hard_ok:
            return merged_html, block_item, first_hard_ok, 1

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                          "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

    return None, None, first_hard_ok or 0, 0


def _blocked_row(runner, model, digest, backend, repeat_no, seed, pid, kind, pair, rows):
    rows.append(engine._empty_row(
        runner=runner, model=model, digest=digest, backend=backend,
        group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
        repeat_no=repeat_no, seed=seed, attempt=1,
        hard_ok=0, all_ok=0, fails="chain_blocked_by_previous_stage_failure"))


# ══════════════════════════════════════════════════════════════
#  CHAIN2 — J 생성 → K 패치(문구) → JS-PATCH(카운트다운 add_block) → K로 날짜 수정
#           순수 JSON 노선 4단계
# ══════════════════════════════════════════════════════════════

def custom_run_chain2(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    plan, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN2_GEN", kind="1_생성_J", pair=case.pid,
        system=cases_js_plan.GEN_SYSTEM, prompt=cases_js_plan.GEN_P1, mode="plan",
        keep=list(REQUIRED), forbid=["notices"],
        json_schema=cases_js_plan.PLAN_SCHEMA, num_predict=V3_NUM_PREDICT)
    if plan is None:
        for pid, kind in [("CHAIN2_PATCH", "2_수정_K"), ("CHAIN2_JSADD", "3_JS추가"),
                           ("CHAIN2_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    patched, patch_first, patch_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN2_PATCH", kind="2_수정_K_문구", pair=case.pid,
        system=_patch_system_full(plan), prompt=CHAIN_CTA_REQUEST, mode="patch",
        keep=list(REQUIRED), forbid=["notices"], current_plan=plan,
        json_schema=FULL_PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)
    if patched is None:
        for pid, kind in [("CHAIN2_JSADD", "3_JS추가"), ("CHAIN2_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    with_cd, jsadd_first, jsadd_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN2_JSADD", kind="3_JS추가_카운트다운", pair=case.pid,
        system=_patch_system_full(patched), prompt=CHAIN_COUNTDOWN_ADD_REQUEST_JSON, mode="patch",
        keep=list(REQUIRED) + ["countdown"], forbid=["notices"], current_plan=patched,
        extra_check=cases_js_patch.check_countdown_patch_format,
        json_schema=FULL_PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)
    if with_cd is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN2_JSMOD", "4_JS수정_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and patch_first) else 0), 0

    _, jsmod_first, jsmod_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN2_JSMOD", kind="4_JS수정_카운트다운날짜", pair=case.pid,
        system=_patch_system_full(with_cd), prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON, mode="patch",
        keep=list(REQUIRED) + ["countdown"], forbid=["notices"], current_plan=with_cd,
        extra_check=check_countdown_setfield_date,
        json_schema=FULL_PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)

    chain_first = 1 if (gen_first and patch_first and jsadd_first and jsmod_first) else 0
    chain_final = 1 if (gen_final and patch_final and jsadd_final and jsmod_final) else 0
    return chain_first, chain_final


# ══════════════════════════════════════════════════════════════
#  CHAIN3 — S 생성 → E 블록왕복(문구) → JS-HTML(카운트다운 직접작성)
#           → 전체재작성으로 날짜 수정. 순수 HTML 노선 4단계
# ══════════════════════════════════════════════════════════════

def custom_run_chain3(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    doc, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN3_GEN", kind="1_생성_S", pair=case.pid,
        system=SYSTEM_SHAPE, prompt=GEN_P1_HTML, mode="html",
        keep=list(REQUIRED), forbid=["notices"])
    if doc is None:
        for pid, kind in [("CHAIN3_EDIT", "2_수정_E"), ("CHAIN3_JSADD", "3_JS추가"),
                           ("CHAIN3_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    cta_before = edit_lib.block_of(doc, "cta")
    edited_cta, edit_first, edit_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN3_EDIT", kind="2_수정_E_문구", pair=case.pid,
        system=edit_lib.build_block_edit_system("cta"),
        prompt=f"이 영역의 {EDIT_REQUEST_TEXT}\n\n{cta_before}", mode="html",
        keep=["cta"], forbid=[k for k in REQUIRED if k != "cta"],
        extra_check=lambda raw, html: check_block_text_edit(cta_before, html, "cta", EDIT_WANT_TEXT))
    if edited_cta is None:
        for pid, kind in [("CHAIN3_JSADD", "3_JS추가"), ("CHAIN3_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    merged_doc = edit_lib.replace_block(doc, "cta", edited_cta)

    with_cd, jsadd_first, jsadd_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN3_JSADD", kind="3_JS추가_카운트다운", pair=case.pid,
        system=cases_js_html.SYSTEM_JS,
        prompt=CHAIN_COUNTDOWN_ADD_REQUEST_HTML + merged_doc, mode="html",
        keep=list(REQUIRED), forbid=["notices"], allow_script=True,
        extra_check=cases_js_html.check_js_structure, num_predict=V3_NUM_PREDICT)
    if with_cd is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN3_JSMOD", "4_JS수정_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and edit_first) else 0), 0

    _, jsmod_first, jsmod_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN3_JSMOD", kind="4_JS수정_카운트다운날짜", pair=case.pid,
        system=SYSTEM_WHOLE_EDIT, allow_script=True,
        prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_HTML + with_cd, mode="html",
        keep=list(REQUIRED), forbid=["notices"],
        extra_check=lambda raw, html: check_date_updated(html) + cases_js_html.check_js_structure(raw, html),
        num_predict=V3_NUM_PREDICT)

    chain_first = 1 if (gen_first and edit_first and jsadd_first and jsmod_first) else 0
    chain_final = 1 if (gen_final and edit_final and jsadd_final and jsmod_final) else 0
    return chain_first, chain_final


# ══════════════════════════════════════════════════════════════
#  CHAIN4 — J 생성 → K로 구조 수정(steps 추가) 시도 → 실패하면 E로 재시도
# ══════════════════════════════════════════════════════════════

def custom_run_chain4(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    plan, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN4_GEN", kind="1_생성_J", pair=case.pid,
        system=cases_js_plan.GEN_SYSTEM, prompt=cases_js_plan.GEN_P1, mode="plan",
        keep=list(REQUIRED), forbid=["notices"],
        json_schema=cases_js_plan.PLAN_SCHEMA, num_predict=V3_NUM_PREDICT)
    if plan is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN4_K", "2_수정시도_K_생성실패로_스킵", case.pid, rows)
        return 0, 0

    _, k_first, k_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN4_K", kind="2_수정시도_K_steps추가", pair=case.pid,
        system=_patch_system_full(plan), prompt=CHAIN_STEPS_ADD_PATCH_REQUEST, mode="patch",
        keep=list(REQUIRED) + ["steps"], forbid=["notices"], current_plan=plan,
        json_schema=FULL_PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)

    if k_final:
        # K가 됐으면 E 우회는 필요 없다 — "K가 못 할 때만 E로 구제"가 이 체인의 핵심이므로
        # 여기서는 E 행을 아예 만들지 않는다(성공한 것처럼 꾸민 가짜 행을 남기지 않기 위해).
        # 이 회차의 CHAIN 행 수가 K 성공 여부에 따라 2개(GEN+K) 또는 3개(GEN+K+E)로
        # 달라지는 건 의도된 것이다 — E는 K가 실패했을 때만 실제로 스트레스 테스트된다.
        return (1 if gen_first and k_first else 0), 1

    baseline_html = render_plan(plan)
    _, e_first, e_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN4_E", kind="3_우회_E_steps추가", pair=case.pid,
        system=SYSTEM_WHOLE_EDIT,
        prompt=CHAIN_STEPS_ADD_WHOLE_PREFIX + baseline_html, mode="html",
        keep=list(REQUIRED) + ["steps"], forbid=["notices"])

    chain_first = 1 if (gen_first and (k_first or e_first)) else 0
    chain_final = 1 if (gen_final and (k_final or e_final)) else 0
    return chain_first, chain_final


# ══════════════════════════════════════════════════════════════
#  CHAIN5 — J 생성 → K 패치(문구) → JS-HTML(카운트다운 직접작성) → 날짜 수정
#           JSON 생성/수정 + HTML 인터랙션 (교차 조합)
# ══════════════════════════════════════════════════════════════

def custom_run_chain5(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    plan, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN5_GEN", kind="1_생성_J", pair=case.pid,
        system=cases_js_plan.GEN_SYSTEM, prompt=cases_js_plan.GEN_P1, mode="plan",
        keep=list(REQUIRED), forbid=["notices"],
        json_schema=cases_js_plan.PLAN_SCHEMA, num_predict=V3_NUM_PREDICT)
    if plan is None:
        for pid, kind in [("CHAIN5_PATCH", "2_수정_K"), ("CHAIN5_JSADD", "3_JS추가"),
                           ("CHAIN5_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    patched, patch_first, patch_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN5_PATCH", kind="2_수정_K_문구", pair=case.pid,
        system=_patch_system_full(plan), prompt=CHAIN_CTA_REQUEST, mode="patch",
        keep=list(REQUIRED), forbid=["notices"], current_plan=plan,
        json_schema=FULL_PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)
    if patched is None:
        for pid, kind in [("CHAIN5_JSADD", "3_JS추가"), ("CHAIN5_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    baseline_html = render_plan(patched)
    with_cd, jsadd_first, jsadd_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN5_JSADD", kind="3_JS추가_카운트다운_HTML", pair=case.pid,
        system=cases_js_html.SYSTEM_JS,
        prompt=CHAIN_COUNTDOWN_ADD_REQUEST_HTML + baseline_html, mode="html",
        keep=list(REQUIRED), forbid=["notices"], allow_script=True,
        extra_check=cases_js_html.check_js_structure, num_predict=V3_NUM_PREDICT)
    if with_cd is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN5_JSMOD", "4_JS수정_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and patch_first) else 0), 0

    _, jsmod_first, jsmod_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN5_JSMOD", kind="4_JS수정_카운트다운날짜", pair=case.pid,
        system=SYSTEM_WHOLE_EDIT, allow_script=True,
        prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_HTML + with_cd, mode="html",
        keep=list(REQUIRED), forbid=["notices"],
        extra_check=lambda raw, html: check_date_updated(html) + cases_js_html.check_js_structure(raw, html),
        num_predict=V3_NUM_PREDICT)

    chain_first = 1 if (gen_first and patch_first and jsadd_first and jsmod_first) else 0
    chain_final = 1 if (gen_final and patch_final and jsadd_final and jsmod_final) else 0
    return chain_first, chain_final


# ══════════════════════════════════════════════════════════════
#  CHAIN6 — S 생성 → E 블록왕복(문구) → 카운트다운을 JSON 블록으로 "추가"
#           → 그 블록만 K로 날짜 수정. HTML 생성/수정 + JSON 인터랙션 (교차 조합)
# ══════════════════════════════════════════════════════════════

def custom_run_chain6(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    doc, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN6_GEN", kind="1_생성_S", pair=case.pid,
        system=SYSTEM_SHAPE, prompt=GEN_P1_HTML, mode="html",
        keep=list(REQUIRED), forbid=["notices"])
    if doc is None:
        for pid, kind in [("CHAIN6_EDIT", "2_수정_E"), ("CHAIN6_JSADD", "3_JS추가"),
                           ("CHAIN6_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    cta_before = edit_lib.block_of(doc, "cta")
    edited_cta, edit_first, edit_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN6_EDIT", kind="2_수정_E_문구", pair=case.pid,
        system=edit_lib.build_block_edit_system("cta"),
        prompt=f"이 영역의 {EDIT_REQUEST_TEXT}\n\n{cta_before}", mode="html",
        keep=["cta"], forbid=[k for k in REQUIRED if k != "cta"],
        extra_check=lambda raw, html: check_block_text_edit(cta_before, html, "cta", EDIT_WANT_TEXT))
    if edited_cta is None:
        for pid, kind in [("CHAIN6_JSADD", "3_JS추가"), ("CHAIN6_JSMOD", "4_JS수정")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    merged_doc = edit_lib.replace_block(doc, "cta", edited_cta)

    with_cd, countdown_block, jsadd_first, jsadd_final = _run_add_single_block_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN6_JSADD", kind="3_JS추가_카운트다운_JSON", pair=case.pid,
        current_html=merged_doc, block_key="countdown",
        block_request=CHAIN_COUNTDOWN_ADD_REQUEST_JSON,
        extra_check=cases_js_plan.check_countdown_value_format, num_predict=V3_NUM_PREDICT)
    if with_cd is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN6_JSMOD", "4_JS수정_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and edit_first) else 0), 0

    # 우리가 방금 추가한 블록의 JSON을 그대로 쥐고 있으므로, 페이지 전체가
    # 아니라 "그 블록 하나짜리 미니 계획"에 대한 평범한 K 패치로 수정한다
    # (모듈 docstring 참고 — 이게 S→E→JSON인터랙션 조합이 막히지 않는 이유).
    mini_plan = {"blocks": [countdown_block], "theme": {}}
    updated_mini, jsmod_first, jsmod_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN6_JSMOD", kind="4_JS수정_카운트다운날짜_K", pair=case.pid,
        system=cases_js_patch._patch_system(mini_plan), prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON,
        mode="patch", keep=["countdown"], forbid=[], current_plan=mini_plan,
        extra_check=check_countdown_setfield_date,
        json_schema=cases_js_patch.PATCH_SCHEMA, num_predict=V3_NUM_PREDICT)

    if updated_mini is not None:
        # 최종 문서까지 병합해서 raw로 남긴다(체크 자체는 위 _run_stage가 이미 끝냄).
        updated_fragment = render_plan(updated_mini)
        final_doc = edit_lib.replace_block(with_cd, "countdown", updated_fragment)
        safe = model.replace(":", "_")
        with open(f"{out_dir}/{safe}_CHAIN6_FINAL_r{repeat_no}_s{seed}.rendered.html",
                  "w", encoding="utf-8") as f:
            f.write(final_doc)

    chain_first = 1 if (gen_first and edit_first and jsadd_first and jsmod_first) else 0
    chain_final = 1 if (gen_final and edit_final and jsadd_final and jsmod_final) else 0
    return chain_first, chain_final


CASES = [
    Case("CHAIN2", "JSON노선_4단계_생성수정추가수정", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain2),
    Case("CHAIN3", "HTML노선_4단계_생성수정추가수정", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain3),
    Case("CHAIN4", "K실패시_E로_구제", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain4),
    Case("CHAIN5", "JSON생성수정_HTML인터랙션_교차", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain5),
    Case("CHAIN6", "HTML생성수정_JSON인터랙션_교차", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain6),
]


def self_check():
    assert callable(cases_js_plan.build_plan_system)
    assert isinstance(cases_js_plan.GEN_P1, str) and cases_js_plan.GEN_P1

    assert FULL_PATCH_SCHEMA["type"] == "object"
    variants = FULL_PATCH_SCHEMA["properties"]["ops"]["items"]["oneOf"]
    assert any(v["properties"].get("op", {}).get("const") == "set_theme" for v in variants)
    countdown_variants = [v for v in variants
                          if v["properties"].get("type", {}).get("const") == "countdown"]
    assert countdown_variants and "target_date" in countdown_variants[0]["properties"]

    for b in LLM_BLOCKS:
        assert b.shape in SYSTEM_SHAPE

    demo_plan = {"blocks": [
        {"type": "hero", "variant": "hyperui_centered", "title": "제목", "sub": "소개"},
        {"type": "benefits", "variant": "hyperui_list", "items": ["a", "b"]},
        {"type": "cta", "variant": "hyperui_simple", "label": "가입하기"},
    ], "theme": {}}
    system = _patch_system_full(demo_plan)
    assert "가입하기" in system, "_patch_system_full이 실제 계획 내용을 프롬프트에 못 넣음"

    # check_block_text_edit 회귀 — v1 check_cta_text_edit과 동일한 시나리오
    baseline = '<section data-block="cta"><a href="#" class="btn">가입하기</a></section>'
    good = baseline.replace("가입하기", "지금 신청하기")
    assert not check_block_text_edit(baseline, good, "cta", "지금 신청하기")
    assert "request_not_applied" in check_block_text_edit(baseline, baseline, "cta", "지금 신청하기")
    wrong_href = good.replace('href="#"', 'href="https://wrong.example"')
    assert "diff_unintended" in check_block_text_edit(baseline, wrong_href, "cta", "지금 신청하기")

    # check_date_updated 회귀
    assert check_date_updated(f"...target={MODIFIED_DATE_ISO}...") == []
    assert "date_not_updated" in check_date_updated("아무 날짜도 없음")
    assert "old_date_still_present" in check_date_updated(
        f"{MODIFIED_DATE_ISO} 인데 {INITIAL_DATE_ISO}도 같이 남음")

    # check_countdown_setfield_date 회귀
    good_op = json.dumps({"ops": [
        {"op": "set_field", "block_key": "countdown", "field": "target_date",
         "value": MODIFIED_DATE_ISO},
    ]}, ensure_ascii=False)
    assert check_countdown_setfield_date(good_op, "") == []
    wrong_value_op = json.dumps({"ops": [
        {"op": "set_field", "block_key": "countdown", "field": "target_date", "value": "2099-01-01"},
    ]}, ensure_ascii=False)
    assert "countdown_date_not_updated" in check_countdown_setfield_date(wrong_value_op, "")
    no_op = json.dumps({"ops": [
        {"op": "add_block", "type": "countdown", "variant": "digital",
         "title": "x", "target_date": MODIFIED_DATE_ISO},
    ]}, ensure_ascii=False)
    assert "countdown_setfield_missing" in check_countdown_setfield_date(no_op, "")

    assert len(CASES) == 5
    for c in CASES:
        assert c.group == "CHAIN"
        assert c.mode == "custom"
        assert c.custom_run is not None

    # 이 파일이 옛 CHAIN5/6(E×5/K×5 누적)를 정말로 없앴는지 — 남아있으면 회귀.
    import sys
    module = sys.modules[__name__]
    assert not hasattr(module, "CHAIN_STEPS"), "옛 CHAIN5(E×5)의 CHAIN_STEPS가 아직 남아있음"
    assert not hasattr(module, "K5_STEPS"), "옛 CHAIN6(K×5)의 K5_STEPS가 아직 남아있음"
