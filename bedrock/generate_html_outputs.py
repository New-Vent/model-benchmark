"""
generate_html_outputs.py — HTML 방식 출력을 만들어 outputs/html/ 에 채우는 도우미
====================================================================
`judge/`는 의도적으로 "생성기가 아니라 채점기"다(README §2 "독립적인의 의미").
그런데 judge를 돌리려면 outputs/html/<id>.html 이 먼저 있어야 한다 — 이
스크립트는 그 첫 단계(BYO Model Response, v2-pipeline.md §9·§11)를
채워주는 **편의용** 도구다. judge/ 패키지에 넣지 않고 bedrock/ 바로 아래
둔 이유가 그것이다: 채점 로직과 생성 로직을 같은 파일에서 섞지 않는다.

실제 백엔드가 모델에게 시키는 프롬프트(`registry.PromptBuilder.generate()`
/ `edit()`)를 그대로 재현한다 — README §0-①에서 확인했듯, HTML 방식은
백엔드에 실제 구현이 있으므로 "실제로 서비스가 쓰는 프롬프트"로 만든
출력이라야 judge 결과가 의미 있다. 임의의 프롬프트로 만들면 judge는
그 임의의 프롬프트를 채점하는 것이지 서비스를 채점하는 게 아니다.

지원 범위: generation · edit 뿐이다. **behavior 는 만들지 않는다** —
`data-behavior`를 실제로 만들라고 시키는 백엔드 프롬프트 자체가 없다
(`deterministic_html.BEHAVIOR_IMPLEMENTED_IN_BACKEND = False`). behavior
케이스는 여전히 사람이 직접 outputs/html/TC-BEHAVIOR-*.html 을 만들어
넣어야 한다.

사용법:
    python bedrock/generate_html_outputs.py --dataset generation --model gemma
    python bedrock/generate_html_outputs.py --dataset edit --model gemma
    python bedrock/generate_html_outputs.py --dataset generation --model gemma --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "judge"))  # deterministic_html의 Block 레지스트리를 재사용

import deterministic_html as DH  # noqa: E402

MAX_TOKENS_HTML = 1536  # 백엔드 LlmClient.Mode.HTML(1536)과 동일 — versions/v8/provider.py 참고
# ★ docs/bedrock/v1-migration.md §8-2: 실제 서비스가 필요로 하는 전체 페이지 분량은
#   1,985~2,443토큰인데, 이 1536 캡이 이미 그보다 작다고 실측으로 지적되어 있다.
#   기본값은 백엔드와 똑같이 1536으로 두되(생성 결과가 "실제 서비스와 다른 조건"이
#   되지 않도록), 더 풍부한 출력을 보고 싶으면 --max-tokens 로만 올린다 — 기본값을
#   그냥 올려버리면 judge 결과가 "실제 백엔드에서는 안 나오는 분량"을 채점하게 된다.
TEMPERATURE = 0.2

# versions/v8/provider.py BEDROCK_MODELS 에서 1차 후보로 확인된 것만 옮김.
# v8 §6 결론: gemma가 100% 통과·최저가 — 기본값으로 둔다.
GEN_MODEL_ALIASES = {
    "gemma": "google.gemma-3-27b-it",
    "qwen": "qwen.qwen3-coder-30b-a3b-v1:0",
    "oss120": "openai.gpt-oss-120b-1:0",
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}
DEFAULT_MODEL_ALIAS = "gemma"


def resolve_model(name: str) -> str:
    return GEN_MODEL_ALIASES.get(name, name)


# ══════════════════════════════════════════════════════════════════
#  프롬프트 — registry.PromptBuilder.generate()/edit() 재현
#  (deterministic_html.BLOCKS 하나만 근거로 삼는다 — 사실을 두 곳에 안 적는다)
# ══════════════════════════════════════════════════════════════════

def system_generate() -> str:
    lines = [
        "너는 통신사 이벤트 페이지를 만드는 도우미다.", "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명, 인사말, 마무리 멘트를 붙이지 마라.", "",
        "만들 영역:",
    ]
    for b in DH.LLM_BLOCKS:
        tail = "" if b.required else "  (선택)"
        lines.append(f'- data-block="{b.key}" : {b.desc}{tail}')
        if b.shape:
            lines.append(f"    형태: {b.shape}")
    if DH.SERVER_BLOCKS:
        lines += ["", "만들면 안 되는 영역:"]
        for b in DH.SERVER_BLOCKS:
            lines.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')
    lines += [
        "", "태그를 반드시 쓴다. 맨 텍스트만 두지 마라.", "예:",
        '<section data-block="hero">', "  <h1>여름 데이터 대방출</h1>",
        "  <p>이번 여름 데이터 걱정 없이</p>", "</section>",
        '<section data-block="cta">', '  <a href="#" class="btn">참여하기</a>', "</section>", "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택이나 수치를 만들어내지 마라.",
        "- 대괄호 자리표시자를 절대 남기지 마라. 값을 모르면 그 문장을 아예 빼라.",
        "- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


def system_edit(block_key: str) -> str:
    b = DH.block_of(block_key)
    if b.source == DH.SERVER:
        raise ValueError(f"{block_key} 는 서버 소유입니다. 모델에게 수정시키면 안 됩니다.")
    lines = [
        "너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.", "",
        f'<section data-block="{b.key}"> 영역만 수정해서 그 영역만 출력한다.',
        f"이 영역의 역할: {b.desc}",
    ]
    if b.shape:
        lines.append(f"형태: {b.shape}")
    lines += [
        "", "출력 규칙:",
        f'- <section data-block="{b.key}"> 로 시작해서 </section> 으로 끝난다.',
        "- 다른 영역을 새로 만들지 마라.", "- 코드블록으로 감싸지 마라.", "- 설명을 붙이지 마라.", "",
        "건드리면 안 되는 것:",
        '- data-slot="..." 이 붙은 태그는 지우지 마라. 태그와 속성을 그대로 둔다.',
        "- 그 안의 내용을 채우지 마라. 비어 있으면 비운 채로 둔다. 서버가 채운다.",
        "- data-slot 을 새로 만들지 마라.", "",
        "금지:",
        "- 요청받은 것만 바꿔라. href, class 같은 기존 속성은 그대로 둔다.",
        '- href="#" 는 그대로 둬라. 실제 주소를 만들어 넣지 마라.',
        "- 날짜를 임의로 만들지 마라.", "- 대괄호 자리표시자를 남기지 마라.", "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  Bedrock 호출 (bedrock_client.BedrockJudgeClient와 같은 형태, 생성용 max_tokens)
# ══════════════════════════════════════════════════════════════════

class BedrockGenClient:
    def __init__(self, model, region, profile=None):
        import boto3
        self.model = model
        # ★ 이 컴퓨터의 기본 AWS 자격증명이 내 계정이 아닐 수 있다 — 건드리지
        #   않고 별도 프로필을 지정할 수 있게 한다(bedrock_client.py와 동일 원칙).
        session = boto3.Session(profile_name=profile) if profile else boto3
        self.client = session.client("bedrock-runtime", region_name=region)

    def generate(self, system: str, user: str, max_tokens: int = MAX_TOKENS_HTML) -> str:
        # ★ 일부 모델(2026-09 실측: us.anthropic.claude-sonnet-5)은 temperature
        #   파라미터 자체를 거부한다("`temperature` is deprecated for this
        #   model") — judge/bedrock_client.py와 동일한 이유로 감지 후 재시도한다.
        try:
            resp = self.client.converse(
                modelId=self.model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": TEMPERATURE},
            )
        except Exception as e:
            if "temperature" not in str(e).lower():
                raise
            resp = self.client.converse(
                modelId=self.model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens},
            )
        return "".join(c.get("text", "") for c in resp["output"]["message"]["content"])


def _load_jsonl(path: Path) -> list:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def output_path(case_id: str, model_alias: str) -> Path:
    """모델별로 파일을 분리한다 — 없으면 모델을 여러 개 돌릴 때 서로 덮어쓴다.
    `<id>__<별칭>.html` 형태. 별칭이 없는 옛 방식(`<id>.html`, 단일 모델
    수동 테스트)도 run_judge.py가 계속 읽을 수 있다(하위 호환)."""
    return HERE / "outputs" / "html" / f"{case_id}__{model_alias}.html"


def run_for_model(alias: str, cases: list, dataset: str, region: str, profile: str,
                   overwrite: bool, dry_run: bool, max_tokens: int = MAX_TOKENS_HTML):
    model_id = resolve_model(alias)
    client = None
    if not dry_run:
        client = BedrockGenClient(model_id, region, profile=profile)
        who = f" profile={profile}" if profile else ""
        print(f"\n[generate] model={alias}({model_id}) region={region}{who} "
              f"cases={len(cases)}")

    for case in cases:
        out_path = output_path(case["id"], alias)
        if out_path.exists() and not overwrite:
            print(f"  [skip] {case['id']}__{alias}: 이미 있음 (--overwrite로 다시 생성)")
            continue

        if dataset == "generation":
            system, user = system_generate(), case["prompt"]
        else:  # edit
            system = system_edit(case["target"])
            user = f"{case['prompt']}\n\n{case['before']['html']}"

        if dry_run:
            print(f"\n=== {case['id']} ({alias}) ===\n--- system ---\n{system}\n"
                  f"--- user ---\n{user}\n")
            continue

        t0 = time.time()
        raw = client.generate(system, user, max_tokens=max_tokens)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(raw, encoding="utf-8")
        print(f"  [ok] {case['id']}__{alias} -> {out_path.name} "
              f"({int((time.time()-t0)*1000)}ms, {len(raw)}자)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["generation", "edit"], required=True,
                     help="behavior 는 지원하지 않는다 (docstring 참고)")
    ap.add_argument("--model", default=None, help="별칭 또는 모델 ID 하나만")
    ap.add_argument("--models", default=None,
                     help="쉼표로 여러 개 — 예: qwen,oss120,gemma,haiku "
                          "(versions/v8 FIRST_PASS와 동일한 4종). "
                          "지정하면 --model 은 무시하고 모델별로 파일을 따로 만든다"
                          f"(`<id>__<별칭>.html`). 기본값은 --model 하나(`{DEFAULT_MODEL_ALIAS}`)")
    ap.add_argument("--region", default=os.environ.get("BEDROCK_REGION", "us-east-1"))
    ap.add_argument("--profile", default=os.environ.get("BEDROCK_PROFILE")
                     or os.environ.get("AWS_PROFILE"),
                     help="이 컴퓨터의 기본 AWS 자격증명이 내 계정이 아닐 때 쓸 프로필 이름")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--overwrite", action="store_true", help="이미 있는 outputs 파일도 다시 만든다")
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 어떤 프롬프트가 나갈지만 출력")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS_HTML,
                     help=f"출력 상한(기본값 {MAX_TOKENS_HTML} — 백엔드 실제 캡과 동일). "
                          "docs/bedrock/v1-migration.md 8-2가 실제 풀페이지는 1,985~2,443토큰이 "
                          "필요하다고 지적한 값보다 이미 작으므로, 더 풍부한 출력을 보려면 "
                          "이 값만 올린다(예: --max-tokens 2560). 기본값은 백엔드와 다르게 "
                          "만들지 않는다.")
    args = ap.parse_args()

    aliases = [m.strip() for m in args.models.split(",")] if args.models \
        else [args.model or DEFAULT_MODEL_ALIAS]

    dataset_path = HERE / "datasets" / f"{args.dataset}.jsonl"
    cases = _load_jsonl(dataset_path)
    if args.limit:
        cases = cases[:args.limit]

    if not args.dry_run:
        total_calls = len(aliases) * len(cases)
        print(f"[generate] 모델 {len(aliases)}개 x 케이스 {len(cases)}개 "
              f"= 총 {total_calls}회 Bedrock 호출 예정: {', '.join(aliases)}")

    for alias in aliases:
        run_for_model(alias, cases, args.dataset, args.region, args.profile,
                      args.overwrite, args.dry_run, max_tokens=args.max_tokens)

    if not args.dry_run:
        model_flag = f"--models {args.models}" if args.models else ""
        print(f"\n[generate] 완료. 다음으로:\n"
              f"  python judge/run_judge.py --dataset {args.dataset} --format html --dry-run"
              f"   (0원, 배선 확인)\n"
              f"  python judge/run_judge.py --dataset {args.dataset} --format html"
              f"             (Bedrock Judge 실제 호출 — 모델별로 자동 채점, {model_flag} 불필요)")


if __name__ == "__main__":
    main()
