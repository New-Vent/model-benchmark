"""
provider.py — 백엔드 `infra.llm.LlmClient` 미러 + Bedrock 구현
===============================================================

interface LlmClient { Response chat(Request); String providerName(); }
    Mode.HTML(1536) · Mode.ROUTER(256)
    Response(content, inputTokens, outputTokens, wallMs, truncated)

v8 은 이 모양을 그대로 쓴다. 여기서 통과한 파라미터·모델 ID 를 백엔드
`BedrockClient` 에 그대로 옮기면 된다.

## 왜 base/engine.py 를 안 고치는가

`base/` 는 팀 공용이고 "합의 없이 개인이 고치지 않는다"가 저장소 규칙이다.
게다가 engine 은 Ollama 에 깊게 묶여 있다(캘리브레이션·digest·/api/tags 확인).
v8 은 백엔드 미러라 필요한 게 다르므로 독립 러너를 쓴다 — v1~v7 결과는
그대로 재현 가능한 채로 남는다.

## 실행

    export LLM_PROVIDER=bedrock
    export BEDROCK_REGION=us-east-1          # AWS_REGION 과 별개 (아래 참고)
    BEDROCK_MODEL=qwen   python run_v8.py    # 별칭 또는 모델 ID
    BEDROCK_MODEL=haiku  python run_v8.py

    LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b python run_v8.py   # 대조군
    LLM_PROVIDER=mock python run_v8.py                             # 0원, 배선 확인

쓸 수 있는 별칭은 BEDROCK_MODELS 참고. 전부 2026-09-21 에 실제로 호출해서
되는 것만 남겼다.
"""

import json
import os
import time

# 백엔드 LlmClient.Mode 와 같은 값이어야 한다
MAX_TOKENS = {"html": 1536, "router": 256}

# 백엔드 OllamaClient 의 options (바꾸면 v1~v7 과 조건이 달라진다)
TEMPERATURE = 0.2
TOP_P = 0.9
TOP_K = 40
REPEAT_PENALTY = 1.05


# ── v8 후보 모델 (us-east-1, 2026-09-21 실호출로 확인) ─────────────
#
# ★ 호출 방식이 둘로 갈린다. 섞으면 ValidationException 이 난다.
#     ON_DEMAND          modelId 를 그대로 쓴다
#     INFERENCE_PROFILE  `us.` 접두 프로파일 ID 를 써야 한다
#   `aws bedrock list-foundation-models` 의 inferenceTypesSupported 로 확인한다.
#
# 단가는 us-east-1 온디맨드 기준(입력/출력, 1M 토큰당 USD). 단가순 정렬.
BEDROCK_MODELS = {
    # 별칭              모델 ID                                        입력   출력
    "oss20":   ("openai.gpt-oss-20b-1:0",                             0.07,  0.30),
    "gemma12": ("google.gemma-3-12b-it",                              0.09,  0.29),
    "qwen":    ("qwen.qwen3-coder-30b-a3b-v1:0",                      0.15,  0.60),
    "qwen32":  ("qwen.qwen3-32b-v1:0",                                0.15,  0.60),
    "oss120":  ("openai.gpt-oss-120b-1:0",                            0.15,  0.60),
    "gemma":   ("google.gemma-3-27b-it",                              0.23,  0.38),
    "haiku":   ("us.anthropic.claude-haiku-4-5-20251001-v1:0",        1.00,  5.00),
    "terra":   ("us.openai.gpt-5.6-terra",                            2.20, 13.20),
    "sonnet":  ("us.anthropic.claude-sonnet-5",                       2.00, 10.00),
}

# ★ 일부러 뺀 것
#
#   gpt-5.6-luna ($0.22/$1.32)
#     AWS Marketplace 구독이 필요하다. 실호출하면 이렇게 막힌다:
#       AccessDeniedException: ... not authorized to perform the required AWS
#       Marketplace actions (aws-marketplace:ViewSubscriptions, aws-marketplace:Subscribe)
#     IAM 에 저 두 액션을 주면 Bedrock 이 알아서 구독을 걸고 2분 뒤 풀린다.
#     그런데 `aws-marketplace:Subscribe` 는 **계정에 유료 구독을 거는 권한**이라
#     벤치마크용 사용자에게 주기엔 과하다. 게다가 같은 OpenAI 계열인
#     gpt-oss-120b 가 더 싸고($0.15/$0.60) 구독 없이 바로 된다 — 대표는 그쪽으로.
#     (같은 us.openai.* 인 terra 는 구독 없이 호출된다. 계열 전체가 막힌 게 아니다)
#
#   gpt-oss-safeguard-20b / 120b
#     콘텐츠 안전성 **분류** 전용 모델이다. HTML 생성·수정에 쓸 물건이 아니라
#     단가가 싸다고 넣으면 엉뚱한 걸 재게 된다.


