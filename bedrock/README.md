# bedrock/ — Bedrock LLM-as-a-Judge (독립 실행)

`docs/bedrock/v2-pipeline.md`가 제안한 "이미 나온 모델 출력을 Bedrock이 별도로
채점한다"(§10~§11, BYO Model Response)를 구현한 것이다. **생성기가 아니라
채점기**다 — 페이지를 만들지 않고, `outputs/`에 이미 있는 결과물을 읽어서
점수만 매긴다.

## 0. 먼저 알아야 할 것 — 분석 결과 요약

이 폴더를 설계하기 전에 `docs/bedrock/v2-pipeline.md`, `docs/architect/project-architect.md (HTML 파트)`,
`docs/architect/project-architect.md (JSON 파트)` 세 문서와, 그 문서들이 가리키는 실제 코드
(`newvent-backend/src/main/java/com/newvent/registry/*.java`,
`model-benchmark/versions/v8/*`)를 대조했다. 세 가지가 중요하다.

### 1-1 `data-behavior` 검증(`BehaviorValidator`)도 실제 구현이 없다

`project-architect.md (HTML 파트)` §7~§12, §27이 설명하는 Behavior 검증 로직은
Java 쪽에 `BehaviorValidator.java` 자체가 없다. `judge/deterministic_html.py`의
`validate_behavior()`는 문서의 allowlist(§11)만 근거로 새로 작성했다.

## 1-2. 폴더 구조 (`v2-pipeline.md` §31 그대로)

```
bedrock/
├── datasets/                  테스트 케이스 (JSONL, id별 prompt/requirements)
│   ├── generation.jsonl       TC-GEN-* 8건       — §6
│   ├── edit.jsonl             TC-EDIT-* 6건      — §7 (before를 html/json 둘 다 담음)
│   └── behavior.jsonl         TC-BEHAVIOR-* 5건  — §8
├── outputs/                   ★ 이미 생성된 모델 출력을 여기 놓는다(BYO)
│   ├── json/<id>.json
│   └── html/<id>.html
├── results/                   judge 실행 결과 + 요약표
│   ├── json/<id>.json
│   ├── html/<id>.json
│   └── summary_{json,html}.md
├── judge/                     독립 judge 스크립트 (아래 §2)
├── generate_html_outputs.py   HTML 출력을 채우는 편의용 생성기 (아래 §1-1, judge/와 별도)
├── requirements.txt
└── README.md                  (이 파일)
```

`outputs/`는 `judge/`가 채우지 않는다 — 로컬 Qwen이든, `versions/v8`이
Bedrock으로 생성한 결과든, `generate_html_outputs.py`로 만든 결과든, 사람이
손으로 만든 결과든, **파일명을 테스트 케이스 id에 맞춰**(`TC-GEN-001.html`처럼)
넣어주면 된다.

**데이터셋이 재는 축** (군더더기 없이, `versions/v1~v8`에서 실제로 실패가
나왔던 축만 골랐다):

| 파일 | 케이스 | 재는 것 |
| --- | --- | --- |
| `generation.jsonl` | TC-GEN-001~003 | 기본 생성(날짜/혜택 명시) |
| | TC-GEN-004 | 선택 블록(`steps`) 생략 요청 준수 — v8 G2 |
| | TC-GEN-005 | **환각 방어** — 날짜/혜택 미지정 시 지어내지 않는가(D군 취지) |
| | TC-GEN-006 | 혜택/단계 4개(상한) 경계값 |
| | TC-GEN-007 | 대상·CTA 문구 특정 요청 |
| | TC-GEN-008 | 정보 최소 프롬프트 — placeholder 없이 문장을 통째로 빼는가 |
| `edit.jsonl` | TC-EDIT-001·002 | 슬롯(`period`/`cta-link`) 보존 — v8 E1·E2 |
| | TC-EDIT-003 | 구조 늘리기(항목 추가) — v8 E3 |
| | TC-EDIT-004 | **구조 줄이기(항목 삭제)** — v1~v8 전 버전에서 JSON 패치가 0%였던 축 |
| | TC-EDIT-005 | 항목 수 불변, 문구만 다듬기 |
| | TC-EDIT-006 | **의도치 않은 변경 감지** — 건드리지 말라고 한 필드가 바뀌는가 |
| `behavior.jsonl` | TC-BEHAVIOR-001~003 | api-request/복합 액션, open-modal, close-modal |
| | TC-BEHAVIOR-004 | scroll |
| | TC-BEHAVIOR-005 | redirect — 외부 URL로 바꿔치기하면 잡히는가(§12 Allowlist) |

### 1-1. `generate_html_outputs.py` — HTML 전용 편의 생성기 (judge와 분리)

