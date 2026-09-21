"""
template_loader.py — 실제 제품 템플릿(template/template_1~5.html + event.css)을
playground에서 불러온다.

versions/v4/templates.py(읽기 전용 유틸리티, container()/block_html()/
blocks_of())를 그대로 재사용한다 — v4 폴더 자체를 고치지 않으므로 v4의
재현성에는 영향이 없다(base/registry.py를 직접 고치지 않는 것과는 다른
얘기: 여기는 "가져다 쓰기"지 "바꿔치기"가 아니다).

event.css는 실제 템플릿이 `<link rel="stylesheet" href="./event.css">`로
불러오는 진짜 스타일시트다 — component_library.py의 Tailwind풍 합성
마크업과는 클래스 체계가 완전히 다르므로(`ev-block`/`block-*`/
`benefit-card` 등), 이 로더로 불러온 템플릿을 수정할 때는 (J/K가 아니라)
S 방식 — 블록의 실제 outerHTML을 왕복 편집하는 방식만 의미가 있다
(core.edit_block_direct 참고).
"""
import os
import sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_DIR, "versions", "v4"))

import templates as T  # noqa: E402

TEMPLATE_CSS_PATH = os.path.join(REPO_DIR, "template", "event.css")

TEMPLATE_LABELS = {
    1: "1 — 스포츠 응원",
    2: "2 — 명절 선물",
    3: "3 — 멤버십 감사",
    4: "4 — 플래시 세일",
    5: "5 — 사전예약",
}


def load_event_css() -> str:
    with open(TEMPLATE_CSS_PATH, encoding="utf-8") as f:
        return f.read()


def load_template(template_id: int) -> dict:
    return {
        "html": T.container(template_id),
        "blocks": T.blocks_of(template_id),
        "label": TEMPLATE_LABELS.get(template_id, str(template_id)),
        "theme": T.theme_of(template_id),
        # event.css의 색상/레이아웃 대부분이 "body 또는 상위 요소의
        # theme-* 클래스"에 스코프돼 있다(event.css 상단 주석 참고).
        # container()는 <div class="ev-container">만 반환하고 원본의
        # <body class="theme-sports">는 버리므로, 이 값을 미리보기를
        # 감쌀 때(util.wrap_with_css) body에 다시 붙여야만 템플릿마다
        # 실제 색이 다르게 나온다 — 안 그러면 전부 테마 없는 기본값으로
        # 보여서 5개가 똑같아 보인다(실제로 겪은 버그).
    }
