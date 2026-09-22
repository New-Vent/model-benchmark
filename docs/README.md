# docs/ — 읽는 순서

이 폴더는 하나의 이야기를 네 조각으로 나눠 담는다. 순서대로 읽으면 이렇게 이어진다.

```
architect/  뭘 만들 것인가 (설계: JSON 방식 vs HTML 방식)
     ↓
common/     어떻게 잴 것인가 (버전이 바뀌어도 안 바뀌는 방법론)
     ↓
reports/    로컬 LLM(Ollama)으로 그렇게 재본 결과 — v1~v7
     ↓
bedrock/    그 결과 때문에 왜, 어떻게 클라우드(Bedrock)로 넘어갔는가
```

## 1. `architect/` — 설계: JSON 방식 vs HTML 방식

[`project-architect.md`](architect/project-architect.md) — LLM이 이벤트 페이지를 만들 때
서버와 책임을 어떻게 나눌지에 대한 **두 가지 설계안**.

- **Part 1 — HTML 방식**: LLM이 HTML을 직접 쓰되, `data-block`/`data-slot`/`data-behavior`로
  서버가 구조·데이터·동작을 통제한다.
- **Part 2 — JSON 방식**: LLM이 HTML 대신 Page Schema(JSON)를 내고, 서버(Renderer)가
  HTML로 변환한다.

**둘 다 "설계"이지 "구현 현황"이 아니다** — 실제로 어느 쪽이 코드로 존재하는지는 이
문서만 봐서는 모른다. 저장소 루트의 [`bedrock/README.md`](../bedrock/README.md) §0-①이
`newvent-backend`와 대조해 확인해둔 결론: **HTML 방식은 실제로 구현되어 있고, JSON
방식은 아직 설계뿐이다.** 이 사실이 아래 `reports/`와 `bedrock/`을 읽을 때 계속
따라붙는 전제다

## 2. `common/` — 방법론: 버전이 바뀌어도 안 바뀌는 원칙

[`methodology.md`](common/methodology.md) — 위 설계를 **어떻게 채점하고, 어떻게 여러
버전·여러 사람의 결과를 합칠 것인가**의 공통 규칙. 군(D·E·JS·N·S·J·K·C·R)의 정의,
CHAIN(파이프라인) 검증 기준, 결과 합치기 규칙, 재실행·표본 수 원칙, 통계적 유의성
검정(McNemar)까지 — **모델이나 버전이 바뀌어도 이 문서의 내용은 안 바뀐다.** 버전마다
달라지는 것(모델 목록·파라미터·케이스 수)은 각 `versions/<버전>/README.md`에 있다.

## 3. `reports/v1_v1-v7/` — 로컬 LLM(Ollama)으로 그렇게 재본 결과

`architect/`의 HTML 방식을, `common/methodology.md`의 규칙대로 로컬 모델
4~6종에 v1부터 v7까지 실제로 재본 결과다.

| 문서 | 내용 |
| --- | --- |
| [`v-summary.md`](reports/v1_v1-v7/v-summary.md) | 버전별 원표(통과율·실패 유형 분포·속도) — 다른 세 문서의 근거 데이터 |
| [`모델선정_종합보고서.md`](reports/v1_v1-v7/모델선정_종합보고서.md) | 버전별 상세 결과 + 모델 최종 판정 |
| [`pipeline.md`](reports/v1_v1-v7/pipeline.md) | 축별(생성·수정·JS추가·값수정) 결론 |
| [`model.md`](reports/v1_v1-v7/model.md) | 모델별 추이·탈락/채택 근거 |

**결론만 먼저 보려면** 최상위 [`README.md`](../README.md)의 "v7까지의 결론" 절이 가장
짧다 — `qwen2.5:7b`·`qwen2.5-coder:7b` 최종 후보, `exaone3.5:7.8b`·`gemma3:4b` 탈락 확정.

## 4. `bedrock/` — 왜, 어떻게 클라우드로 넘어갔는가

`reports/`가 보여준 로컬 결론(작은 모델의 구조적 한계, 버전마다 재발하는 실패 모드)이
**왜** 넘어가는 이유이고, 그 다음 **어떻게** 넘어가서 무엇을 잴지가 설계다.

| 문서 | 역할 |
| --- | --- |
| [`v1-migration.md`](bedrock/v1-migration.md) | **왜** — `reports/`의 실측 데이터를 근거로 로컬→Bedrock 전환 이유를 정리 |
| [`v2-pipeline.md`](bedrock/v2-pipeline.md) | **어떻게** — Bedrock을 Generator/Judge로 어떻게 나눠 쓸지, JSON/HTML 두 방식을 어떤 항목으로 채점할지 설계 |

**`v2-pipeline.md`는 설계 문서이고, 실제 구현은 저장소 루트의 [`bedrock/`](../bedrock/)
폴더다.** 그 폴더의 `README.md` §0이 이 설계 문서와 실제 코드(`newvent-backend`,
`versions/v8`)를 대조해서 확인한 것 — 특히 "JSON 방식은 아직 백엔드에 없다"(§1
`architect/`의 전제와 동일)와 "Bedrock을 심판으로 쓰는 계층이 이 저장소에 없었다"는
두 가지 빠진 조각을 채운 자리다.

Bedrock에서의 실측 결론(v8~v9)은 이 설계·구현과 별개로 최상위
[`README.md`](../README.md) 최상단 "v8~v9 결론"에 있다.
