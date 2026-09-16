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

_(아직 실행 전 — CSV가 모이면 `summarize.py` 출력을 여기 붙여넣습니다.)_

## 결론

_(미정)_
