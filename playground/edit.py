"""
edit.py — 2단계(CLI): 생성된 페이지를 패치(K 방식)로 수정한다.
실제 로직은 core.edit_page()에 있다 — playground/app.py(GUI)도 같은
함수를 쓴다.

여러 번 이어서 실행하면(직전 결과의 .plan.json을 다시 넘기면) 수정이
누적된다 — 실제 서비스의 "생성 → 여러 번 수정" 흐름을 그대로 재현.

지시문 예시 (구조변경/삭제·문구변경·크기변경·테마변경·색깔변경·JS추가):
    구조 추가   "참여 방법을 3단계로 추가해줘"
    구조 삭제   "혜택 항목 중 마지막 하나를 삭제해줘"
    문구 변경   "버튼 문구를 '지금 신청하기'로 바꿔줘"
    크기 변경   "글자 크기를 18px로 키워줘"
    테마 변경   "전체적으로 화사한(vivid) 느낌으로 바꿔줘"
    색깔 변경   "강조 색을 #e0a458로 바꿔줘"
    JS 추가     "투표 기능을 추가해줘. 옵션 3개로"
"""
import argparse
import json
import os
import sys

from backend import DEFAULT_MODEL
from core import edit_page
from util import save_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_path", help="이전 단계의 .plan.json 경로")
    parser.add_argument("instruction", help="예: '혜택 항목 중 마지막 하나를 삭제해줘'")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    with open(args.plan_path, encoding="utf-8") as f:
        current_plan = json.load(f)

    print(f"[edit] {args.model} 호출 중... 지시문: {args.instruction!r}", file=sys.stderr)
    result = edit_page(current_plan, args.instruction, args.model)

    print("\n=== 모델이 낸 patch ===")
    print(json.dumps(result["patch"], ensure_ascii=False, indent=2))

    if result["rejected"]:
        patch = result["patch"]
        print(f"\n모델이 patch를 거부함 (action={patch.get('action')}) "
              f"— question={patch.get('question')!r}, reason={patch.get('reason')!r}")
        return

    session_dir = os.path.dirname(args.plan_path)
    existing = [f for f in os.listdir(session_dir) if f.endswith(".plan.json")]
    step_no = len(existing) + 1
    label = "edit_" + "".join(c if c.isalnum() else "_" for c in args.instruction[:20])
    html_path = save_step(session_dir, step_no, label, result["plan"], result["html"])

    print(f"\n수정 완료 → {html_path}")
    print(f"이어서 수정하려면: python playground/edit.py {html_path.replace('.html', '.plan.json')} \"다음 지시문\"")


if __name__ == "__main__":
    main()
