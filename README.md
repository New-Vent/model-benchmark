# 모델 벤치마크

이벤트 페이지 생성/수정에 쓸 LLM을 정하기 위한 실험 기록입니다.
v1~v7은 로컬 Ollama, **v8부터는 AWS Bedrock**입니다.
버전이 바뀌어도 변하지 않는 원칙은 [docs/common/methodology.md](docs/common/methodology.md)에 있습니다.
`docs/` 전체를 어떤 순서로 읽으면 되는지는 [docs/README.md](docs/README.md)에 정리되어 있습니다.

## v8~v9 결론 — Bedrock

- **1순위: `google.gemma-3-27b-it`.** 전 축 만점(v8 45/45, v9 60/60)이고
  `claude-haiku-4.5`와 **동점인데 비용이 1/9**입니다(실서비스 추정 1,119원 vs 7,883원).
- **갈린 축은 라우터 하나뿐입니다.** 생성·수정·누적수정은 네 모델 전부 만점이라
  변별력이 없었습니다. 라우터만 gemma 24/24 · oss120 22/24 · qwen3-coder 16/24로 갈립니다.
- **체급이 답이 아닙니다.** 로컬 `qwen2.5:7b`(17/24)가 Bedrock `qwen3-coder-30b`(16/24)보다
  라우터를 잘합니다. 반면 gemma는 4B→27B에서 크게 올랐습니다 — **계열마다 강한 축이 다릅니다.**
- **슬롯·`class`·`href` 보존은 실패 0건**(v9, 4모델 60호출).
- **실제 템플릿에서는 qwen만 무너집니다**(v10). `data-slot` 을 **스스로 지어냈고**
  (`benefit-1-name` 등), 블록을 통째로 다시 썼습니다. gemma·haiku 는 27/27.

## v7까지의 결론 — 로컬

- **최종 후보: `qwen2.5:7b`, `qwen2.5-coder:7b`.** 인공 문서(v1~v3)·실제 템플릿
  수정(v4)·실제 템플릿 생성(v5)·전체 파이프라인(v7) 전 구간에서 거의 무결점입니다.
  둘은 v4·v5·v7에서 **완전 동률**이라 이 저장소의 데이터만으로는 갈리지 않습니다.
- **수정 경로는 S(HTML 블록 직접 수정)가 J/K(JSON 계획·패치)보다 낫습니다.**
  v2에서 J/K가 유리해 보인 건 인공 문서 조건의 착시였고, v4가 실제 템플릿으로
  뒤집었습니다.
- **신규 생성 경로는 S-T·J-T 어느 쪽도 무방합니다** (v5, qwen 계열 100/100 동률).
  "수정에서 S가 낫다"는 결론이 생성에는 그대로 적용되지 않습니다.
- **`exaone3.5:7.8b`는 JSON을 다루는 모든 단계에서 탈락**합니다. 생성(J-T 1/50)·
  수정(K-T)·맨눈 변환(v7 CHAIN7-S 0/10) 전부 "텍스트 필드에 마크업을 못 뺀다"는
  같은 결함의 변주이고 2기기에서 재현됩니다. S(HTML) 단독 경로로는 여전히 쓸 만합니다.
- **`gemma3:4b`는 탈락 유지.** 생성은 84%로 나쁘지 않지만 패치(K) 계열이 반복 전멸합니다.
- **모델에게 "지어낼 것"을 안 주면 실패가 사라집니다** (v6). 문구 생성을 빼고 구조만
  내게 하거나(`J-STRUCT`), `remove_item` 대신 `set_field itemCount`로 표현을 바꾸면
  (`K-COUNT`) 0%였던 축이 100%로 올라옵니다 — **모델을 바꾸는 것보다 요청 형태를
  바꾸는 쪽이 효과가 컸습니다.**

버전별 근거는 각 버전 README, 종합 정리는 [docs/reports/v1_v1-v7/](docs/reports/v1_v1-v7/)에 있습니다.

| 보고서 | 내용 |
| --- | --- |
| [모델선정_종합보고서.md](docs/reports/v1_v1-v7/모델선정_종합보고서.md) | v1~v7 통합 모델 선정 근거 |
| [pipeline.md](docs/reports/v1_v1-v7/pipeline.md) | 축별 결론(생성·수정·JS추가·값수정) — v7 CHAIN7까지 확정 |
| [v-summary.md](docs/reports/v1_v1-v7/v-summary.md) | 버전별 `summarize.py` 원표 모음 |
| [model.md](docs/reports/v1_v1-v7/model.md) | 모델별 특성 정리(v1~v7 추이) |

<details>
<summary>모델 테스트 버전 7개</summary>
<div markdown="1">

**프롬프트·채점·파라미터·모델·케이스 중 하나라도 달라지면 새 버전을 팝니다.**
조건이 다르면 결과를 섞을 수 없어서, 스크립트와 결과와 분석을 한 폴더에 같이 둡니다.

