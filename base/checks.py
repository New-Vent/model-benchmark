"""
checks.py — 검증 함수 모음 (공통, 아무도 개별로 건드리지 않음)
================================================================
각 cases_*.py는 이 파일의 함수를 가져다 쓰기만 한다. 새 검증
규칙이 필요하면 여기 추가하고 PR로 팀 합의를 받는다 — 이 파일을
동시에 여러 명이 건드리면 충돌이 나므로, 그럴 땐 먼저 이슈로
"이런 검증이 필요하다"를 공유한 뒤 한 사람이 반영한다.
"""

import copy
import json
import re
from html.parser import HTMLParser

from bs4 import BeautifulSoup

from registry import BY_KEY, SERVER, THEME_FIELDS, STYLE_PRESETS, render_plan

FENCE = re.compile(r"```")
PLACEHOLDER = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")
BAD_TAGS = ["script", "iframe", "object", "embed", "style"]
FULL_DOC = ["html", "head", "body"]
SOFT_FAILS = {"code_fence", "extra_text", "excess_ops_review"}

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


class _StrictTagBalanceChecker(HTMLParser):
    """BeautifulSoup은 관대해서 태그가 깨져도 조용히 고쳐버린다.
    원문을 엄격하게 스캔해 실제 마크업 결함을 별도로 잡아낸다."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.data_block_values = []

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            attrs_dict = dict(attrs)
            if "data-block" in attrs_dict:
                self.data_block_values.append(attrs_dict["data-block"])
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"unexpected_closing_tag_{tag}")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.errors.append(f"mismatched_nesting_{tag}")
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"unmatched_closing_tag_{tag}")


def check_html_structural_validity(raw_html: str) -> list:
    fails = []
    checker = _StrictTagBalanceChecker()
    try:
        checker.feed(raw_html)
        checker.close()
    except Exception:
        return ["html_parse_exception"]
    fails += checker.errors
    if checker.stack:
        fails.append(f"unclosed_tags_{'_'.join(checker.stack)}")
    dup = sorted({k for k in checker.data_block_values
                  if checker.data_block_values.count(k) > 1})
    for k in dup:
        fails.append(f"duplicate_data_block_{k}")
    return fails


def check_html(raw, html, keep, forbid, strict_structure, allow_script=False):
    """
    allow_script: JS군처럼 <script>가 정당하게 필요한 케이스만 True로
    넘긴다. 기본은 False — LLM이 raw HTML을 생성하는 N/S군은 script를
    절대 허용하지 않는다(원칙: LLM은 JS 코드를 직접 쓰지 않는다).
    """
    fails, notes = [], []
    if not html:
        return ["no_html"], "HTML을 찾을 수 없습니다. <section> 태그로 시작하는 HTML만 출력하세요."

    if len(raw.strip()) - len(html) > 40:
        fails.append("extra_text")
        notes.append("HTML 앞뒤에 설명이 붙어 있습니다.")
    if FENCE.search(raw):
        fails.append("code_fence")
        notes.append("코드블록으로 감쌌습니다.")

    structural_fails = check_html_structural_validity(html)
    if structural_fails:
        fails += structural_fails
        notes.append("HTML 태그가 제대로 열리고 닫히지 않았거나 data-block이 중복됩니다: "
                     + ", ".join(structural_fails[:3]))

    # BeautifulSoup은 우리가 만든 check_html_structural_validity보다
    # 엄격해서, LLM이 <!-- 주석을 <![--- 처럼 완전히 틀리게 쓰는 등
    # 심하게 깨진 마크업에서는 파싱 자체를 거부(ParserRejectedMarkup)
    # 할 수 있다. 이걸 안 잡으면 이 케이스 하나가 전체 실행을 죽인다
    # — 실제로 발생했던 크래시라 반드시 방어해야 한다.
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        fails.append("unparseable_html")
        notes.append(f"HTML을 파싱할 수 없습니다({type(e).__name__}). "
                     f"주석이나 특수 문자 사용을 피하고 일반적인 HTML만 출력하세요.")
        return fails, " ".join(notes)

    if not soup.find_all("section"):
        fails.append("no_section")
        notes.append("<section> 태그가 없습니다.")

    bad_tags = [t for t in BAD_TAGS if not (allow_script and t == "script")]
    for t in bad_tags:
        if soup.find(t):
            fails.append(f"bad_tag_{t}")
            notes.append(f"<{t}> 태그를 제거하세요.")

    for t in FULL_DOC:
        if soup.find(t):
            fails.append(f"full_doc_{t}")
            notes.append(f"<{t}> 태그가 있습니다. 조각만 출력하세요.")

    found = PLACEHOLDER.findall(html)
    if found:
        fails.append("placeholder")
        notes.append(f"자리표시자가 남아 있습니다: {', '.join(found[:3])}.")

    for sec in soup.find_all("section"):
        if not sec.get("data-block"):
            fails.append("no_data_block")
            notes.append('모든 <section> 에 data-block="이름" 속성이 있어야 합니다.')
            break

    for k in keep:
        el = soup.select_one(f'[data-block="{k}"]')
        if el is None:
            fails.append(f"lost_{k}")
            notes.append(f"{k} 영역이 없습니다.")
            continue
        if not strict_structure:
            continue
        b = BY_KEY[k]
        if b.must and not el.select_one(b.must):
            fails.append(f"empty_{k}")
            notes.append(f"{k} 안에 {b.shape} — 맨 텍스트만 두면 안 됩니다.")
        elif b.min_items:
            n = len(el.select(b.count_selector))
            if n < b.min_items:
                fails.append(f"few_{k}")
                notes.append(f"{k} 항목이 {n}개입니다. {b.min_items}개 이상 필요합니다.")

    for k in forbid:
        if soup.select_one(f'[data-block="{k}"]'):
            b = BY_KEY.get(k)
            if b and b.source == SERVER:
                fails.append(f"wrote_{k}")
                notes.append(f"{k} 영역은 만들면 안 됩니다.")
            else:
                fails.append(f"extra_{k}")
                notes.append(f"{k} 영역은 만들지 마세요.")

    return fails, " ".join(notes)


def check_css_structural_validity(style_html: str) -> list:
    m = re.search(r"<style>(.*?)</style>", style_html, re.S)
    css = m.group(1) if m else style_html
    fails, balance = [], 0
    for ch in css:
        if ch == "{":
            balance += 1
        elif ch == "}":
            balance -= 1
            if balance < 0:
                return ["css_unbalanced_braces"]
    if balance != 0:
        fails.append("css_unbalanced_braces")
    if css.count("{") > 4:
        fails.append("css_unexpected_extra_rules")
    return fails


def check_plan(raw, keep, forbid):
    fails, notes = [], []
    text = FENCE.sub("", raw).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return ["no_json"], "JSON을 찾을 수 없습니다.", None, ""
    try:
        plan = json.loads(text[s:e + 1])
    except Exception as ex:
        return ["bad_json"], f"JSON 파싱 실패: {ex}", None, ""

    if len(raw.strip()) - len(text[s:e + 1]) > 40:
        fails.append("extra_text")
        notes.append("JSON 앞뒤에 설명이 붙어 있습니다.")
    if FENCE.search(raw):
        fails.append("code_fence")
        notes.append("코드블록으로 감쌌습니다.")

    blocks = plan.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return fails + ["no_blocks"], "blocks 배열이 없습니다.", plan, ""

    seen = []
    for i, item in enumerate(blocks):
        if not isinstance(item, dict):
            fails.append("bad_item")
            continue
        t = item.get("type")
        b = BY_KEY.get(t)
        if b is None:
            fails.append("unknown_type")
            notes.append(f'"{t}" 는 없는 블록입니다.')
            continue
        if b.source == SERVER:
            fails.append(f"wrote_{t}")
            notes.append(f"{t} 는 넣으면 안 됩니다.")
            continue
        seen.append(t)
        v = b.variant(item.get("variant"))
        if v is None:
            fails.append("unknown_variant")
            notes.append(f'{t} 의 variant "{item.get("variant")}" 가 없습니다.')
            continue
        for f in v.fields:
            val = item.get(f)
            if f == "items":
                if not isinstance(val, list) or len(val) < b.min_items:
                    fails.append(f"few_{t}")
                elif any(not isinstance(x, str) or not x.strip() for x in val):
                    fails.append(f"empty_item_{t}")
            elif f == "sub":
                continue
            elif not isinstance(val, str) or not val.strip():
                fails.append(f"missing_{t}_{f}")

    for k in keep:
        if k not in seen:
            fails.append(f"lost_{k}")
    for k in forbid:
        if k in seen:
            fails.append(f"extra_{k}")

    blob = json.dumps(plan, ensure_ascii=False)
    if PLACEHOLDER.findall(blob):
        fails.append("placeholder")

    return fails, " ".join(notes), plan, render_plan(plan)


def apply_patch(current_plan: dict, patch: dict) -> dict:
    blocks = copy.deepcopy(current_plan.get("blocks", []))
    theme = copy.deepcopy(current_plan.get("theme", {}))

    def find(key):
        return next((i for i, b in enumerate(blocks) if b.get("type") == key), None)

    for op in patch.get("ops", []):
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "set_field":
            i = find(op.get("block_key"))
            if i is not None and isinstance(op.get("field"), str):
                blocks[i][op["field"]] = op.get("value", "")
        elif kind == "append_item":
            i = find(op.get("block_key"))
            if i is not None:
                blocks[i].setdefault("items", [])
                if isinstance(blocks[i]["items"], list):
                    blocks[i]["items"].append(op.get("value", ""))
        elif kind == "remove_block":
            i = find(op.get("block_key"))
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

    return {"blocks": blocks, "theme": theme}


def diff_unintended_changes(current_plan: dict, merged: dict, ops: list) -> list:
    touched, removed, added = set(), set(), set()
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind in ("set_field", "append_item"):
            touched.add(op.get("block_key"))
        elif kind == "remove_block":
            removed.add(op.get("block_key"))
        elif kind == "add_block":
            added.add(op.get("type"))
    before_by_type = {b.get("type"): b for b in current_plan.get("blocks", [])}
    after_by_type = {}
    for b in merged.get("blocks", []):
        after_by_type.setdefault(b.get("type"), b)
    unexpected = []
    for t, before_block in before_by_type.items():
        if t in touched or t in removed or t in added:
            continue
        after_block = after_by_type.get(t)
        if after_block is None or after_block != before_block:
            unexpected.append(t)
    return unexpected


def check_patch(raw, current_plan, keep, forbid):
    text = FENCE.sub("", raw).strip()
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
        if not patch.get("reason"):
            fails.append("missing_reason")
        return fails, " ".join(notes), None, ""

    ops = patch.get("ops")
    if not isinstance(ops, list) or not ops:
        return fails + ["no_ops"], "ops 배열이 없습니다.", patch, ""

    valid_kinds = {"set_field", "append_item", "remove_block", "add_block",
                   "set_theme", "apply_preset"}
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in valid_kinds:
            fails.append("unknown_op")
            continue
        if op.get("op") in ("set_field", "append_item", "remove_block"):
            if op.get("block_key") not in [b["type"] for b in current_plan.get("blocks", [])]:
                fails.append("unknown_block_key")
            if op.get("block_key") in [k for k, b in BY_KEY.items() if b.source == SERVER]:
                fails.append("touched_server_block")

    merged = apply_patch(current_plan, patch)
    rendered = render_plan(merged)

    rf, rn = check_html(rendered, rendered, keep, forbid, True)
    fails += rf
    if rn:
        notes.append(rn)

    unexpected = diff_unintended_changes(current_plan, merged, ops)
    for t in unexpected:
        fails.append(f"unintended_side_effect_{t}")

    if len([o for o in ops if isinstance(o, dict)]) >= 2:
        fails.append("excess_ops_review")

    return fails, " ".join(notes), merged, rendered


def extract(raw: str) -> str:
    text = FENCE.sub("", raw)
    s, e = text.find("<"), text.rfind(">")
    return text[s:e + 1].strip() if s != -1 and e != -1 else ""
