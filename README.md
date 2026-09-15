# Ollama 모델 벤치마크

이벤트 페이지 생성/수정에 쓸 로컬 LLM과 출력 방식을 정하기 위한 테스트 기록입니다.
방법론 원문은 [docs/v8-plan.md](docs/v8-plan.md)에 있습니다.

## 진행 순서

```
Phase 1  모델 + 출력 방식(N/S) 비교, D·E·JS·C·R군      ← 지금 단계, 2대 이상 기기에서 분담 실행
Phase 2  파라미터 미니 스윕 (repeat_penalty, temperature)  ← Phase 1 확정 후, 1대 기기로 충분
```

## `scripts/benchmark_v8.py` — 손대지 않는 완성본

D·E·JS·N·S·C·R 7개 군이 전부 구현되어 있는 단일 스크립트입니다. **바꿔도 되는 건 `RUNNER` 환경변수뿐이고, `MODELS`·`BASE_OPTIONS`·`NUM_PREDICT`·`SEEDS`·프롬프트·케이스는 절대 임의로 고치지 않습니다** (스크립트 상단 주석, docs/v8-plan.md §13). 다음 라운드에 군(J/K 등)을 추가할 때는 docs/v8-plan.md의 "6-1. 다음 라운드에 군 추가하기"를 따릅니다.

## Phase 1 — 여러 컴퓨터에서 분담 실행

**결과 파일이 사람마다 안 섞이도록, 자기 이름의 폴더를 만들고 그 안에서 실행합니다.**

```bash
pip install requests beautifulsoup4
for m in exaone3.5:7.8b qwen2.5:7b gemma3:4b qwen3:8b; do ollama pull "$m"; done
ollama list   # digest가 docs/v8-plan.md §3 표와 일치하는지 확인

# 컴퓨터 A
mkdir -p results/raw/kwon_M3Pro && cd results/raw/kwon_M3Pro
export RUNNER="kwon_M3Pro"
python ../../../scripts/benchmark_v8.py
```

```bash
# 컴퓨터 B (다른 사람 / 다른 기기)
mkdir -p results/raw/joo_RTX4060 && cd results/raw/joo_RTX4060
export RUNNER="joo_RTX4060"
python ../../../scripts/benchmark_v8.py
```

스크립트가 실행된 폴더(현재 디렉터리) 기준으로 아래가 생성됩니다.

```
results/raw/<RUNNER>/
  results_v8_<RUNNER>_<날짜>.csv   호출마다 한 행
  env_v8_<RUNNER>_<날짜>.json      환경·설정·보정·드리프트
  raw_v8/                          시도별 원문 HTML (브라우저로 열어 눈으로 확인, 특히 JS군)
```

시작 전에 `self_check()`와 `preflight()`가 자동으로 돌아 로직 결함·모델 누락을 미리 잡아줍니다. 전원이 네 모델을 다 돌리므로 기기당 2~3시간 걸리고, 무인으로 돌아갑니다.

**두 컴퓨터 결과를 한곳에 모은 뒤** (git, USB, 공유 드라이브 등으로 `results/raw/` 전체를 합쳐서):

```bash
python scripts/merge_results.py
```

- digest 불일치, `base_options` 불일치, drift 이상은 자동으로 경고합니다
- 합친 결과는 `results/merged/combined_v8_<날짜>.csv`
- **시간(wall_sec) 비교는 반드시 같은 `runner` 안에서만** 하세요. 기기 간 절대시간 비교는 무효입니다

## Phase 2 — 파라미터 미니 스윕

Phase 1에서 모델이 확정된 뒤 1대에서만 실행합니다. 전체 재스윕이 아니라, 이미 위험 신호가 있는 `repeat_penalty`/`temperature` 두 개만 좁게 검증합니다 (docs/v8-plan.md §7).

```bash
export CHOSEN_MODEL="exaone3.5:7.8b"   # Phase 1에서 확정된 모델
python scripts/param_sweep.py
```

결과는 `results/param-sweep/<날짜>/`에 쌓이고, `temperature_sweep.csv`의 원문은 `blind/` 폴더에 익명화되어 저장됩니다(문장 품질 블라인드 채점용, `blind_key.json`은 채점 끝날 때까지 열어보지 않음).

## 전체 디렉터리 구조

```
model-benchmark/
  README.md
  docs/
    v8-plan.md                 ← 방법론 원문 (source of truth)
  scripts/
    benchmark_v8.py             ← Phase 1 완성본 (손대지 않음)
    merge_results.py            ← 여러 컴퓨터 결과 합치기
    param_sweep.py              ← Phase 2 실행 스크립트
  results/
    raw/
      <runner-1>/               ← 컴퓨터별 실행 결과 (해당 폴더 안에서 직접 실행)
      <runner-2>/
    merged/
      combined_v8_<날짜>.csv    ← merge_results.py 출력
    param-sweep/
      <날짜>/
```
