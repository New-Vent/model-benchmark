# v2

J(조합 계획) · K(패치) · CHAIN(생성→그 결과를 실제로 패치) 군.
v1에서 보류했던 **출력 방식 J·K**를 실제로 재는 버전입니다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md), 공통 코드는 [`base/`](../../base/)에 있습니다.

## v1에서 무엇이 달라졌나

| | v1 | v2 |
| --- | --- | --- |
| 군 | D · E · JS · N · S · C · R | **J · K · CHAIN** |
| LLM이 내는 것 | HTML 본문 (N·S) | **JSON** — 조합 계획(J) / 패치 오퍼레이션(K) |
| HTML을 만드는 주체 | LLM | **서버** (`registry.render_plan` — 태그는 전부 우리 것) |
| 출력 강제 | 프롬프트의 형태 규칙 | **JSON Schema** (`build_plan_json_schema` / `build_patch_json_schema`) |

v1과 **케이스·채점이 다르므로 결과 CSV를 섞지 않습니다.** J1↔S1처럼 `pair`로 묶인
케이스만, 같은 요청 문구를 쓴다는 전제 아래 수동으로 비교합니다.

> ⚠ J군의 요청 문구(P1/P2/P8/P9)는 v1 `cases_ns.py`와 **글자 그대로 같아야** pair 비교가
> 성립합니다. 두 파일이 서로 다른 버전 폴더에 있어 import로 묶여 있지 않으니,
> 프롬프트를 고칠 때는 반드시 `versions/v1/cases_ns.py`와 `versions/v2/cases_j.py`를
> 둘 다 확인하세요.

## 이 버전의 조건

파라미터·시드·모델은 v1과 동일합니다 (`base/engine.py`, 개인이 수정 금지).

```python
BASE_OPTIONS = {"temperature": 0.2, "top_p": 0.9, "top_k": 40,
                "repeat_penalty": 1.1, "num_ctx": 8192}
NUM_PREDICT  = {"html": 1536, "plan": 512, "patch": 256, "router": 128}
KEEP_ALIVE   = "30m"
SEEDS        = [42, 43, 44, 45, 46]        # 반복 5회
```

| 군 | 케이스 | 무엇을 재나 |
| --- | --- | --- |
| J | 4개 (J1 · J2 · J8 · J9) | 신규 생성을 **조합 계획 JSON**으로 냈을 때의 성공률. v1 S1·S2·S8·S9와 같은 요청 문구 |
| K | 10개 (K1~K10) | 고정 baseline 위의 **패치**. 짧은 문서(K1~K6, 약 370자) 대 긴 문서(K7~K10, 약 590자) |
| CHAIN | 1개 (CHAIN1) | J가 **실제로 만들어낸** 계획을 K가 이어받아 패치. 생성이 실패하면 `chain_blocked_by_generation_failure`로 기록하고 2단계는 돌리지 않음 |

케이스 15개 × 5회.

### ⚠ `NUM_PREDICT["plan"]=512` · `["patch"]=256`가 J·K에 구조적으로 불리함

S/N군(HTML 직접생성)은 `NUM_PREDICT["html"]=1536`을 받는데, J는 512, K는 256만 받습니다.
JSON은 필드명·따옴표·`"type"/"variant"` 같은 스키마 식별자를 매번 다시 써야 해서 **같은
분량의 내용이라도 HTML보다 원래 토큰이 더 필요한 포맷**인데, 예산은 오히려 1/3~1/6밖에
안 됩니다.

실측(윤기=cuda, 주호=cpu 두 기기, 아래 결과 참고)으로 `truncated` 표시가 붙은 행을 전부
확인한 결과, **11건 전부 `eval_count`가 그 모드의 캡과 정확히 일치**했습니다(J=512 8건,
K=256 1건, 나머지도 512). 즉 지금까지 나온 `bad_json|truncated` 실패는 전부 모델 실력이
아니라 **순수하게 토큰 예산 부족**이었습니다. 가장 내용이 많은 케이스(P9=서술형 다중 지시,
K3=블록 통째로 추가)에서만 정확히 걸린다는 점도 이 해석과 일치합니다.

반면 `missing_reason`(action:"unsupported"로 즉시 거부, eval_count 6~10)이나
`unknown_block_key`(eval_count 53~146, 캡에 한참 못 미침), `placeholder`·`lost_cta`
(eval_count 캡의 절반 이하)는 캡과 무관하게 발생해서 — 이건 예산이 아니라 진짜 모델
능력 차이로 봐도 됩니다.

`NUM_PREDICT`는 `base/engine.py`의 "팀 합의 없이 개인이 수정 금지" 상수라 여기서 임의로
올리지 않았습니다. `docs/methodology.md` §6 규칙상 파라미터 변경은 새 버전 사유이기도
합니다 — **v3에서 `plan`/`patch` 캡 상향(예: 512→900, 256→400)을 논의할 것을 제안합니다.**

## 실행

```bash
export RUNNER="<본인이름>"          # Windows: set RUNNER=<본인이름>
python base/run.py v2              # 이 폴더의 케이스 전부 (J·K·CHAIN)
python base/run.py v2 K            # K군만
python base/run.py v2 J CHAIN      # 여러 군 지정
```

결과는 어느 쪽으로 돌리든 이 폴더 안으로 들어갑니다.

```
versions/v2/result_csv/results_v2_<RUNNER>_<타임스탬프>.csv
versions/v2/result_json/env_v2_<RUNNER>_<타임스탬프>.json
versions/v2/raw_v2/                시도별 원문 (git 제외)
```

