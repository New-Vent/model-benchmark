"""
bedrock_client.py — Bedrock을 "Judge"로만 부르는 독립 클라이언트
====================================================================
`docs/bedrock/v2-pipeline.md` §10~§11의 역할 분리를 그대로 따른다.

    Generator (이미 끝난 일) → 로컬 LLM(Qwen 등) 또는 versions/v8의
                                 Bedrock 생성 모델. 이 파일은 그 결과를
                                 만들지 않는다 — outputs/ 에 이미 있다고
                                 가정한다(BYO Model Response, §11).
    Evaluator/Judge (이 파일) → Bedrock의 별도 모델 호출 하나만 한다.

★ versions/v8/provider.py 를 참고했지만 import 하지 않는다("독립적인
  judge 스크립트" 요청에 따름 — versions/v8 은 버전 고정 폴더다).
  Converse API 호출 형태(boto3 bedrock-runtime, system/messages/
  inferenceConfig)는 동일하게 맞췄다 — 이미 실측으로 검증된 형태이기
  때문이다(provider.py의 Anthropic temperature/top_p 동시 불가 주석 참고).

★ Judge 모델은 기본적으로 "평가 대상 모델보다 더 신뢰할 수 있는 모델"을
  쓴다는 LLM-as-a-Judge 관례에 따라 sonnet 계열을 기본값으로 둔다
  (versions/v8/provider.py의 BEDROCK_MODELS 별칭 표를 그대로 재사용).
  평가 대상이 무엇이든(로컬 Qwen, v8의 haiku/gemma 등) Judge는 별도로
  고정해야 "같은 채점 기준"이 유지된다.
"""

import json
import os
import time

# versions/v8/provider.py의 BEDROCK_MODELS 표에서 그대로 옮김(2026-09-21 실측).
# Judge 용도로 쓸 것만 추렸다 — 별칭이 다르면 이 표를 갱신할 것.
JUDGE_MODEL_ALIASES = {
    "sonnet": "us.anthropic.claude-sonnet-5",
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "gemma": "google.gemma-3-27b-it",
}
DEFAULT_JUDGE_ALIAS = "sonnet"
DEFAULT_REGION = "us-east-1"
JUDGE_MAX_TOKENS = 1024
JUDGE_TEMPERATURE = 0.0  # 채점은 재현 가능해야 한다 — 생성과 달리 다양성이 필요 없다


def resolve_model(name: str) -> str:
    return JUDGE_MODEL_ALIASES.get(name, name)


class JudgeResponse:
    def __init__(self, content, input_tokens, output_tokens, wall_ms, truncated):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.wall_ms = wall_ms
        self.truncated = truncated


