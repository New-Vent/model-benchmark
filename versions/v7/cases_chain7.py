"""
cases_chain7.py — CHAIN7: 확정된 조합(생성→수정→JS-PLAN추가→값수정)을
실제 템플릿 스케일로 잇는다. 두 노선(CHAIN7-J/CHAIN7-S) × 값수정
변형(-E/-K)으로 versions/v7/README.md §2·§3이 설계한 것을 그대로 구현한다.

이 파일이 v3/cases_chain.py와 겹치는 부분(_run_stage 실행 골격, 편집
문구 상수)은 의도적으로 복붙이다 — run.py는 버전 폴더 하나만 sys.path에
넣으므로 cases_chain.py를 직접 import할 수 없고(README §0 참고), 프롬프트
문구도 버전마다 독립으로 보존하는 게 기존 관례다(run.py 상단 docstring,
v1 cases_ns.py ↔ v3 SYSTEM_SHAPE 선례). 생성 시스템 프롬프트(SYSTEM_JT7/
SYSTEM_ST7)는 versions/v5/cases_jt.py·cases_st.py의 SYSTEM과 글자 그대로
같아야 한다 — 어긋나면 v5와 v7이 "다른 생성 방식"을 비교하게 된다.

이 파일이 지켜야 할 규약(engine.py와의 계약):
  - CASES: list[Case]
  - self_check(): 선택
"""

import json
import re

import engine
from engine import Case
import edit_lib
from checks import check_html, check_plan, check_patch, extract, SOFT_FAILS
from registry import REQUIRED, render_plan, build_plan_json_schema, build_patch_json_schema

GROUPS = ["CHAIN"]

FENCE = re.compile(r"```")
MAX_RETRY = 3

# v5(cases_st.py/cases_jt.py) 캡 그대로 — 1단계는 4블록만 요청하므로 동일.
CHAIN7_NUM_PREDICT_GEN = 3072
# 3·4단계는 5블록(+countdown) 전체를 다시 내야 해서 더 큰 캡이 필요할 수
# 있다 — 실측 근거 없는 잠정치다(README §4 "위험 요소" 참고).
CHAIN7_NUM_PREDICT_STAGE34 = 3584

EDIT_REQUEST_TEXT = "버튼 문구만 '지금 신청하기'로 바꿔줘."
EDIT_WANT_TEXT = "지금 신청하기"

INITIAL_DATE_ISO = "2026-08-31"
MODIFIED_DATE_ISO = "2026-09-15"
OLD_DATE_TOKENS = [INITIAL_DATE_ISO, "2026년 8월 31일", "8월 31일"]
COUNTDOWN_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CHAIN7_COUNTDOWN_ADD_REQUEST = ("이벤트 마감까지 남은 시간을 보여주는 카운트다운을 추가해줘. "
                                f"마감일은 {INITIAL_DATE_ISO}야.")
CHAIN_COUNTDOWN_MODIFY_REQUEST_HTML = (
    f"다음 HTML에서 카운트다운 마감일을 {MODIFIED_DATE_ISO}(YYYY-MM-DD 형식 그대로 유지)로 바꿔줘. "
    "나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n")
CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON = f"카운트다운 마감일을 {MODIFIED_DATE_ISO}로 바꿔줘."

SYSTEM_WHOLE_EDIT = ("너는 기존 이벤트 HTML을 수정하는 도우미다. "
                     "요청한 변경만 하고 나머지 텍스트, 태그, 속성, 영역 순서는 그대로 유지한다. "
                     "입력의 section 조각 전체만 출력한다. 설명, 코드펜스, html/head/body는 출력하지 않는다.")

PLAN_SCHEMA_BASE = build_plan_json_schema()
PATCH_SCHEMA_BASE = build_patch_json_schema()

# 신규 생성 요청 문구 — v5 ST1/JT1과 글자 그대로 같아야 pair 비교가 유지된다.
CHAIN7_GEN_PROMPT = ("2026년 프로야구 시즌 응원 이벤트 페이지를 만들어줘. "
                     "혜택 3개(굿즈, 할인, 포인트 적립), 참여 방법 3단계를 포함해줘.")

