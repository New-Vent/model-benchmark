"""
deterministic_json.py — JSON 방식(Page Schema)의 Code 기반 평가
====================================================================
`docs/architect/project-architect.md (JSON 파트)`의 Page Schema / Modification Command
규격을 코드로 옮긴 것이다.

★★ 정확성에 대한 중요한 경고 — deterministic_html.py 와 근본적으로 다르다
    HTML 쪽(`deterministic_html.py`)은 실제로 배포된
    `com.newvent.registry.Block/BlockValidator.java`를 그대로 미러했다 —
    대조할 실제 구현이 있었다.

    JSON 방식(Page Schema, Section, Component, Behavior, Operation Engine)은
    **newvent-backend 어디에도 구현되어 있지 않다.** 2026-09-22 기준으로
    저장소 전체(`grep -r "PageSchema\\|OperationEngine\\|ModificationCommand"`)를
    뒤져도 클래스가 하나도 없다 — `project-architect.md (JSON 파트)` 자신의 제목이
    "추가 구현 범위"인 것과 일치한다. 즉 이 문서는 **아직 실현되지 않은
    설계도**이고, 이 파일은 그 설계도"만"을 근거로 새로 쓴 것이다.

    따라서 이 파일이 잡아내는 실패는 "실제 서버가 거부하는 것"이 아니라
    "문서가 규정한 대로면 거부해야 하는 것"이다. JSON_IMPLEMENTED_IN_BACKEND
    = False 로 이 사실을 코드에도 남긴다 — 결과 리포트(run_judge.py)가 이
    플래그를 보고 매 결과에 "spec-only" 표시를 강제로 붙인다.

★ HTML 쪽과 맞춘 설계상의 선택 (문서에 명시되지 않아 추론한 것 — 근거를 남긴다)
    - `notice` variant를 SERVER 소유로 취급한다. HTML 쪽 `notices` 블록이
      `Source.SERVER`(§34 대응 개념)인 것과 대응시킨 것이다. 문서 자체는
      이 소유권을 명시하지 않는다.
    - Component.type 허용 목록은 문서 §5 예시(heading/text/image/button/
      card/input)에 list/icon을 더한 것 — 문서가 "..." 로 열어뒀기 때문에
      완전한 목록이 아니라는 것을 `COMPONENT_TYPES`의 주석에 남긴다.
"""

from __future__ import annotations

import json
import re

JSON_IMPLEMENTED_IN_BACKEND = False

# project-architect.md (JSON 파트) §4.2 의 예시 variant 목록
ALLOWED_VARIANTS = {
    "hero", "intro", "promotion", "product", "event", "feature", "benefit",
    "banner", "gallery", "steps", "timeline", "countdown", "review", "faq",
    "form", "cta", "notice", "location", "social", "footer",
}
# 추론: HTML의 notices(SERVER)에 대응 — 근거는 모듈 docstring 참고
SERVER_OWNED_VARIANTS = {"notice"}

# §5 예시 + 문서가 "..." 로 명시적으로 열어둔 확장분(list/icon)
COMPONENT_TYPES = {"heading", "text", "image", "button", "card", "input",
                    "list", "icon"}

OPERATIONS = {"update", "delete", "create", "move", "replace"}

_PLACEHOLDER = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")

# ══════════════════════════════════════════════════════════════════
#  soft/hard 실패 구분 — deterministic_html.py와 동일한 근거
#  (base/checks.py SOFT_FAILS, base/engine.py hard_ok/all_ok 관례).
#  코드펜스·군더더기 설명은 이미 validate_schema/validate_modification가
#  파싱 전에 걷어내므로 여기서 "raw 대비 무엇이 걷혔나"만 별도로 잰다.
# ══════════════════════════════════════════════════════════════════
FENCE = re.compile(r"```")
SOFT_FAILS = {"code_fence", "extra_text"}


def extract_json_text(raw_text: str) -> str:
    """validate_schema/validate_modification이 내부적으로 하는 것과 같은
    추출을 독립적으로 다시 한다 — format_fails가 raw와 비교할 기준이 필요."""
    text = re.sub(r"```(json)?", "", raw_text or "")
    s, e = text.find("{"), text.rfind("}")
    return text[s:e + 1] if (s != -1 and e != -1) else ""


def format_fails(raw_text: str, extracted: str) -> list:
    """deterministic_html.format_fails와 같은 기준(길이 차 40자)."""
    fails = []
    if len((raw_text or "").strip()) - len(extracted) > 40:
        fails.append("extra_text")
    if FENCE.search(raw_text or ""):
        fails.append("code_fence")
    return fails


def split_fails(fails: list) -> tuple:
    hard = [f for f in fails if f not in SOFT_FAILS]
    soft = [f for f in fails if f in SOFT_FAILS]
    return hard, soft


def _walk_components(schema: dict):
    """(section, component) 쌍을 문서 순서대로 낸다."""
    for sec in schema.get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        for comp in sec.get("components", []) or []:
            if isinstance(comp, dict):
                yield sec, comp