class BedrockJudgeClient:
    """Converse API 하나만 쓴다 — 모델 무관 인터페이스라 Judge 모델을
    바꿔도 이 클래스는 그대로다."""

    def __init__(self, model=None, region=None, profile=None):
        import boto3  # 지연 import — dry-run 모드에서는 boto3가 없어도 되게
        self.model = resolve_model(
            model or os.environ.get("BEDROCK_JUDGE_MODEL", DEFAULT_JUDGE_ALIAS))
        self.region = region or os.environ.get("BEDROCK_REGION") or DEFAULT_REGION
        # ★ 이 컴퓨터의 기본 자격증명(~/.aws/credentials의 default)이 내
        #   계정이 아닐 수 있다. 그걸 건드리지 않고 별도 프로필로 지정할
        #   수 있게 한다 — 지정 안 하면 boto3 기본 검색 순서(env var ->
        #   AWS_PROFILE -> default 프로필)를 그대로 따른다.
        self.profile = profile or os.environ.get("BEDROCK_PROFILE") \
            or os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=self.profile) if self.profile else boto3
        self.client = session.client("bedrock-runtime", region_name=self.region)

    def provider_name(self) -> str:
        who = f" profile={self.profile}" if self.profile else ""
        return f"bedrock-judge:{self.model}@{self.region}{who}"

    def _converse(self, system: str, user: str):
        """temperature를 보내되, 이 파라미터 자체를 거부하는 모델이면
        (2026-09 실측: `us.anthropic.claude-sonnet-5` — "`temperature` is
        deprecated for this model") 상한만 남기고 한 번 더 시도한다.

        ★ versions/v8/provider.py가 이미 "Anthropic 모델은 temperature/top_p를
          동시에 못 받는다"는 걸 발견했었는데, sonnet-5는 그보다 더 나가서
          temperature 자체를 안 받는다 — 같은 계열이어도 모델마다 다르므로
          매번 확정적으로 분기하지 않고 오류 문구로 감지해 재시도한다.
        """
        full = {"maxTokens": JUDGE_MAX_TOKENS, "temperature": JUDGE_TEMPERATURE}
        try:
            return self.client.converse(
                modelId=self.model, system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig=full,
            )
        except Exception as e:
            if "temperature" not in str(e).lower():
                raise
            return self.client.converse(
                modelId=self.model, system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": JUDGE_MAX_TOKENS},
            )

    def judge(self, system: str, user: str) -> JudgeResponse:
        t0 = time.time()
        resp = self._converse(system, user)
        wall_ms = int((time.time() - t0) * 1000)
        content = "".join(c.get("text", "") for c in resp["output"]["message"]["content"])
        usage = resp.get("usage", {})
        return JudgeResponse(
            content=content,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            wall_ms=wall_ms,
            truncated=(resp.get("stopReason") == "max_tokens"),
        )


class DryRunJudgeClient:
    """--dry-run 용 — API 호출 없이 배선만 확인한다(0원).
    v8의 MockLlmClient와 같은 목적: 코드 문제와 모델/비용 문제를 분리한다."""

    def provider_name(self) -> str:
        return "dry-run (no bedrock call)"

    def judge(self, system: str, user: str) -> JudgeResponse:
        return JudgeResponse(
            content=json.dumps({"dry_run": True, "rationale": "판정 없음(--dry-run)"}),
            input_tokens=0, output_tokens=0, wall_ms=0, truncated=False,
        )


def make_judge_client(dry_run: bool, model=None, region=None, profile=None):
    if dry_run:
        return DryRunJudgeClient()
    return BedrockJudgeClient(model=model, region=region, profile=profile)


def self_check():
    assert resolve_model("sonnet") == "us.anthropic.claude-sonnet-5"
    assert resolve_model("모르는별칭") == "모르는별칭"  # 원문 모델 ID로 통과시킴

    dry = make_judge_client(dry_run=True)
    r = dry.judge("sys", "user")
    parsed = json.loads(r.content)
    assert parsed["dry_run"] is True
    assert dry.provider_name() == "dry-run (no bedrock call)"

    # temperature를 거부하는 모델(2026-09 실측: sonnet-5)에 대한 재시도 로직.
    # boto3.client() 생성 자체는 네트워크를 안 쓰므로 실제 자격증명 없이도 되고,
    # .client 를 스텁으로 바꿔치기해서 실제 호출 없이 재시도 분기만 검증한다.
    client = BedrockJudgeClient(model="sonnet", region="us-east-1")
    calls = []

    class _FakeBedrock:
        def converse(self, **kwargs):
            calls.append(kwargs["inferenceConfig"])
            if "temperature" in kwargs["inferenceConfig"]:
                raise Exception("ValidationException: `temperature` is deprecated for this model.")
            return {"output": {"message": {"content": [{"text": "ok"}]}}, "usage": {}}

    client.client = _FakeBedrock()
    resp = client.judge("sys", "user")
    assert resp.content == "ok"
    assert len(calls) == 2, f"temperature 거부 시 한 번만 재시도해야 한다: {calls}"
    assert "temperature" in calls[0] and "temperature" not in calls[1]

    print("  [bedrock_client] self_check 통과")


if __name__ == "__main__":
    self_check()