# ══════════════════════════════════════════════════════════════
#  1단계 생성 시스템 프롬프트 — v5 cases_jt.py / cases_st.py의 SYSTEM과
#  동일해야 한다(모듈 docstring 참고).
# ══════════════════════════════════════════════════════════════

SYSTEM_JT7 = """너는 통신사 이벤트 페이지의 구성 계획(JSON)을 만드는 도우미다.

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
- 주어지지 않은 혜택을 지어내지 마라.
- JSON 외에는 아무것도 출력하지 마라."""

_ST7_BLOCK_CLASS_HINT = {
    "hero": "ev-block block-hero",
    "benefits": "ev-block block-benefits",
    "steps": "ev-block block-steps",
    "cta": "ev-block block-cta",
}


def _build_system_st7() -> str:
    lines = [
        "너는 통신사 이벤트 페이지를 처음부터 만드는 도우미다.",
        "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름" class="..."> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body>, <style>, <script> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라. 설명·인사말·마무리 멘트를 붙이지 마라.",
        "",
        "반드시 만들 영역과 class (디자인이 여기 걸려 있으니 정확히 써라):",
        f'- data-block="hero" class="{_ST7_BLOCK_CLASS_HINT["hero"]}" — 제목 <h1>, 소개 <p>',
        f'- data-block="benefits" class="{_ST7_BLOCK_CLASS_HINT["benefits"]}" — <ul><li> 로 혜택 3개',
        f'- data-block="steps" class="{_ST7_BLOCK_CLASS_HINT["steps"]}" — <ol><li> 로 참여 단계 3개',
        f'- data-block="cta" class="{_ST7_BLOCK_CLASS_HINT["cta"]}" — <a href="#" class="btn"> 버튼 하나',
        "",
        '만들면 안 되는 영역:',
        '- data-block="notices" 는 절대 만들지 마라. 서버가 관리한다.',
        "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택을 만들어내지 마라.",
        "- 대괄호 자리표시자를 절대 남기지 마라.",
        "- style=\"...\" 를 넣지 마라. theme- 로 시작하는 클래스를 넣지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


SYSTEM_ST7 = _build_system_st7()


# ══════════════════════════════════════════════════════════════
#  단일 단계 실행 — v3/cases_chain.py의 _run_stage와 동일한 계약
#  (모듈 docstring 참고 — cross-version import가 안 되어 복붙이다).
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


def _blocked_row(runner, model, digest, backend, repeat_no, seed, pid, kind, pair, rows):
    rows.append(engine._empty_row(
        runner=runner, model=model, digest=digest, backend=backend,
        group="CHAIN", prompt_id=pid, kind=kind, pair=pair,
        repeat_no=repeat_no, seed=seed, attempt=1,
        hard_ok=0, all_ok=0, fails="chain_blocked_by_previous_stage_failure"))


# ══════════════════════════════════════════════════════════════
#  2·3단계 공용 헬퍼 — 편집 검증, plan 파싱, 내용보존 검사
# ══════════════════════════════════════════════════════════════

def check_block_text_edit(baseline_block_html: str, edited_html: str, key: str, want_text: str) -> list:
    """v3/cases_chain.py와 동일한 로직 — edit_lib 기반 블록 왕복 편집 검사."""
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
    fails = []
    if MODIFIED_DATE_ISO not in text_or_raw:
        fails.append("date_not_updated")
    if any(tok in text_or_raw for tok in OLD_DATE_TOKENS):
        fails.append("old_date_still_present")
    return fails


def _parse_plan_json(raw):
    text = FENCE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def _parse_patch_ops(raw):
    plan = _parse_plan_json(raw)
    return (plan or {}).get("ops", []) if plan is not None else []


def check_countdown_setfield_date(raw, _):
    for op in _parse_patch_ops(raw):
        if not isinstance(op, dict):
            continue
        if (op.get("op") == "set_field" and op.get("block_key") == "countdown"
                and op.get("field") == "target_date"):
            return [] if op.get("value") == MODIFIED_DATE_ISO else ["countdown_date_not_updated"]
    return ["countdown_setfield_missing"]


def _extract_json_block_content(plan: dict) -> dict:
    """plan(dict)에서 블록별로 비교 가능한 콘텐츠만 뽑는다 — variant는
    제외한다(재출력 시 variant를 다르게 골라도 '내용 보존'과는 무관한
    선택이므로)."""
    out = {}
    for item in (plan or {}).get("blocks", []):
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "hero":
            out["hero"] = {"title": str(item.get("title") or "").strip(),
                            "sub": str(item.get("sub") or "").strip()}
        elif t in ("benefits", "steps"):
            out[t] = [str(x).strip() for x in (item.get("items") or [])]
        elif t == "cta":
            out["cta"] = str(item.get("label") or "").strip()
    return out


def _extract_html_block_content(html: str) -> dict:
    """CHAIN7-S 3단계 전(S-T+E수정 결과) HTML에서 블록별 콘텐츠를 뽑는다
    — v5 cases_st.py가 강제하는 형태(h1/p, ul>li, ol>li, a)를 그대로
    가정한다."""
    soup = edit_lib.safe_soup(html)
    out = {}
    hero = soup.select_one('[data-block="hero"]')
    if hero is not None:
        h1, p = hero.find("h1"), hero.find("p")
        out["hero"] = {"title": h1.get_text(" ", strip=True) if h1 else "",
                        "sub": p.get_text(" ", strip=True) if p else ""}
    for key in ("benefits", "steps"):
        block = soup.select_one(f'[data-block="{key}"]')
        if block is not None:
            out[key] = [li.get_text(" ", strip=True) for li in block.find_all("li")]
    cta = soup.select_one('[data-block="cta"]')
    if cta is not None:
        a = cta.find("a")
        out["cta"] = a.get_text(" ", strip=True) if a else ""
    return out


def _content_drift_fails(before: dict, after: dict) -> list:
    fails = []
    for key in ("hero", "benefits", "steps", "cta"):
        if key not in before:
            continue
        if before[key] != after.get(key):
            fails.append(f"content_drift_{key}")
    return fails


def _check_countdown_format(plan: dict) -> list:
    cd = next((b for b in (plan or {}).get("blocks", [])
               if isinstance(b, dict) and b.get("type") == "countdown"), None)
    if cd is None:
        return []  # keep=[...,"countdown"]가 이미 lost_countdown으로 잡는다
    if not COUNTDOWN_DATE.match(str(cd.get("target_date", ""))):
        return ["countdown_bad_date_format"]
    return []


def _make_stage3_check_j(current_plan_snapshot: dict):
    def _check(raw, _rendered_ignored):
        plan2 = _parse_plan_json(raw)
        if plan2 is None:
            return []
        fails = _content_drift_fails(
            _extract_json_block_content(current_plan_snapshot),
            _extract_json_block_content(plan2))
        fails += _check_countdown_format(plan2)
        return fails
    return _check


def _make_stage3_check_s(before_html: str):
    def _check(raw, _rendered_ignored):
        plan2 = _parse_plan_json(raw)
        if plan2 is None:
            return []
        fails = _content_drift_fails(
            _extract_html_block_content(before_html),
            _extract_json_block_content(plan2))
        fails += _check_countdown_format(plan2)
        return fails
    return _check


def _mini_patch_system(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성을 수정하는 도우미다.

[현재 계획]
{plan_json}

전체 계획을 다시 쓰지 마라. 요청과 관련된 부분만 오퍼레이션으로 표현하라.

사용 가능한 오퍼레이션:
- set_field: {{"op":"set_field","block_key":"countdown","field":"target_date","value":"YYYY-MM-DD"}}

규칙:
- 언급되지 않은 블록/필드는 오퍼레이션에 아예 포함하지 마라.
- target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- JSON 외에는 아무것도 출력하지 마라."""


def _current_plan_system_j(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return f"""너는 이벤트 페이지의 구성 계획(JSON)을 만드는 도우미다.

[현재 계획 — 아래 값은 절대 바꾸지 말고 그대로 유지한다]
{plan_json}

위 계획의 hero·benefits·steps·cta 블록은 title·sub·items·label 값을
글자 하나까지 그대로 유지한 채 다시 낸다. 여기에 countdown 블록 하나만
새로 추가해서, 전체 계획을 처음부터 다시 출력한다.

countdown 블록 예시: {{"type":"countdown","variant":"digital","title":"마감임박","target_date":"YYYY-MM-DD"}}

규칙:
- hero/benefits/steps/cta 값은 위 계획과 동일하게 유지한다(재작성·요약 금지).
- countdown의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- notices 블록은 넣지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


def _blind_transcribe_system_s(current_html: str) -> str:
    return f"""너는 이미 만들어진 이벤트 페이지 HTML을 구성 계획(JSON)으로
바꾸는 도우미다.

[현재 페이지 HTML — 내용을 그대로 옮겨야 한다]
{current_html}

위 HTML에 있는 제목·소개·혜택·참여방법·버튼 문구를 절대 바꾸지 말고
그대로 옮겨서 JSON 계획으로 만든다. 여기에 countdown 블록 하나만 새로
추가한다.

countdown 블록 예시: {{"type":"countdown","variant":"digital","title":"마감임박","target_date":"YYYY-MM-DD"}}

규칙:
- HTML에 있는 문구를 그대로 옮긴다 — 새로 쓰거나 요약하지 마라.
- countdown의 target_date는 반드시 YYYY-MM-DD 형식으로 쓴다.
- notices 블록은 넣지 마라.
- JSON 외에는 아무것도 출력하지 마라."""


# ══════════════════════════════════════════════════════════════
#  CHAIN7-J — J-T 생성 → E수정 → JS-PLAN(JSON 뼈대 있음) → 값수정 2변형
# ══════════════════════════════════════════════════════════════

def custom_run_chain7_j(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    plan, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7J_GEN", kind="1_생성_JT", pair=case.pid,
        system=SYSTEM_JT7, prompt=CHAIN7_GEN_PROMPT, mode="plan",
        keep=list(REQUIRED), forbid=["notices"],
        json_schema=PLAN_SCHEMA_BASE, num_predict=CHAIN7_NUM_PREDICT_GEN)
    if plan is None:
        for pid, kind in [("CHAIN7J_EDIT", "2_수정_E"), ("CHAIN7J_JSADD", "3_JS추가_JSPLAN"),
                           ("CHAIN7J_VALE", "4_값수정_E"), ("CHAIN7J_VALK", "4_값수정_K")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    doc = render_plan(plan)
    cta_before = edit_lib.block_of(doc, "cta")
    edited_cta, edit_first, edit_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7J_EDIT", kind="2_수정_E_문구", pair=case.pid,
        system=edit_lib.build_block_edit_system("cta"),
        prompt=f"이 영역의 {EDIT_REQUEST_TEXT}\n\n{cta_before}", mode="html",
        keep=["cta"], forbid=[k for k in REQUIRED if k != "cta"],
        extra_check=lambda raw, html: check_block_text_edit(cta_before, html, "cta", EDIT_WANT_TEXT))
    if edited_cta is None:
        for pid, kind in [("CHAIN7J_JSADD", "3_JS추가_JSPLAN"),
                           ("CHAIN7J_VALE", "4_값수정_E"), ("CHAIN7J_VALK", "4_값수정_K")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    # 우리가 이미 아는 값(EDIT_WANT_TEXT)으로 cta.label을 직접 갱신한
    # "현재 계획"을 모델에게 보여준다 — README §2 "CHAIN7-J는 JSON 뼈대가
    # 있다"는 설계 그대로.
    current_plan = {
        **plan,
        "blocks": [
            {**b, "label": EDIT_WANT_TEXT} if isinstance(b, dict) and b.get("type") == "cta" else b
            for b in plan.get("blocks", [])
        ],
    }

    plan3, jsadd_first, jsadd_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7J_JSADD", kind="3_JS추가_JSPLAN_재생성", pair=case.pid,
        system=_current_plan_system_j(current_plan), prompt=CHAIN7_COUNTDOWN_ADD_REQUEST,
        mode="plan", keep=list(REQUIRED) + ["countdown"], forbid=["notices"],
        json_schema=PLAN_SCHEMA_BASE, num_predict=CHAIN7_NUM_PREDICT_STAGE34,
        extra_check=_make_stage3_check_j(current_plan))
    if plan3 is None:
        for pid, kind in [("CHAIN7J_VALE", "4_값수정_E"), ("CHAIN7J_VALK", "4_값수정_K")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and edit_first) else 0), 0

    stage123_first = gen_first and edit_first and jsadd_first
    stage123_final = gen_final and edit_final and jsadd_final

    # ── 값수정 변형 E: 렌더링된 전체 문서를 통째로 재작성 ──
    doc_with_cd = render_plan(plan3)
    _, vale_first, vale_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7J_VALE", kind="4_값수정_E_전체재작성", pair=case.pid,
        system=SYSTEM_WHOLE_EDIT,
        prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_HTML + doc_with_cd, mode="html",
        keep=list(REQUIRED) + ["countdown"], forbid=["notices"],
        extra_check=check_date_updated, num_predict=CHAIN7_NUM_PREDICT_STAGE34)

    # ── 값수정 변형 K: countdown 블록만 떼어내 미니 plan K패치 ──
    countdown_block = next((b for b in plan3.get("blocks", [])
                             if isinstance(b, dict) and b.get("type") == "countdown"), None)
    if countdown_block is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN7J_VALK", "4_값수정_K_countdown없음", case.pid, rows)
        valk_first = valk_final = 0
    else:
        mini_plan = {"blocks": [countdown_block], "theme": {}}
        _, valk_first, valk_final = _run_stage(
            model, runner, digest, backend, repeat_no, seed, rows, out_dir,
            pid="CHAIN7J_VALK", kind="4_값수정_K_미니패치", pair=case.pid,
            system=_mini_patch_system(mini_plan), prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON,
            mode="patch", keep=["countdown"], forbid=[], current_plan=mini_plan,
            extra_check=check_countdown_setfield_date, json_schema=PATCH_SCHEMA_BASE,
            num_predict=CHAIN7_NUM_PREDICT_STAGE34)

    e_first = 1 if (stage123_first and vale_first) else 0
    e_final = 1 if (stage123_final and vale_final) else 0
    k_first = 1 if (stage123_first and valk_first) else 0
    k_final = 1 if (stage123_final and valk_final) else 0
    # 반환값은 engine이 소비하지 않는다(참고용) — E/K 각각의 완주 여부는
    # CSV의 CHAIN7J_VALE/CHAIN7J_VALK 행으로 따로 집계한다(README §3).
    return (1 if (e_first or k_first) else 0), (1 if (e_final or k_final) else 0)