`judge/`는 의도적으로 생성기가 아니다(§2). 그런데 judge를 돌리려면
`outputs/html/<id>.html`이 먼저 있어야 하므로, **HTML 방식만** 채워주는
작은 생성기를 `judge/` 밖에 따로 뒀다 — 채점 로직과 섞이지 않게.

실제 백엔드 프롬프트(`registry.PromptBuilder.generate()`/`edit()`)를
`deterministic_html.py`의 Block 레지스트리에서 그대로 재구성해서 쓴다.
**generation·edit만 지원한다** — behavior는 `data-behavior`를 만들라고
시키는 백엔드 프롬프트 자체가 없어서(§0-②) 자동 생성할 근거가 없다.

```bash
# 프롬프트만 확인(호출 없음)
python bedrock/generate_html_outputs.py --dataset generation --dry-run

# 모델 하나만
export BEDROCK_REGION=us-east-1
python bedrock/generate_html_outputs.py --dataset generation --model gemma

# 모델 여러 개를 한 번에 — versions/v8 FIRST_PASS와 같은 4종 비교
python bedrock/generate_html_outputs.py --dataset generation --models qwen,oss120,gemma,haiku
python bedrock/generate_html_outputs.py --dataset edit --models qwen,oss120,gemma,haiku
```

`--model`/`--models` 별칭: `gemma`(단일 실행 시 기본값 — `versions/v8` §6 결론:
100% 통과·최저가) · `qwen` · `oss120` · `haiku`.

### 1-1-1. 출력이 너무 빈약할 때

기본 프롬프트만으로는 모델이 혜택 2개·짧은 문장 정도로 끝내는 경우가 많다
(실측: `qwen`이 TC-GEN-001을 혜택 2개·문장 하나짜리 히어로로 생성). 두 가지로
분리해서 대응한다 — **시스템 프롬프트(`PromptBuilder.generate()` 미러)는
절대 바꾸지 않는다.** 그걸 바꾸면 더 이상 "실제 백엔드가 낼 결과"를 채점하는
게 아니게 된다(§0-①과 같은 이유).

1. **요청(`prompt`)을 더 구체적으로** — `datasets/generation.jsonl`의
   TC-GEN-001·002·003·006·007은 "혜택마다 이유를 한 문장씩", "각 단계를
   구체적으로 설명해줘"처럼 분량을 요구하도록 이미 손봐뒀다. 진짜 사용자도
   이렇게 자세히 요청할 수 있으므로 시스템 프롬프트 위반이 아니다.
   (TC-GEN-004·005·008은 일부러 그대로 뒀다 — 그 셋은 "짧게/모호하게 줬을 때"를
   재는 케이스라 풍부하게 만들면 애초에 재려던 것이 없어진다.)