# ══════════════════════════════════════════════════════════════════
#  Schema Compliance — §13, §15(Semantic Validation)
# ══════════════════════════════════════════════════════════════════

def validate_schema(raw_text: str) -> tuple[list, dict | None]:
    """반환: (fails, parsed_schema or None)"""
    text = re.sub(r"```(json)?", "", raw_text or "")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], None
    try:
        schema = json.loads(text[s:e + 1])
    except Exception:
        return ["bad_json"], None
    if not isinstance(schema, dict):
        return ["bad_json"], None

    fails = []
    if schema.get("type") != "page":
        fails.append("invalid_root_type")

    sections = schema.get("sections")
    if not isinstance(sections, list) or not sections:
        return fails + ["missing_sections"], schema

    seen_ids = set()
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            fails.append(f"bad_section_{i}")
            continue
        sec_id = sec.get("id")
        if not sec_id or not isinstance(sec_id, str):
            fails.append(f"missing_section_id_{i}")
        elif sec_id in seen_ids:
            fails.append(f"duplicate_id_{sec_id}")
        else:
            seen_ids.add(sec_id)

        variant = sec.get("variant")
        if variant not in ALLOWED_VARIANTS:
            fails.append(f"unknown_variant_{variant}")
        elif variant in SERVER_OWNED_VARIANTS:
            fails.append(f"wrote_server_section_{sec_id or i}")

        for comp in sec.get("components", []) or []:
            if not isinstance(comp, dict):
                fails.append(f"bad_component_in_{sec_id or i}")
                continue
            c_id = comp.get("id")
            if not c_id or not isinstance(c_id, str):
                fails.append("missing_component_id")
            elif c_id in seen_ids:
                fails.append(f"duplicate_id_{c_id}")
            else:
                seen_ids.add(c_id)
            if comp.get("type") not in COMPONENT_TYPES:
                fails.append(f"unknown_component_type_{comp.get('type')}")
            if "behavior" in comp and comp["behavior"] is not None \
                    and not isinstance(comp["behavior"], dict):
                fails.append(f"bad_behavior_{c_id}")

    blob = json.dumps(schema, ensure_ascii=False)
    if _PLACEHOLDER.search(blob):
        fails.append("placeholder")

    return fails, schema


# ══════════════════════════════════════════════════════════════════
#  Modification Command — §12, §13(Operation Validation)
# ══════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = {
    "update": (["target", "id"], ["changes"]),
    "delete": (["target", "id"], []),
    "create": (["parent", "id"], ["component"]),
    "move": (["target", "id"], ["parent", "id"]),
    "replace": (["target", "id"], ["component"]),
}


def _get_path(d: dict, path: list):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def validate_modification(raw_text: str, current_schema: dict) -> tuple[list, dict | None]:
    """반환: (fails, parsed_command or None). current_schema는 수정 대상 검증에 쓴다."""
    text = re.sub(r"```(json)?", "", raw_text or "")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], None
    try:
        cmd = json.loads(text[s:e + 1])
    except Exception:
        return ["bad_json"], None
    if not isinstance(cmd, dict):
        return ["bad_json"], None

    fails = []
    op = cmd.get("operation")
    if op not in OPERATIONS:
        return [f"unknown_operation_{op}"], cmd

    req_first, req_second = REQUIRED_FIELDS[op]
    if _get_path(cmd, req_first) is None:
        fails.append(f"missing_{'_'.join(req_first)}")
    if req_second and _get_path(cmd, req_second) is None:
        fails.append(f"missing_{'_'.join(req_second)}")

    all_ids = {c.get("id") for _, c in _walk_components(current_schema)}
    all_ids |= {s.get("id") for s in current_schema.get("sections", []) or []
                if isinstance(s, dict)}
    server_ids = {
        s.get("id") for s in current_schema.get("sections", []) or []
        if isinstance(s, dict) and s.get("variant") in SERVER_OWNED_VARIANTS
    }

    target_id = _get_path(cmd, ["target", "id"])
    if op in ("update", "delete", "move", "replace") and target_id is not None:
        if target_id not in all_ids:
            fails.append(f"target_not_found_{target_id}")
        elif target_id in server_ids:
            fails.append(f"touched_server_section_{target_id}")

    if op == "create":
        parent_id = _get_path(cmd, ["parent", "id"])
        if parent_id is not None and parent_id not in all_ids \
                and parent_id not in {s.get("id") for s in current_schema.get("sections", [])
                                       if isinstance(s, dict)}:
            fails.append(f"parent_not_found_{parent_id}")

    if op in ("create", "replace"):
        comp = cmd.get("component")
        if isinstance(comp, dict) and comp.get("type") not in COMPONENT_TYPES:
            fails.append(f"unknown_component_type_{comp.get('type')}")

    return fails, cmd