# ══════════════════════════════════════════════════════════════
#  CHAIN7-S — S-T 생성 → E수정 → JS-PLAN(맨눈 변환) → 값수정(K만)
# ══════════════════════════════════════════════════════════════

def custom_run_chain7_s(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    doc, gen_first, gen_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7S_GEN", kind="1_생성_ST", pair=case.pid,
        system=SYSTEM_ST7, prompt=CHAIN7_GEN_PROMPT, mode="html",
        keep=list(REQUIRED), forbid=["notices"], num_predict=CHAIN7_NUM_PREDICT_GEN)
    if doc is None:
        for pid, kind in [("CHAIN7S_EDIT", "2_수정_E"), ("CHAIN7S_JSADD", "3_JS추가_JSPLAN"),
                           ("CHAIN7S_VAL", "4_값수정_K")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_생성실패로_스킵", case.pid, rows)
        return 0, 0

    cta_before = edit_lib.block_of(doc, "cta")
    edited_cta, edit_first, edit_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7S_EDIT", kind="2_수정_E_문구", pair=case.pid,
        system=edit_lib.build_block_edit_system("cta"),
        prompt=f"이 영역의 {EDIT_REQUEST_TEXT}\n\n{cta_before}", mode="html",
        keep=["cta"], forbid=[k for k in REQUIRED if k != "cta"],
        extra_check=lambda raw, html: check_block_text_edit(cta_before, html, "cta", EDIT_WANT_TEXT))
    if edited_cta is None:
        for pid, kind in [("CHAIN7S_JSADD", "3_JS추가_JSPLAN"), ("CHAIN7S_VAL", "4_값수정_K")]:
            _blocked_row(runner, model, digest, backend, repeat_no, seed,
                         pid, kind + "_수정실패로_스킵", case.pid, rows)
        return (1 if gen_first else 0), 0

    merged_doc = edit_lib.replace_block(doc, "cta", edited_cta)

    # CHAIN7-J와 달리 JSON 뼈대가 없다 — HTML 문서 그대로를 보여주고
    # 맨눈으로 JSON 변환 + countdown 추가를 동시에 요청한다(README §2).
    plan3, jsadd_first, jsadd_final = _run_stage(
        model, runner, digest, backend, repeat_no, seed, rows, out_dir,
        pid="CHAIN7S_JSADD", kind="3_JS추가_JSPLAN_맨눈변환", pair=case.pid,
        system=_blind_transcribe_system_s(merged_doc), prompt=CHAIN7_COUNTDOWN_ADD_REQUEST,
        mode="plan", keep=list(REQUIRED) + ["countdown"], forbid=["notices"],
        json_schema=PLAN_SCHEMA_BASE, num_predict=CHAIN7_NUM_PREDICT_STAGE34,
        extra_check=_make_stage3_check_s(merged_doc))
    if plan3 is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN7S_VAL", "4_값수정_K_JS추가실패로_스킵", case.pid, rows)
        return (1 if (gen_first and edit_first) else 0), 0

    countdown_block = next((b for b in plan3.get("blocks", [])
                             if isinstance(b, dict) and b.get("type") == "countdown"), None)
    if countdown_block is None:
        _blocked_row(runner, model, digest, backend, repeat_no, seed,
                     "CHAIN7S_VAL", "4_값수정_K_countdown없음", case.pid, rows)
        val_first = val_final = 0
    else:
        mini_plan = {"blocks": [countdown_block], "theme": {}}
        _, val_first, val_final = _run_stage(
            model, runner, digest, backend, repeat_no, seed, rows, out_dir,
            pid="CHAIN7S_VAL", kind="4_값수정_K_미니패치", pair=case.pid,
            system=_mini_patch_system(mini_plan), prompt=CHAIN_COUNTDOWN_MODIFY_REQUEST_JSON,
            mode="patch", keep=["countdown"], forbid=[], current_plan=mini_plan,
            extra_check=check_countdown_setfield_date, json_schema=PATCH_SCHEMA_BASE,
            num_predict=CHAIN7_NUM_PREDICT_STAGE34)

    chain_first = 1 if (gen_first and edit_first and jsadd_first and val_first) else 0
    chain_final = 1 if (gen_final and edit_final and jsadd_final and val_final) else 0
    return chain_first, chain_final