| 버전 | 무엇을 쟀나 | 조건 | 상태 |
| --- | --- | --- | --- |
| [v1](versions/v1/) | 기본 생성·편집·라우팅 (D·E·JS·N·S·C·R) | 인공 문서 370~590자 | **완료** — 4,178행 / 4명(도하·윤기·주호·지원) |
| [v2](versions/v2/) | JSON 계획·패치 도입 (J·K·CHAIN) | 인공 문서 | **완료** — 1,078행 / 3명 |
| [v3](versions/v3/) | JS 인터랙션 3방식 비교(JS-HTML·JS-PLAN·JS-PATCH) + CHAIN2~6 + K-CONTENT | 인공 문서, `num_predict` 3072 | **완료** — 3,291행 / 3명 |
| [v4](versions/v4/) | 실제 제품 템플릿으로 **수정** 경로 재측정 (S-E vs K-T) | 실제 템플릿 4,351~5,356자, 통일 채점기 | **완료** — 728행 / 2명 |
| [v5](versions/v5/) | 실제 제품 템플릿으로 **신규 생성** 재측정 (S-T vs J-T) | 실제 템플릿, `checks_v4`를 `base/`로 승격 | **완료** — 544행 / 2명(윤기·주호) |
| [v6](versions/v6/) | 요청 형태를 바꿔 실패를 없애기 (J-STRUCT · J-STRUCT-V · K-COUNT) | 구조만 출력(문구 없음) / `set_field itemCount` | **실행됨 — 752행 / 1명(주호)**, README 일부가 실측과 어긋남 (아래 주의) |
| [v7](versions/v7/) | 확정 조합을 실제 스케일로 잇기 (CHAIN7-J-E · CHAIN7-J-K · CHAIN7-S) | 실제 템플릿, 4단계 전체 파이프라인 | **완료** — 499행 / 2명(윤기·주호) |
| [v8](versions/v8/) | **Bedrock 모델 비교** (G 생성 · E 수정 · R 라우터 · C 누적수정) | **백엔드 레지스트리 기준**, 정화 뒤를 채점 | **완료** — 213행 / 4모델 + 로컬 대조군, 48원 |
| [v9](versions/v9/) | 슬롯·`class`·`href` 보존 (E1·E2·C1 추가) | v8 + **정화가 생성/수정 2종**, 재시도 4회 | **완료** — 180행 / 4모델, 98원 |
| [v10](versions/v10/) | **실제 템플릿으로 수정** (D 디자인파괴 · P 보존 · H 준것만) | **`template/*.html` 5종** (class 451건, 블록 2,229자) | **완료** — 4모델, 886원 |

각 버전이 직전 버전에서 **무엇을 왜 바꿨는지**는 그 버전 README의 앞부분에 있습니다.

### v8부터 성격이 다릅니다

v1~v7은 **설계를 고르는** 실험이었습니다(J vs S, 부분 vs 전체 재생성, 체인 라우팅).
v8부터는 설계가 확정된 뒤 **모델을 고르는** 실험이고, 기준선도 바뀌었습니다.

| | v1~v3 | v4~v7 | **v8~v9** |
| --- | --- | --- | --- |
| baseline | 인공 문서 | 디자이너 템플릿 5종 | **백엔드 `Block.shape`** |
| 채점 | `checks.py` | `checks_v4.py` | **백엔드 `BlockValidator` 이식** |
| 프롬프트 | 벤치마크 자체 정의 | 자체 정의 | **백엔드 `PromptBuilder` 이식** |
| 모델 | 로컬 Ollama | 로컬 Ollama | **Bedrock** (+ 로컬 대조군) |
| 채점 시점 | 정화 없음 | 정화 없음 | **정화 뒤** |

마지막 줄이 중요합니다. v1~v7은 `raw → extract → check`였지만 실제 서비스는
`raw → extract → sanitize → validate`입니다. **모델 출력이 맞아도 정화가
망가뜨리면 제품은 깨지는데**, 정화 전을 채점하면 그걸 영영 못 봅니다.

**v8~v9는 `base/`를 쓰지 않습니다.** 백엔드 미러라 필요한 게 달라서 독립 러너를
씁니다(`python versions/v8/run_v8.py`) — v1~v7 결과는 그대로 재현 가능합니다.

</div>
</details>

<details>
<summary>폴더 구성</summary>
<div markdown="1">

공통 코드는 `base/` 한 곳에만 둡니다. 버전 폴더에는 **그 버전의 케이스와 결과만** 둡니다.