def diff_unintended_changes(before: dict, after: dict, touched_ids: set) -> list:
    """§22 Existing Feature Preservation / Unintended Change 대응.
    Operation이 명시적으로 언급하지 않은 id의 내용이 바뀌었는가."""
    before_by_id = {c.get("id"): c for _, c in _walk_components(before)}
    after_by_id = {c.get("id"): c for _, c in _walk_components(after)}
    unexpected = []
    for cid, b in before_by_id.items():
        if cid in touched_ids:
            continue
        a = after_by_id.get(cid)
        if a is None or a != b:
            unexpected.append(cid)
    return unexpected


# ══════════════════════════════════════════════════════════════════
#  자체 검사
# ══════════════════════════════════════════════════════════════════

def self_check():
    good = {
        "type": "page", "version": "1.0", "metadata": {"title": "t"}, "theme": {},
        "sections": [{
            "type": "section", "id": "section-hero", "variant": "hero",
            "components": [
                {"type": "heading", "id": "hero-title", "content": {"text": "여름"}},
                {"type": "button", "id": "hero-button", "content": {"text": "참여"},
                 "behavior": {"event": "click", "action": "open-modal", "target": "m"}},
            ],
        }],
    }
    fails, parsed = validate_schema(json.dumps(good, ensure_ascii=False))
    assert not fails, fails
    assert parsed is not None

    fails, _ = validate_schema("이건 JSON이 아니다")
    assert fails == ["no_json"]

    fails, _ = validate_schema('{"type":"page"}')
    assert "missing_sections" in fails

    dup = json.loads(json.dumps(good))
    dup["sections"].append(dup["sections"][0])
    fails, _ = validate_schema(json.dumps(dup, ensure_ascii=False))
    assert any(f.startswith("duplicate_id_") for f in fails), fails

    server_write = json.loads(json.dumps(good))
    server_write["sections"][0]["variant"] = "notice"
    fails, _ = validate_schema(json.dumps(server_write, ensure_ascii=False))
    assert any(f.startswith("wrote_server_section_") for f in fails), fails

    bad_variant = json.loads(json.dumps(good))
    bad_variant["sections"][0]["variant"] = "hero_center"  # 문서 §4가 명시적으로 금지한 형태
    fails, _ = validate_schema(json.dumps(bad_variant, ensure_ascii=False))
    assert any(f.startswith("unknown_variant_") for f in fails), fails

    # Modification Command
    cmd = json.dumps({"operation": "update", "target": {"id": "hero-button"},
                       "changes": {"content": {"text": "이벤트 참여하기"}}})
    fails, parsed_cmd = validate_modification(cmd, good)
    assert not fails, fails

    bad_cmd = json.dumps({"operation": "update", "target": {"id": "no-such-id"},
                           "changes": {}})
    fails, _ = validate_modification(bad_cmd, good)
    assert "target_not_found_no-such-id" in fails

    notice_schema = json.loads(json.dumps(good))
    notice_schema["sections"].append(
        {"type": "section", "id": "section-notice", "variant": "notice", "components": []})
    touch_server = json.dumps({"operation": "delete", "target": {"id": "section-notice"}})
    fails, _ = validate_modification(touch_server, notice_schema)
    assert "touched_server_section_section-notice" in fails

    unknown_op = json.dumps({"operation": "teleport", "target": {"id": "x"}})
    fails, _ = validate_modification(unknown_op, good)
    assert fails == ["unknown_operation_teleport"]

    missing_field = json.dumps({"operation": "create", "parent": {"id": "section-hero"}})
    fails, _ = validate_modification(missing_field, good)
    assert "missing_component" in fails

    # unintended change
    after = json.loads(json.dumps(good))
    after["sections"][0]["components"][1]["content"]["text"] = "몰래 바뀜"
    unexpected = diff_unintended_changes(good, after, touched_ids={"hero-title"})
    assert unexpected == ["hero-button"], unexpected

    # soft/hard 구분 — deterministic_html.py와 동일 기준
    good_text = json.dumps(good, ensure_ascii=False)
    fenced = "```json\n" + good_text + "\n```"
    ff = format_fails(fenced, extract_json_text(fenced))
    assert ff == ["code_fence"], ff
    hard, soft = split_fails(ff)
    assert hard == [] and soft == ["code_fence"]

    chatty = ("안녕하세요! 요청하신 Page Schema를 아래와 같이 정성껏 만들어 드렸습니다. "
              "확인 부탁드립니다.\n\n" + good_text)
    ff2 = format_fails(chatty, extract_json_text(chatty))
    assert "extra_text" in ff2, ff2

    mixed = ["missing_sections", "code_fence", "unknown_variant_x"]
    hard, soft = split_fails(mixed)
    assert hard == ["missing_sections", "unknown_variant_x"] and soft == ["code_fence"]

    print("  [deterministic_json] self_check 통과 (spec-only, 백엔드 구현 없음)")


if __name__ == "__main__":
    self_check()