CASES = [
    Case("CHAIN7J", "JSON뼈대_JSPLAN_값수정2변형", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain7_j),
    Case("CHAIN7S", "맨눈변환_JSPLAN_K값수정", "CHAIN", "", "", "custom",
         custom_run=custom_run_chain7_s),
]


def self_check():
    assert len(CASES) == 2
    assert {c.pid for c in CASES} == {"CHAIN7J", "CHAIN7S"}
    for c in CASES:
        assert c.group == "CHAIN"
        assert c.mode == "custom"
        assert callable(c.custom_run)

    assert "countdown" in json.dumps(PLAN_SCHEMA_BASE), "PLAN_SCHEMA_BASE에 countdown이 없음"

    # ── 내용보존 검사 회귀 (J 노선: JSON 대 JSON) ──
    base_plan = {"blocks": [
        {"type": "hero", "variant": "flowbite_split", "title": "제목", "sub": "소개"},
        {"type": "benefits", "variant": "flowbite_cards", "items": ["혜택1", "혜택2", "혜택3"]},
        {"type": "steps", "variant": "hyperui_numbered", "items": ["1단계", "2단계", "3단계"]},
        {"type": "cta", "variant": "flowbite_banner", "label": EDIT_WANT_TEXT},
    ]}
    good_reoutput = json.dumps({"blocks": base_plan["blocks"] + [
        {"type": "countdown", "variant": "digital", "title": "마감임박",
         "target_date": INITIAL_DATE_ISO},
    ]}, ensure_ascii=False)
    check_j = _make_stage3_check_j(base_plan)
    assert check_j(good_reoutput, good_reoutput) == [], "정상 재출력이 내용보존 검사에 걸림"

    drifted_plan = json.loads(good_reoutput)
    drifted_plan["blocks"][0]["title"] = "다른 제목"
    drifted_raw = json.dumps(drifted_plan, ensure_ascii=False)
    fails = check_j(drifted_raw, drifted_raw)
    assert "content_drift_hero" in fails, "hero 드리프트를 못 잡음"

    bad_date_plan = json.loads(good_reoutput)
    bad_date_plan["blocks"][-1]["target_date"] = "2026/08/31"
    bad_date_raw = json.dumps(bad_date_plan, ensure_ascii=False)
    assert "countdown_bad_date_format" in check_j(bad_date_raw, bad_date_raw)

    # ── 내용보존 검사 회귀 (S 노선: HTML 대 JSON, 맨눈 변환) ──
    before_html = (
        '<section data-block="hero" class="ev-block block-hero">'
        '<h1>제목</h1><p>소개</p></section>'
        '<section data-block="benefits" class="ev-block block-benefits">'
        '<ul><li>혜택1</li><li>혜택2</li><li>혜택3</li></ul></section>'
        '<section data-block="steps" class="ev-block block-steps">'
        '<ol><li>1단계</li><li>2단계</li><li>3단계</li></ol></section>'
        '<section data-block="cta" class="ev-block block-cta">'
        f'<a href="#" class="btn">{EDIT_WANT_TEXT}</a></section>'
    )
    check_s = _make_stage3_check_s(before_html)
    assert check_s(good_reoutput, good_reoutput) == [], "정상 맨눈변환이 내용보존 검사에 걸림"
    assert "content_drift_hero" in check_s(drifted_raw, drifted_raw), "S노선 hero 드리프트를 못 잡음"

    # ── 값수정(K) 검사 회귀 ──
    good_patch = json.dumps({"ops": [
        {"op": "set_field", "block_key": "countdown", "field": "target_date",
         "value": MODIFIED_DATE_ISO},
    ]}, ensure_ascii=False)
    assert check_countdown_setfield_date(good_patch, "") == []
    bad_patch = json.dumps({"ops": [
        {"op": "set_field", "block_key": "countdown", "field": "target_date",
         "value": "2026-01-01"},
    ]}, ensure_ascii=False)
    assert check_countdown_setfield_date(bad_patch, "") == ["countdown_date_not_updated"]

    # ── 값수정(E) 검사 회귀 ──
    assert check_date_updated(f"...{MODIFIED_DATE_ISO}...") == []
    assert "date_not_updated" in check_date_updated("...아무 날짜도 없음...")
    assert "old_date_still_present" in check_date_updated(f"...{INITIAL_DATE_ISO}...{MODIFIED_DATE_ISO}...")

    # ── 편집 검사 회귀 (edit_lib 기반, v3와 동일 로직) ──
    baseline = '<section data-block="cta"><a href="#" class="btn">가입하기</a></section>'
    edited = f'<section data-block="cta"><a href="#" class="btn">{EDIT_WANT_TEXT}</a></section>'
    assert check_block_text_edit(baseline, edited, "cta", EDIT_WANT_TEXT) == []
    drifted_edit = f'<section data-block="cta"><a href="#" class="btn2">{EDIT_WANT_TEXT}</a></section>'
    assert check_block_text_edit(baseline, drifted_edit, "cta", EDIT_WANT_TEXT) != []

    print("  [cases_chain7] self_check 통과")