`raw_v2/`에는 원본 JSON(`*.txt`)과 함께 **서버가 렌더링한 실제 HTML**
(`*.rendered.html`)이 같이 저장됩니다 — J·K 결과는 이 파일을 브라우저로 열어 확인하세요.

검증만 (LLM 호출 없이):

```bash
python base/run.py v2 --self-check
```

비교표:

```bash
python tools/summarize.py versions/v2
```

## 결과

**2대 실행 (윤기, 주호), 366행.** 아직 exaone3.5:7.8b만 2기기 다 돌았고 qwen2.5:7b·
qwen2.5-coder:7b는 윤기 1기기뿐이라 — 아래 표는 **잠정치**입니다.

### 모델 × 군 — 최종 통과 (재시도 포함)

| 모델 | J | K | CHAIN | 합계 |
| --- | --- | --- | --- | --- |
| exaone3.5:7.8b | 29/40 | 99/100 | 10/10 | **138/150 (92%)** |
| qwen2.5:7b | 18/20 | 42/50 | - | **60/70 (86%)** |
| qwen2.5-coder:7b | 20/20 | 40/50 | - | **60/70 (86%)** |

### 케이스별로 몰려 있는 실패 — 평균 통과율로 보면 안 됨

| 케이스 (요청) | exaone3.5:7.8b | qwen2.5:7b | qwen2.5-coder:7b |
| --- | --- | --- | --- |
| K3 "steps 영역을 **추가**해줘" | 4/5 | 2/5 | 0/5 |
| K9 "steps 영역을 통째로 **삭제**해줘" | 5/5 | 0/5 | 0/5 |
| J8 (긴출력, 상품권 추첨) | 2/5 | 5/5 | 5/5 |

**Qwen 계열(2.5·2.5-coder 둘 다)은 블록을 새로 추가/삭제하는 구조적 패치를 `missing_reason`
(= `action:"unsupported"`로 즉시 거부하면서 이유도 안 씀, eval_count 6~10)으로 거의 전부
거절합니다.** exaone은 같은 요청을 거의 완벽히 처리합니다. qwen2.5-coder는 J(신규 생성)에서
20/20 만점이면서 정확히 같은 능력이 필요 없는 K의 구조 변경에서는 최악이라 — "생성은
잘하는데 구조적 수정 지시는 인식 못 함"이 이 모델의 특성으로 보입니다.

exaone의 J8 실패(placeholder — 문구에 대괄호 자리표시자가 남음)는 두 기기(cuda·cpu)에서
**회차별 성패 패턴이 정확히 일치**했습니다(회차 2·4는 항상 성공, 1·3·5는 항상 실패) —
기기 노이즈가 아니라 특정 seed에서 재현되는 진짜 모델 특성입니다.

### v1 S ↔ v2 J 참고 비교 (pair, 표본 수 주의)

| | S1/J1 | S2/J2 | S8/J8 | S9/J9 |
| --- | --- | --- | --- | --- |
| exaone — S(v1, 4기기 합산) | 20/20 | 20/20 | 20/20 | 20/20 |
| exaone — J(v2, 윤기 1기기) | 4/5 | 5/5 | 2/5 | 4/5 |
| qwen2.5:7b — S(v1, 4기기) | 20/20 | 20/20 | 20/20 | 20/20 |
| qwen2.5:7b — J(v2, 윤기 1기기) | 5/5 | 4/5 | 5/5 | 4/5 |

v1은 4기기 합산, v2는 아직 1~2기기뿐이라 표본 크기가 안 맞습니다 — 방향성 참고만 하고,
기기가 더 모이기 전에는 "J가 S보다 못하다"고 단정하지 않습니다. 위 NUM_PREDICT 캡
문제가 이 차이의 상당 부분을 설명할 가능성이 있습니다.

### ⚠ 주호(cpu로 표시된) 데이터 — backend 라벨을 곧이곧대로 믿지 말 것

`base/engine.py`의 backend 감지는 `nvidia-smi`가 있으면 "cuda", 없으면 무조건 "cpu"로
찍습니다(AMD GPU·iGPU는 볼 방법이 없음). 주호의 CPU는 `AMD64 Family 25 Model 80`
(Ryzen 6000번대 모바일 — Radeon 680M 내장 GPU 탑재 모델)인데, exaone 응답시간이
**3.6s**로 윤기의 실제 NVIDIA GPU(GTX 1070 Ti, cuda, 7.4s)보다 오히려 빠르고 eval_rate도
더 높습니다(~38~39 tok/s vs ~30 tok/s). 7.8B 모델이 순수 CPU 추론으로 GPU보다 빠를 수는
없으므로, **이 "cpu" 라벨은 오탐일 가능성이 높습니다** — Ollama가 내장 GPU(Vulkan)를 쓰고
있는데 `nvidia-smi` 기반 감지가 놓쳤을 것으로 보입니다. `env_v2_주호_*.json`의 `gpu` 필드도
"cpu-only 또는 감지 실패 (통합그래픽 가능성 — 수동 확인 필요)"로 스스로 이 가능성을
경고하고 있습니다.

**그래서 지금은 backend별 시간 비교표에서 주호의 시간 지표를 신뢰하지 않습니다.**
`hard_ok`/`fails` 같은 품질 지표는 backend 오탐과 무관하게 유효합니다(같은 GPU 계열
안에서만 결정론이 보장되는 게 아니라, 통과/실패 자체는 그대로 기록된 사실이므로). 실제
가속 방식은 주호가 기기에서 직접 `ollama ps`나 작업 관리자의 GPU 사용률로 확인해 주세요.

## 결론

_(미정 — exaone3.5:7.8b는 2기기, 나머지 모델은 1기기뿐이라 아직 이르다. 최소 qwen 계열도
2기기 이상 모이면 다시 판단.)_
