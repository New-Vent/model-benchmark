# Ollama 모델 벤치마크

이벤트 페이지 생성/수정에 쓸 로컬 LLM을 정하기 위한 실험 기록입니다.
버전이 바뀌어도 변하지 않는 원칙은 [docs/methodology.md](docs/methodology.md)에 있습니다.

## 버전

**프롬프트·채점·파라미터·모델·케이스 중 하나라도 달라지면 새 버전을 팝니다.**
조건이 다르면 결과를 섞을 수 없어서, 스크립트와 결과와 분석을 한 폴더에 같이 둡니다.

| 버전 | 내용 | 상태 |
| --- | --- | --- |
| [v1](versions/v1/) | D·E·JS·N·S·C·R 군, 출력 방식 N·S | **4대 완료 (3362행) — 생성 모델 qwen2.5:7b 결정** |
| [v2](versions/v2/) | J·K 군 + CHAIN(파이프라인 검증), 출력 방식 J·K | 4대 실행 중 — exaone 92%·qwen 계열 88%·gemma3:4b는 K군 0/150 |
| [v3](versions/v3/) | JS군(HTML/JSON 방식 비교)·CHAIN 확장·모델 확대·`NUM_PREDICT` 3072 통일 | **구현 완료(JS-HTML/JS-PLAN/JS-PATCH·CHAIN2~6), 실행 대기 — 아직 실제 모델로 안 돌림** |

## 폴더 구성

공통 코드는 `base/` 한 곳에만 둡니다. 버전 폴더에는 **그 버전의 케이스와 결과만** 둡니다.

```
base/                                공통 — 버전이 늘어도 복사하지 않는다
  run.py                             진입점 (RUNNER·MODELS만 고친다)
  engine.py                          케이스 실행·캘리브레이션·CSV 저장
  registry.py                        블록/변형 레지스트리 + JSON Schema
  checks.py                          채점
  component_library.py               컴포넌트 렌더 함수

versions/v1/                         D·E·JS·N·S·C·R 군
  cases_d.py cases_e.py cases_js.py cases_ns.py cases_c.py cases_r.py
  result_csv/results_v1_도하_*.csv     runner마다 CSV 하나
  result_json/env_v1_도하_*.json       digest·drift·기기 정보
  raw_v1/                            시도별 원문 (git 제외, 로컬에만)
  benchmark_v1.py                    v1 결과를 만들었던 원본 단일 스크립트 (기록용, 보존)
  README.md                          이 버전의 조건 + 실행법 + 결과 비교표 + 결론

versions/v2/                         J·K·CHAIN 군
  cases_j.py cases_k.py cases_chain.py
  result_csv/  result_json/  raw_v2/  README.md
```

`base/`의 파일은 **팀 합의 없이 개인이 고치지 않습니다.** 새 군을 추가할 때는
해당 버전 폴더에 `cases_<이름>.py`를 만들면 `run.py`가 알아서 찾아냅니다
(`CASES: list[Case]`와, 있으면 `self_check()`만 지키면 됩니다).

버전 README에는 **그 버전에서만 유효한 조건**(모델 목록·digest·파라미터·케이스 수)을 적습니다.
군이 각각 무엇을 재는지 같은 공통 정의는 `docs/methodology.md`에 한 번만 적습니다.

## 한 사이클

```bash
# 1. 각자 실행 (전원 같은 스크립트, RUNNER만 다르게)
export RUNNER="도하"          # Windows: set RUNNER=도하
# Ollama가 localhost가 아니면(원격 서버 사용자만) 셸에 맞게 하나만:
# export OLLAMA_HOST="http://<주소>:11434"        # bash
# $env:OLLAMA_HOST = "http://<주소>:11434"         # PowerShell — set은 안 먹는다
# set OLLAMA_HOST=http://<주소>:11434              # cmd.exe
python base/run.py v1         # v1 폴더의 케이스 전부
python base/run.py v1 D       # v1 의 D군만
python base/run.py v1 N S     # 여러 군 지정
python base/run.py v2         # v2 폴더의 케이스 전부 (J·K·CHAIN)
python base/run.py v2 K

# 2. CSV가 모이면 비교표 생성 → 버전 README의 결과 섹션에 붙여넣기
python tools/summarize.py versions/v1

# 3. v1의 S(HTML) ↔ v2의 J(JSON)처럼 pair로 묶인 케이스만 공정하게 비교 (McNemar)
python tools/compare_v1_v2.py                    # 기본: S(v1) ↔ J(v2), 신규 생성
python tools/compare_v1_v2.py --pair-set e-k      # E(v1, 전체재생성) ↔ K(v2, 패치)
```

`python base/run.py <버전>` 은 그 폴더의 `cases_*.py`를 전부 찾아 실행하고,
뒤에 군 이름을 붙이면 **그 버전 안의 그 군만** 돕니다. 어느 쪽이든 결과는
그 버전 폴더로만 들어갑니다.

| 실행 | 결과 |
| --- | --- |
| `python base/run.py v1` | `versions/v1/result_csv/results_v1_*.csv` + `versions/v1/result_json/env_v1_*.json` |
| `python base/run.py v1 D` | 같은 위치에, D군 행만 담긴 CSV 하나 |
| `python base/run.py v2` | `versions/v2/result_csv/` + `versions/v2/result_json/` |

군을 나눠 돌려도 `summarize.py`가 `result_csv/` 아래 CSV를 전부 읽어 합산합니다.
LLM 호출 없이 케이스 정의만 검증하려면 `python base/run.py v1 --self-check`.

`summarize.py`가 뽑는 비교축:

| 축 | 답하는 질문 |
| --- | --- |
| 모델 × 군 (1차/최종) | 어느 모델이 어느 군에서 강한가 |
| 라우터 동작별 | 동작은 맞히는데 대상을 틀리는가 |
| 실패 유형 분포 | 무엇 때문에 떨어지는가 (하드/소프트 분리) |
| 회차별 생성 속도 | 발열로 느려졌는가 |
| runner × 모델 시간 | 기기별 소요 시간 (같은 runner 안에서만 비교) |

폴더 안의 CSV를 전부 읽으므로, runner가 몇 명이든 파일만 넣으면 됩니다.

## 새 버전 만들기

```bash
mkdir -p versions/v3
cp versions/v2/cases_*.py versions/v3/      # 이어갈 군만 골라서 복사
```

공통 코드는 복사하지 않습니다 — `base/`를 그대로 씁니다. 출력 파일명
(`results_v3_...`, `env_v3_...`, `raw_v3/`)은 폴더 이름에서 자동으로 붙으므로
따로 고칠 곳이 없습니다.
`versions/v3/README.md`에 **직전 버전에서 무엇을 왜 바꿨는지**와 **그 버전의 조건표**를 적습니다.

## 사전 준비

```bash
pip install -r requirements.txt
for m in exaone3.5:7.8b qwen2.5:7b gemma3:4b qwen3:8b; do ollama pull "$m"; done
ollama list   # digest가 버전 README의 표와 일치하는지 확인
```
