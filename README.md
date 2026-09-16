# Ollama 모델 벤치마크

이벤트 페이지 생성/수정에 쓸 로컬 LLM을 정하기 위한 실험 기록입니다.
버전이 바뀌어도 변하지 않는 원칙은 [docs/methodology.md](docs/methodology.md)에 있습니다.

## 버전

**프롬프트·채점·파라미터·모델·케이스 중 하나라도 달라지면 새 버전을 팝니다.**
조건이 다르면 결과를 섞을 수 없어서, 스크립트와 결과와 분석을 한 폴더에 같이 둡니다.

| 버전 | 내용 | 상태 |
| --- | --- | --- |
| [v1](versions/v1/) | D·E·JS·N·S·C·R 군, 출력 방식 N·S | **4대 완료 (3362행) — 생성 모델 qwen2.5:7b 결정** |

## 폴더 하나의 구성

```
versions/v1/
  benchmark_v1.py                    스크립트 (RUNNER 외에는 고치지 않음)
  results_v1_kwon_*.csv                runner마다 CSV 하나
  results_v1_지원_*.csv
  env_v1_kwon_*.json                   digest·drift·기기 정보
  raw_v1/                            시도별 원문 (git 제외, 로컬에만)
  README.md                            이 버전의 조건 + 변경점 + 실행법 + 결과 비교표 + 해석
```

버전 README에는 **그 버전에서만 유효한 조건**(모델 목록·digest·파라미터·케이스 수)을 적습니다.
군이 각각 무엇을 재는지 같은 공통 정의는 `docs/methodology.md`에 한 번만 적습니다.

## 한 사이클

```bash
# 1. 각자 버전 폴더에서 실행 (전원 같은 스크립트, RUNNER만 다르게)
cd versions/v1
export RUNNER="kwon"
python benchmark_v1.py

# 2. CSV가 모이면 비교표 생성 → README의 결과 섹션에 붙여넣기
python ../../tools/summarize.py .
```

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
mkdir versions/v2
cp versions/v1/benchmark_v1.py versions/v2/benchmark_v2.py
```

스크립트 안의 출력 파일명(`results_v2_...`, `env_v2_...`, `raw_v2/`)도 같이 올려야 이전 결과와 안 섞입니다.
`versions/v2/README.md`에 **직전 버전에서 무엇을 왜 바꿨는지**와 **그 버전의 조건표**를 적습니다.

## 다음 버전 후보

이미 위험 신호가 있는 파라미터만 좁게 검증합니다. 전체를 다시 스윕하지 않습니다.

| 바꿀 것 | 검증값 | 가설 | 볼 것 |
| --- | --- | --- | --- |
| `repeat_penalty` | 1.0 / 1.1 / 1.3 | 높을수록 `<li>` 반복이 억제되어 혜택 개수가 모자람 | S군 실패율 |
| `temperature` | 0.1 / 0.2 / 0.4 | 높을수록 문장 품질↑, 환각도 같이↑ | D군 실패율 + 블라인드 문장 품질 |
| 출력 방식 J·K 추가 | — | 조합 계획/패치가 HTML 직접 생성보다 안정적인가 | 전 군 |
| qwen3:8b 제외 | — | 출력 잘림 14%(전부 실패) + 3.3~6.8배 느림 → v1에서 탈락 확정 | — |

`num_predict`, `top_p`/`top_k`는 바꾸지 않습니다 — 전자는 `done_reason`으로 상한 도달만 확인,
후자는 부차 효과로 판단해 고정합니다.

## 사전 준비

```bash
pip install -r requirements.txt
for m in exaone3.5:7.8b qwen2.5:7b gemma3:4b qwen3:8b; do ollama pull "$m"; done
ollama list   # digest가 버전 README의 표와 일치하는지 확인
```