# ★ BEDROCK_MODELS 는 **조회표**이지 실행 목록이 아니다.
#   ID 와 단가를 한 번 알아내는 게 번거로워서(온디맨드/프로파일 구분, 리전별
#   유무, Marketplace 구독) 확인한 것을 전부 적어둔 것뿐이다. 여기 있다고
#   호출되지 않는다 — 안 쓰면 0원이다.
#
#   1차로 실제 돌릴 건 이 넷이다. 계열마다 하나씩, 단가 범위를 고루 덮는다.
FIRST_PASS = ["qwen", "oss120", "gemma", "haiku"]
#     qwen    우리 데이터가 가장 강하게 지지 (qwen2.5-coder 가 v7 에서 10/10)
#     oss120  qwen 과 **단가가 똑같다**. 같은 값에 다른 계열 — 공짜 비교
#     gemma   gemma3:4b 실패가 체급 문제였는지 계열 문제였는지 가른다
#     haiku   위 셋이 라우터에서 무너질 때의 상위 대조군
#
#   나머지는 대기다. qwen32(coder 대신 dense), gemma12(더 싼 체급),
#   oss20(최저가), sonnet·terra(상위 승급용) — 1차 결과를 보고 필요할 때만.


def resolve_model(name: str) -> str:
    """별칭이면 모델 ID 로, 아니면 그대로 돌려준다."""
    return BEDROCK_MODELS.get(name, (name,))[0]


def price_of(model_id: str):
    """(입력단가, 출력단가) — 모르는 모델이면 None"""
    for mid, pin, pout in BEDROCK_MODELS.values():
        if mid == model_id:
            return pin, pout
    return None


class Response:
    """LlmClient.Response 이식 — 토큰 수를 반드시 담는다(비용 추적)."""

    def __init__(self, content, input_tokens, output_tokens, wall_ms, truncated):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.wall_ms = wall_ms
        self.truncated = truncated

    def __repr__(self):
        return (f"Response({len(self.content)}자, in={self.input_tokens}, "
                f"out={self.output_tokens}, {self.wall_ms}ms, trunc={self.truncated})")


# ── Bedrock ───────────────────────────────────────────────────────
class BedrockClient:
    """Converse API — 모델 무관 인터페이스.

    ★ bedrock-runtime 을 쓴다 (bedrock-mantle 아님).
      Converse 는 modelId 만 바꾸면 Claude·Nova·Llama 가 같은 코드로 돌아간다.
      우리는 여러 모델을 같은 케이스로 비교해야 하므로 이쪽이 맞다.

    ★ 교차 리전 추론
      서울(ap-northeast-2) Pricing API 에 Anthropic SKU 가 안 보였다.
      `aws bedrock list-inference-profiles --region ap-northeast-2` 로 확인해서
      프로파일 ID(apac.anthropic...)가 나오면 BEDROCK_MODEL 에 그걸 넣는다.
    """

    # ★ 계정 기본 리전과 Bedrock 리전을 분리한다.
    #   팀 계정 기본값은 서울(ap-northeast-2)인데 거기엔 Anthropic 모델이 없다.
    #   AWS_REGION 을 건드리면 다른 AWS 작업까지 영향을 받으므로 Bedrock 전용
    #   변수를 따로 둔다. 지연 차이(0.2초)는 이 워크로드에서 무의미하다.
    DEFAULT_REGION = "us-east-1"

    def __init__(self, model=None, region=None):
        import boto3  # 여기서 import — 다른 provider 쓸 때 boto3 없어도 돌게
        self.model = resolve_model(
            model or os.environ.get("BEDROCK_MODEL", "qwen"))
        self.region = region or os.environ.get("BEDROCK_REGION") or self.DEFAULT_REGION
        if self.region.startswith("ap-northeast-2"):
            print("  ⚠ 서울 리전에는 Anthropic 모델 가격 SKU가 없습니다. "
                  "BEDROCK_REGION 을 us-east-1 등으로 두세요.")
        self.client = boto3.client("bedrock-runtime", region_name=self.region)

    def provider_name(self):
        return f"bedrock:{self.model}@{self.region}"

    def chat(self, system, user, mode="html", seed=None):
        max_tokens = MAX_TOKENS[mode]
        t0 = time.time()
        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": TEMPERATURE,
                "topP": TOP_P,
            },
        )
        wall_ms = int((time.time() - t0) * 1000)

        content = "".join(
            c.get("text", "") for c in resp["output"]["message"]["content"])
        usage = resp.get("usage", {})
        return Response(
            content=content,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            wall_ms=wall_ms,
            # ★ 상한에 걸려 잘렸나 — 안 보면 잘린 HTML 을 정상으로 받는다
            truncated=(resp.get("stopReason") == "max_tokens"),
        )


