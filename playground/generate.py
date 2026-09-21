"""
generate.py — 1단계(CLI): J 방식(plan JSON)으로 새 이벤트 페이지를 생성한다.
실제 로직은 core.generate_page()에 있다 — playground/app.py(GUI)도 같은
함수를 쓴다.

사용법:
    python playground/generate.py "설명 문구"
    python playground/generate.py "설명 문구" --model qwen2.5-coder:7b
    PLAYGROUND_BACKEND=bedrock python playground/generate.py "설명 문구"

출력: playground/output/<시각>_gen/01_generate.plan.json 과 .html
      — .html을 브라우저로 그냥 열면 결과를 바로 볼 수 있다.
      다음 단계(edit.py)에서 이 .plan.json 경로를 그대로 넘기면 된다.
"""
import argparse
import sys

from backend import DEFAULT_MODEL
from core import generate_page
from util import new_session_dir, save_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", help="예: '여름 데이터 프로모션 이벤트 페이지를 만들어줘'")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    print(f"[generate] {args.model} 호출 중...", file=sys.stderr)
    result = generate_page(args.prompt, args.model)

    session_dir = new_session_dir("gen")
    html_path = save_step(session_dir, 1, "generate", result["plan"], result["html"])

    print(f"\n생성 완료 → {html_path}")
    print(f"다음 단계: python playground/edit.py {html_path.replace('.html', '.plan.json')} \"수정 지시문\"")


if __name__ == "__main__":
    main()
