"""
cases_kt.py — K-T 군: 같은 수정을 패치 JSON 으로
=================================================
S-E 와 **글자 그대로 같은 요청 문구**를 쓴다. 그래야 pair 비교가 성립한다.
어긋나면 "다른 요청"을 비교하게 되므로, 프롬프트를 고칠 때는 반드시
`cases_se.py` 와 함께 고칠 것. (v1 cases_ns ↔ v2 cases_j 에서 이미 한 번
겪은 문제다.)

    SE1 ↔ KT1   버튼 문구를 '지금 응원하기' 로
    SE2 ↔ KT2   제목을 '설 선물 대축제' 로
    SE3 ↔ KT3   혜택 마지막 항목 삭제
    SE4 ↔ KT4   혜택 항목 추가
    SE5 ↔ KT5   단계 설명 짧게

baseline 은 `templates.plan_of()` — 실제 템플릿의 **내용**(문구·항목 수·
분량)을 담은 plan 이다. 모델은 이 JSON 만 보고 마크업은 아예 안 본다.

한계 — 반드시 읽을 것
    `component_library.py` 의 variant 는 Tailwind 풍 마크업을 내므로
    렌더 결과가 실제 템플릿과 다르다. 따라서 K-T 에서는 **클래스 보존
    검사를 하지 않는다**(할 수 없다). S-E 는 하고 K-T 는 못 하는 이 비대칭은
    component_library 에 실제 템플릿 variant 가 등록되면 해소된다.

    그때까지 S-E ↔ K-T 비교는 `checks_v4.split_fails()` 의 **공통 실패만**
    써야 한다 — class_lost 를 한쪽에만 적용하면 비교가 무너진다.
"""

import json

from engine import Case
from registry import build_patch_json_schema

import checks_v4
import templates as T

GROUPS = ["K-T"]

PATCH_SCHEMA = build_patch_json_schema()

# 패치 오퍼레이션은 짧다 — v2 실측 eval_count 중앙값 30~46 tok.
# 현재 patch 캡 256 으로 충분하다. (전체 페이지 생성만 캡을 넘는다.)


def _system(current_plan: dict) -> str:
    plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)
    return "\n".join([
        "너는 이벤트 페이지의 구성 계획(JSON)을 수정하는 도우미다.",
        "",
        "아래가 현재 계획이다. 요청에 맞게 **바꿔야 할 부분만** 패치",
        "오퍼레이션으로 출력한다. 계획 전체를 다시 쓰지 마라.",
        "",
        "현재 계획:",
        plan_json,
        "",
        "규칙:",
        "- 요청받은 것만 바꾼다. 다른 블록은 건드리지 마라.",
        "- 값만 쓴다. HTML 태그를 넣지 마라 — 마크업은 서버가 만든다.",
        "- 날짜를 임의로 만들지 마라.",
        "- 대괄호 자리표시자를 남기지 마라.",
        "- 주어지지 않은 혜택을 지어내지 마라.",
    ])


def _make_check(current_plan: dict):
    """plan 안의 텍스트 필드에 태그가 섞였는지 본다.

    base/checks.py 의 check_patch 에는 이 검사가 없다 — v3 감사에서
    "성공 처리된 22건이 이걸로 샌다"고 지적한 구멍이다.
    """
    def _check(raw, html):
        try:
            text = raw.strip()
            s, e = text.find("{"), text.rfind("}")
            patch = json.loads(text[s:e + 1]) if s >= 0 else {}
        except Exception:
            return []
        merged = None
        try:
            from checks import apply_patch
            merged = apply_patch(current_plan, patch)
        except Exception:
            return []
        fails, _ = checks_v4.check_tag_in_fields(merged)
        return fails
    return _check


def _case(pid, kind, tpl, prompt):
    plan = T.plan_of(tpl)
    return Case(
        pid, kind, "K-T",
        _system(plan),
        prompt,
        mode="patch",
        keep=tuple(b["type"] for b in plan["blocks"]),
        forbid=(),
        current_plan=plan,
        json_schema=PATCH_SCHEMA,
        extra_check=_make_check(plan),
    )


# 요청 문구는 cases_se.py 와 글자 그대로 같아야 한다.
CASES = [
    _case("KT1", "버튼문구수정_sports", 1,
          "이 영역의 버튼 문구를 '지금 응원하기' 로 바꿔줘."),
    _case("KT2", "제목수정_holiday", 2,
          "이 영역의 제목을 '설 선물 대축제' 로 바꿔줘."),
    _case("KT3", "혜택삭제_vip", 3,
          "이 영역의 혜택 항목 중 마지막 하나를 삭제해줘."),
    _case("KT4", "혜택추가_sale", 4,
          "이 영역에 혜택 항목을 하나 더 추가해줘. "
          "기존 항목과 같은 구조로 만들어야 한다."),
    _case("KT5", "단계문구수정_launch", 5,
          "이 영역의 각 단계 설명을 더 짧고 간결하게 다듬어줘. "
          "단계 개수는 그대로 둬라."),
]


def self_check():
    import cases_se

    assert len(CASES) == 5, f"케이스 수가 {len(CASES)}개"
    seen = set()
    for c in CASES:
        assert c.pid not in seen, f"{c.pid} 중복"
        seen.add(c.pid)
        assert c.group == "K-T"
        assert c.mode == "patch"
        assert c.current_plan is not None, f"{c.pid} current_plan 누락"
        assert c.json_schema is not None, f"{c.pid} json_schema 누락"
        assert "notices" not in c.keep, "notices 는 서버 소유라 plan 에 없어야 한다"

    # ★ pair 무결성 — S-E 와 요청 문구가 글자 그대로 같아야 한다
    se = {c.pid: c for c in cases_se.CASES}
    for k, s in zip(CASES, ["SE1", "SE2", "SE3", "SE4", "SE5"]):
        want = se[s].prompt.split("\n\n")[0]      # baseline HTML 앞부분만
        assert k.prompt == want, (
            f"{k.pid} 와 {s} 의 요청 문구가 다릅니다. pair 비교가 무너집니다.\n"
            f"  {s}: {want!r}\n  {k.pid}: {k.prompt!r}")

    # baseline plan 은 태그가 섞여 있으면 안 된다
    for c in CASES:
        f, _ = checks_v4.check_tag_in_fields(c.current_plan)
        assert not f, f"{c.pid} baseline plan 에 태그가 섞임: {f}"

    print("  [cases_kt] self_check 통과")