# ── Ollama (대조군) ───────────────────────────────────────────────
class OllamaClient:
    """백엔드 OllamaClient 미러. Bedrock 결과를 로컬과 견주려고 남겨둔다."""

    def __init__(self, model=None, base_url=None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.base_url = base_url or os.environ.get(
            "OLLAMA_HOST", "http://localhost:11434")

    def provider_name(self):
        return f"ollama:{self.model}"

    def chat(self, system, user, mode="html", seed=None):
        import requests
        options = {
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
            "repeat_penalty": REPEAT_PENALTY,
            "num_predict": MAX_TOKENS[mode],
        }
        if seed is not None:
            options["seed"] = seed
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": "10m",
            "options": options,
        }
        if mode == "router":
            body["format"] = "json"

        t0 = time.time()
        r = requests.post(f"{self.base_url}/api/chat", json=body, timeout=900)
        r.raise_for_status()
        data = r.json()
        wall_ms = int((time.time() - t0) * 1000)

        return Response(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            wall_ms=wall_ms,
            truncated=(data.get("done_reason") == "length"),
        )


# ── Mock (0원) ────────────────────────────────────────────────────
class MockLlmClient:
    """배선 확인용 — **완벽한 모델**을 흉내 낸다.

    ★ 일부러 "정답만 내는 모델"로 만들었다.
      그래야 `LLM_PROVIDER=mock` 실행에서 **남는 실패가 전부 파이프라인 탓**이
      된다. 모델이 완벽한데도 실패가 뜬다면 그건 정화·검증 쪽 문제다 —
      API 비용 0원으로 그걸 먼저 잡으라고 두는 장치다.

    수정 요청에는 user 에 붙어 온 원본 블록을 그대로 돌려준다
      = "아무것도 안 바꾼 모델". 구조·슬롯은 온전하므로, 여기서 뜨는 실패는
        (a) 요청 미반영(request_not_applied) — 예상된 것이고
        (b) 정화 손상 — ★ 이게 우리가 보려는 것
    """

    def provider_name(self):
        return "mock"

    def chat(self, system, user, mode="html", seed=None):
        if mode == "router":
            content = json.dumps(_mock_route(user), ensure_ascii=False)
        elif "영역만 수정해서" in system:
            # user 끝에 붙어 온 원본 블록을 그대로 돌려준다
            s = user.find("<section")
            content = user[s:] if s >= 0 else ""
        else:
            content = (
                '<section data-block="hero"><h1>여름 데이터 대방출</h1><p>소개</p></section>'
                '<section data-block="benefits"><ul><li>A</li><li>B</li></ul></section>'
                '<section data-block="steps"><ol><li>1</li><li>2</li></ol></section>'
                '<section data-block="cta"><a href="#" class="btn">참여하기</a></section>'
            )
        return Response(content, len(system) // 4, len(content) // 4, 1, False)


def _mock_route(user):
    """정답 라우팅을 흉내 낸다 — 케이스 문구에 맞춘 최소 규칙."""
    u = user
    if "없는데 새로 넣어" in u:
        op = "ADD"
    elif "빼줘" in u or "없애줘" in u:
        op = "DELETE"
    elif "크고" in u or "빨갛게" in u:
        op = "STYLE"
    else:
        op = "EDIT"

    if "혜택" in u:
        target = "benefits"
    elif "참여 방법" in u or "단계" in u:
        target = "steps"
    elif "유의사항" in u:
        target = "notices"
    elif "버튼" in u:
        target = "cta"
    else:
        target = "hero"
    return {"op": op, "target": target}


def make_client(name=None):
    name = (name or os.environ.get("LLM_PROVIDER", "mock")).lower()
    if name == "bedrock":
        return BedrockClient()
    if name == "ollama":
        return OllamaClient()
    if name == "mock":
        return MockLlmClient()
    raise SystemExit(f"모르는 provider: {name} (bedrock | ollama | mock)")


def self_check():
    c = MockLlmClient()
    r = c.chat("sys", "user", mode="html")
    assert r.content.startswith("<section"), r.content[:40]
    assert MAX_TOKENS == {"html": 1536, "router": 256}, "백엔드 Mode 와 어긋남"

    # 별칭 · 단가 — run_v8 이 요약에서 price_of 를 부른다
    assert resolve_model("qwen") == "qwen.qwen3-coder-30b-a3b-v1:0"
    assert resolve_model("qwen.qwen3-32b-v1:0") == "qwen.qwen3-32b-v1:0"  # 통과시킴
    assert price_of("google.gemma-3-27b-it") == (0.23, 0.38)
    assert price_of("모르는모델") is None
    assert "luna" not in BEDROCK_MODELS, "Marketplace 구독이 필요해 뺐다 (위 주석)"
    assert all(a in BEDROCK_MODELS for a in FIRST_PASS), FIRST_PASS

    # 프로파일 전용 모델은 `us.` 가 붙어 있어야 한다 — 빼면 ValidationException
    for alias in ("haiku", "sonnet", "terra"):
        assert BEDROCK_MODELS[alias][0].startswith("us."), alias
    print(f"  [provider] self_check 통과 — Bedrock 모델 {len(BEDROCK_MODELS)}종")


if __name__ == "__main__":
    self_check()