```
base/                                공통 — 버전이 늘어도 복사하지 않는다
  run.py                             진입점 (RUNNER·MODELS만 고친다)
  engine.py                          케이스 실행·캘리브레이션·CSV 저장
  registry.py                        블록/변형 레지스트리 + JSON Schema
  checks.py                          채점 (v1~v3 벤치마크 규격)
  checks_v4.py                       제품 규격 채점 (v4에서 만들어 v5에 승격)
  edit_lib.py                        블록 왕복 편집 공용 헬퍼
  component_library.py               컴포넌트 렌더 함수

template/                            실제 서비스 템플릿 5종 (v4부터 baseline)
docs/common/methodology.md           버전 무관 공통 원칙
docs/architect/project-architect.md  HTML·JSON 두 방식의 설계 문서(§0-①: HTML만 구현됨)
docs/bedrock/                        v1-migration.md(전환 이유) · v2-pipeline.md(평가 설계)
docs/reports/v1_v1-v7/               버전 횡단 종합 보고서

versions/v4/                         S-E·K-T 군
  cases_se.py cases_kt.py templates.py
  result_csv/results_v4_OO_*.csv     runner마다 CSV 하나
  result_json/env_v4_OO_*.json       digest·drift·기기 정보
  raw_v4/                            시도별 원문 (git 제외, 로컬에만)
  README.md                          이 버전의 조건 + 실행법 + 결과 비교표 + 결론
```

`base/`의 파일은 **팀 합의 없이 개인이 고치지 않습니다.** 새 군을 추가할 때는
해당 버전 폴더에 `cases_<이름>.py`를 만들면 `run.py`가 알아서 찾아냅니다
(`CASES: list[Case]`와, 있으면 `self_check()`만 지키면 됩니다).

버전 README에는 **그 버전에서만 유효한 조건**(모델 목록·digest·파라미터·케이스 수)을 적습니다.
군이 각각 무엇을 재는지 같은 공통 정의는 `docs/common/methodology.md`에 한 번만 적습니다.

</div>
</details>

<details>
<summary>테스트 사이클</summary>
<div markdown="1">

## 한 사이클

```bash
export RUNNER="OO"          # Windows: set RUNNER=OO
# Ollama가 localhost가 아니면(원격 서버 사용자만) 셸에 맞게 하나만:
# export OLLAMA_HOST="http://<주소>:11434"        # bash
# $env:OLLAMA_HOST = "http://<주소>:11434"         # PowerShell — set은 안 먹는다
# set OLLAMA_HOST=http://<주소>:11434              # cmd.exe
python base/run.py v1         # v1 폴더의 케이스 전부
python base/run.py v1 D       # v1 의 D군만
python base/run.py v1 N S     # 여러 군 지정

```

`python base/run.py <버전>` 은 그 폴더의 `cases_*.py`를 전부 찾아 실행하고,
뒤에 군 이름을 붙이면 **그 버전 안의 그 군만** 돕니다. 어느 쪽이든 결과는
그 버전 폴더로만 들어갑니다.

| 실행 | 결과 |
| --- | --- |
| `python base/run.py v1` | `versions/v1/result_csv/results_v1_*.csv` + `versions/v1/result_json/env_v1_*.json` |
| `python base/run.py v1 D` | 같은 위치에, D군 행만 담긴 CSV 하나 |
| `python base/run.py v6 K-COUNT` | `versions/v6/result_csv/` + `versions/v6/result_json/` |

군을 나눠 돌려도 `summarize.py`가 `result_csv/` 아래 CSV를 전부 읽어 합산합니다.
LLM 호출 없이 케이스 정의만 검증하려면 `python base/run.py v1 --self-check`.

`summarize.py`가 뽑는 비교축:

| 축 | 답하는 질문 |
| --- | --- |
| 모델 × 군 (1차/최종) | 어느 모델이 어느 군에서 강한가 |
| CHAIN 파이프라인 전체 통과율 | 단계가 아니라 **체인 전체**가 끝까지 이어졌는가 |
| 라우터 동작별 | 동작은 맞히는데 대상을 틀리는가 |
| 실패 유형 분포 | 무엇 때문에 떨어지는가 (하드/소프트 분리) |
| 회차별 생성 속도 | 발열로 느려졌는가 |
| runner × 모델 시간 | 기기별 소요 시간 (같은 runner 안에서만 비교) |

폴더 안의 CSV를 전부 읽으므로, runner가 몇 명이든 파일만 넣으면 됩니다.

> CHAIN 군은 "모델 × 군" 표와 "파이프라인 전체 통과율" 표의 수치가 다릅니다 —
> 앞은 단계를 독립 케이스로 더한 값이고, 뒤가 `docs/common/methodology.md` §4가 말하는
> 진짜 성공 기준(체인 전체 완주)입니다. **CHAIN을 인용할 때는 뒤쪽 표를 쓰세요.**

</div>
</details>


## 사전 준비

```bash
pip install -r requirements.txt
for m in exaone3.5:7.8b qwen2.5:7b gemma3:4b qwen2.5-coder:7b; do ollama pull "$m"; done
ollama list   # digest가 버전 README의 표와 일치하는지 확인
```