2. **`--max-tokens`로 상한만 올리기** — 기본값 1536은 백엔드 실제 캡과
   동일하다(`docs/bedrock/v1-migration.md` §8-2가 이미 "실제 풀페이지는
   1,985~2,443토큰 필요, 1536은 부족"이라고 실측 지적한 값). 더 큰 출력을
   시험해보고 싶을 때만 명시적으로 올린다:
   ```bash
   python bedrock/generate_html_outputs.py --dataset generation --model qwen \
       --overwrite --max-tokens 2560
   ```
   기본값을 조용히 올리지 않는 이유는 그러면 judge가 "실제 서비스에서는 절대
   안 나오는 분량"을 채점하게 되기 때문이다.

**모델별로 파일이 자동으로 나뉜다** — `outputs/html/TC-GEN-001__gemma.html`,
`TC-GEN-001__haiku.html`처럼 `<id>__<모델별칭>.html`로 저장되어 서로
덮어쓰지 않는다. `run_judge.py`가 `<id>__*.html` 패턴을 전부 찾아서
**모델이 몇 개든 자동으로 전부 채점**하므로(`--model` 지정 불필요),
`aggregate.py`가 `versions/v8`의 "모델 × 케이스" 표와 같은 형식으로
모델 간 비교표를 만들어준다(§4 참고).

### 1-2. 이 컴퓨터의 기본 AWS 계정이 내 계정이 아닐 때 — `--profile`

`generate_html_outputs.py`·`run_judge.py` 둘 다 boto3가 기본으로 찾는
자격증명(보통 `~/.aws/credentials`의 `[default]`, 또는 `AWS_ACCESS_KEY_ID` 등
환경변수)을 그대로 쓴다. **그 기본값이 내 계정이 아니라면** 그걸 바꾸지 말고
`--profile`로 내 프로필만 지정한다.

```bash
# 1) 내 자격증명을 별도 프로필로 등록(한 번만)
aws configure --profile my-account
# AWS Access Key ID / Secret / 기본 region(뭘 넣어도 상관없음 — 아래 --region이 우선)을 입력

# 2) 그 프로필로만 실행 (전역 기본값은 그대로 둠)
python bedrock/generate_html_outputs.py --dataset generation --model gemma --profile my-account
python bedrock/judge/run_judge.py --dataset generation --format html --profile my-account
# 또는 이 셸에서만: export BEDROCK_PROFILE=my-account (그러면 --profile 생략 가능)
```

`--region`도 마찬가지로 계정 기본 리전(`aws configure list`)과 별개로 동작한다
— `us-east-1`이 기본값이다(Bedrock의 Anthropic 계열 모델은 서울 리전에 없다,
`versions/v8` README 참고).

## 2. `judge/` — 독립 실행 판정기

| 파일 | 역할 | 근거 |
| --- | --- | --- |
| `deterministic_html.py` | HTML 구조·정화(sanitize)·슬롯·behavior allowlist 검증 | `Block.java`/`BlockValidator.java`/`Slot.java` 1:1 미러 |
| `deterministic_json.py` | Page Schema·Modification Command 검증 | `project-architect.md (JSON 파트)` 스펙만 근거(§0-① 참고, spec-only) |
| `rubric.py` | Judge 프롬프트(0~5점 척도) + 응답 파싱 | `v2-pipeline.md` §13~§22 |
| `bedrock_client.py` | Bedrock Converse API 호출 1개 함수(`judge()`) | `versions/v8/provider.py`의 실측 검증된 호출 형태를 재사용(단, import는 안 함) |
| `run_judge.py` | 위 넷을 엮는 CLI 진입점 | `v2-pipeline.md` §26 이중 평가 구조 |
| `aggregate.py` | 결과 집계 → 마크다운 표 | `v2-pipeline.md` §27·§29 |

**"독립적"의 의미** — 이 6개 파일 + 표준 라이브러리 + `boto3`/`bs4`만 있으면
돈다. `base/`, `versions/v8/`, `playground/`를 import하지 않는다. 생성기가
아니므로 어떤 provider로 만든 출력이든 채점 대상이 될 수 있다.

## 3. 실행

```bash
pip install -r bedrock/requirements.txt

# 0) 네트워크 호출 없이 로직만 검증(가장 먼저 할 것 — v8과 같은 관례)
python bedrock/judge/run_judge.py --self-check

# 1) 이미 만든 출력이 outputs/html/TC-GEN-001.html 처럼 있다면
export BEDROCK_REGION=us-east-1
export BEDROCK_JUDGE_MODEL=sonnet        # 별칭(sonnet/haiku/gemma) 또는 실제 모델 ID
python bedrock/judge/run_judge.py --dataset generation --format html

# 2) 비용 없이 배선만 (Judge 응답 자리에 dry_run 표시만 채움)
python bedrock/judge/run_judge.py --dataset generation --format html --dry-run

# 3) 수정(edit) 평가 — datasets/edit.jsonl의 before 상태와 비교
python bedrock/judge/run_judge.py --dataset edit --format html

# 4) Behavior 시나리오
python bedrock/judge/run_judge.py --dataset behavior --format html

# 5) JSON 방식 — ⚠ §0-①. outputs/json/*.json은 project-architect.md (JSON 파트)
#    스펙으로 별도 생성한 Page Schema여야 한다(이 폴더가 만들지 않는다)
python bedrock/judge/run_judge.py --dataset generation --format json

# 비용 절약 (methodology.md·v8과 같은 원칙 — 싼 것부터, 개수 제한)
python bedrock/judge/run_judge.py --dataset generation --format html --limit 1
```

Judge 모델 별칭(`bedrock_client.JUDGE_MODEL_ALIASES`, `versions/v8/provider.py`의
가격표에서 발췌): `sonnet`(기본, 채점용 상위 모델) · `haiku` · `gemma`.
**Judge는 평가 대상 모델과 분리해서 고정**해야 채점 기준이 흔들리지 않는다 —
`versions/v8`이 haiku/gemma/qwen을 "평가 대상"으로 부르는 것과 이 폴더가
`sonnet`을 "심판"으로 부르는 것은 서로 다른 역할이다.

## 4. 결과 형식 (`v2-pipeline.md` §30)

`results/{json,html}/<id>__<모델>.json` (모델을 지정 안 하고 단일 파일로
채점했다면 `<id>.json`):

```json
{
  "testCaseId": "TC-GEN-002",
  "model": "gemma",
  "format": "html",
  "category": "generation",
  "html": {
    "requirement_accuracy": 5,
    "content_accuracy": 4,
    "rationale": "...",
    "validation": true,
    "hard_ok": true,
    "model_fails": [],
    "pipeline_fails": [],
    "hard_fails": [],
    "soft_fails": [],
    "sanitize_damaged": false,
    "spec_only": false
  },
  "judge_meta": {"provider": "...", "input_tokens": 0, "output_tokens": 0, ...}
}
```

`model_fails`/`pipeline_fails`/`sanitize_damaged`는 `versions/v8` README §1-②의
구분을 그대로 따른다 — **정화(sanitize) 전에도 실패하면 모델 탓, 정화
후에만 생기면 파이프라인(정화 로직) 탓**이다. 이 구분이 없으면 정화 버그를
모델 탓으로 돌리는 오판이 생긴다(v8이 실측으로 확인한 문제 — href="#" 소실,
data-slot 소실).

### 4-1. Soft vs Hard 실패 — 이건 Judge가 아니라 코드가 나눈다

`base/checks.py`의 `SOFT_FAILS = {"code_fence", "extra_text"}` /
`base/engine.py`의 `hard_ok`·`all_ok` 관례를 그대로 옮긴 것이다.

| 필드 | 뜻 |
| --- | --- |
| `validation` (= all_ok) | 하드+소프트 실패 **0건**, 완전히 깨끗한 출력 |
| `hard_ok` | code_fence·extra_text 같은 형식적 흠은 무시하고, **구조/계약 위반이 없는가** |
| `hard_fails` / `soft_fails` | 위 둘을 실제로 가른 목록 |

**왜 하드/소프트를 코드가 나누고 Judge에게 안 맡기는가** —
`docs/bedrock/v2-pipeline.md` §36.3("Judge에게 구조 검증을 전부 맡기지 않는다")과
같은 이유다. "코드펜스로 감쌌는가"는 판단이 필요 없는 사실이라 고정된 집합
(`deterministic_html.SOFT_FAILS`/`deterministic_json.SOFT_FAILS`)으로 코드가
결정하고, Judge(LLM)는 여기 관여하지 않는다 — Judge의 점수(`requirement_accuracy`
등)는 순수하게 의미 판단에만 쓴다.

**읽는 법** — `hard_ok`인데 `validation`(all_ok)만 `false`인 케이스가 있다면,
그건 실제로 깨진 게 아니라 "코드블록으로 감쌌다"처럼 서버가 어차피 정리해줄
사소한 흠 하나가 남아 있다는 뜻이다. 모델 비교의 주지표는 `hard_ok`로 보고,
`validation`(all_ok)은 "얼마나 깔끔하게 지시를 따르는가"의 보조 지표로 본다
— `docs/bedrock/v1-migration.md` §6의 "완성도(%) = all_ok"와 같은 관례다.

`"model"` 필드는 `aggregate.by_model()`이 그룹핑 키로 쓴다 — 모델을 여러 개
돌렸으면 `summary_<format>.md`에 전체 합계 표 아래 "모델 N종 비교" 표가
자동으로 붙는다(`versions/v8`의 "모델 × 케이스" 표와 같은 축, `all_ok`/`hard_ok`
둘 다 표시).

`python bedrock/judge/aggregate.py`를 따로 돌리면 `results/summary_<format>.md`를
다시 생성한다.

## 5. 앞으로 필요한 것 (이 폴더가 하지 않은 일)

1. **JSON 방식 생성기가 없다.** `project-architect.md (JSON 파트)`의 Page Schema를
   실제로 만들게 하려면 `PromptBuilder.generate()`에 대응하는 JSON 전용
   프롬프트를 새로 작성해야 한다(백엔드에도, 이 벤치마크에도 아직 없음).
   이게 있어야 `outputs/json/`이 채워지고 §0-①의 "공정 비교"가 비로소
   가능해진다.
2. **S3 업로드·Bedrock Model Evaluation(콘솔 배치잡) 연동은 하지 않았다.**
   `v2-pipeline.md` §5·§32·§33이 언급하는 S3 경로는 옵션으로 남겨뒀다 —
   지금은 로컬 파일(`outputs/`, `results/`)만으로 Converse API를 직접
   호출하는 더 가벼운 경로를 택했다(비용·설정 모두 더 저렴, v8과 같은 판단).
   나중에 배치 규모가 커지면 `datasets/*.jsonl`을 그대로 S3에 올리고
   `results/*.json`을 합치는 식으로 확장할 수 있다.
3. **BehaviorValidator, PageSchema 클래스가 백엔드에 실제로 생기면** 이
   폴더의 `spec_only` 플래그와 관련 주석을 갱신해야 한다 — 그 전까지는
   "문서 스펙 대비 채점"이지 "실제 서버 규칙 대비 채점"이 아니라는 것을
   결과에 항상 표시한다.
