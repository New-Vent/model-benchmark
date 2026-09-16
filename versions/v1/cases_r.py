"""
cases_r.py — R군: 라우터 정확도
=================================
담당자만 이 파일을 건드리세요.

사용자 요청을 보고 "어느 오퍼레이션을 써야 하는지"를 LLM이 정확히
판정하는지만 본다. 실제 렌더링/병합은 하지 않는다 — mode="router".
"""

from engine import Case

SYSTEM_ROUTER = """너는 사용자 요청을 보고 어떤 오퍼레이션을 써야 할지
판정하는 라우터다. 아래 JSON 형식으로만 답하라.

{"op": "set_field" | "append_item" | "remove_block" | "add_block" |
        "set_theme" | "rewrite_all" | "unclear"}

- 요청이 애매해서 어느 블록/필드인지 특정할 수 없으면 "unclear"를 골라라.
- 전체 톤/분위기를 바꾸라는 요청이면 "rewrite_all"을 골라라.
- JSON 외에는 아무것도 출력하지 마라."""

# (요청, 정답 op) — 20개. 정답은 사람이 미리 적어둔다.
ROUTER_TEST_SET = [
    ("버튼 색 노란색으로 바꿔줘", "set_theme"),
    ("참여 단계 지워줘", "remove_block"),
    ("혜택 하나 더 넣어줘", "append_item"),
    ("전체적으로 톤을 밝게 해줘", "rewrite_all"),
    ("두 번째 버튼 바꿔줘", "unclear"),
    ("CTA 문구를 '지금 신청하기'로", "set_field"),
    ("제목 굵기를 더 두껍게", "set_theme"),
    ("자주 묻는 질문 영역 추가해줘", "add_block"),
    ("카운트다운 빼줘", "remove_block"),
    ("이 페이지 전체적으로 다시 만들어줘", "rewrite_all"),
    ("혜택 목록에 쿠폰 항목 추가", "append_item"),
    ("hero 제목 바꿔줘", "set_field"),
    ("더 예쁘게 해줘", "set_theme"),   # apply_preset도 set_theme 계열로 채점
    ("이거 좀 손봐줘", "unclear"),
    ("탭 영역 새로 넣어줘", "add_block"),
    ("배경색 바꿔줘", "set_theme"),
    ("참여방법 3단계로 늘려줘", "append_item"),
    ("전부 다 새로 써줘", "rewrite_all"),
    ("아까 그거 다시 원래대로", "unclear"),
    ("CTA 링크는 그대로 두고 문구만", "set_field"),
]


def _make_case(i, request, expected_op):
    def _check(raw, html):
        import json
        try:
            parsed = json.loads(raw.strip())
        except Exception:
            return ["router_bad_json"]
        got = parsed.get("op")
        if got != expected_op:
            return [f"router_wrong_{expected_op}_got_{got}"]
        return []

    return Case(f"R{i}", f"라우팅_{expected_op}", "R", SYSTEM_ROUTER, request,
                "router", extra_check=_check)


CASES = [_make_case(i, req, op) for i, (req, op) in enumerate(ROUTER_TEST_SET, 1)]


def self_check():
    assert len(CASES) == 20
    for c in CASES:
        assert c.group == "R"
        assert c.mode == "router"
        assert c.extra_check is not None
    # 정답 op 집합이 실제 오퍼레이션 체계와 어긋나지 않는지 확인
    valid_ops = {"set_field", "append_item", "remove_block", "add_block",
                 "set_theme", "rewrite_all", "unclear"}
    for _, op in ROUTER_TEST_SET:
        assert op in valid_ops, f"정답 op '{op}'가 유효한 오퍼레이션 집합에 없음"
