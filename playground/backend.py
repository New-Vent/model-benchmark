"""
backend.py — playground이 쓸 생성 백엔드를 고른다.

PLAYGROUND_BACKEND=ollama(기본) → base/engine.call (로컬 Ollama)
PLAYGROUND_BACKEND=bedrock      → bedrock/bedrock_call.call (Bedrock)

bedrock/run.py가 engine.call을 통째로 갈아끼우는 것과 달리, 여기는
call() 하나만 옵션에 따라 골라 쓴다 — playground는 versions/*의
run_one()/checks.py 파이프라인을 쓰지 않고 훨씬 가벼운 자체 루프라서
engine 전체를 몽키패치할 필요가 없다.
"""
import os
import sys

PLAYGROUND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(PLAYGROUND_DIR)
BASE_DIR = os.path.join(REPO_DIR, "base")
BEDROCK_DIR = os.path.join(REPO_DIR, "bedrock")

sys.path.insert(0, BASE_DIR)

BACKEND = os.environ.get("PLAYGROUND_BACKEND", "ollama")

if BACKEND == "bedrock":
    sys.path.insert(0, BEDROCK_DIR)
    from bedrock_call import call  # noqa: F401
    DEFAULT_MODEL = os.environ.get(
        "BEDROCK_MODEL_ID",
        "<BEDROCK_MODEL_ID 환경변수를 설정하세요>",
    )
else:
    from engine import call  # noqa: F401
    DEFAULT_MODEL = os.environ.get("PLAYGROUND_MODEL", "qwen2.5:7b")

print(f"[playground] backend={BACKEND} model={DEFAULT_MODEL}", file=sys.stderr)
