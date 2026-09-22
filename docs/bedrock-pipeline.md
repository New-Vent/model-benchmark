# Amazon Bedrock — JSON / HTML 방식 LLM 평가 설계

## 1. 개요

본 프로젝트에서는 로컬 LLM을 이용한 이벤트 페이지 생성 및 수정 방식을 비교하기 위해 Amazon Bedrock의 **Model Evaluation / LLM-as-a-Judge** 기능을 사용한다.

비교 대상은 다음 두 가지 방식이다.

```text
JSON 방식
LLM
 ↓
Page Schema / Modification Command
 ↓
Server
 ↓
Renderer
 ↓
HTML
```

```text
HTML 방식
LLM
 ↓
HTML + Behavior Metadata
 ↓
Validator
 ↓
Sanitizer
 ↓
HTML
 ↓
Runtime JavaScript
```

두 방식의 공정한 비교를 위해 **사용자 요구사항과 테스트 케이스는 동일하게 유지하고, 출력 형식과 평가 항목만 방식에 맞게 분리한다.**

---

# 2. 평가의 기본 원칙

## 2.1 동일한 Prompt 사용

JSON 방식과 HTML 방식은 동일한 사용자 요구사항을 입력으로 사용한다.

예:

```text
여름 휴가 시즌을 맞아
7월 1일부터 7월 31일까지
데이터 추가 혜택을 제공하는
통신사 이벤트 페이지를 만들어줘.
```

동일한 Prompt를 각각의 LLM 설정에 전달한다.

```text
                 동일한 Prompt
                       │
              ┌────────┴────────┐
              ↓                 ↓
         JSON 방식           HTML 방식
              ↓                 ↓
        JSON Output          HTML Output
```

이렇게 해야 출력 형식의 차이가 평가 결과에 영향을 주더라도 동일한 입력 조건에서 비교할 수 있다.

---

# 3. 테스트 케이스 구성

테스트 케이스마다 고유 ID를 부여한다.

```json
{
  "id": "TC-001",
  "prompt": "여름 휴가 시즌을 맞아 7월 1일부터 7월 31일까지 데이터 추가 혜택을 제공하는 통신사 이벤트 페이지를 만들어줘.",
  "requirements": {
    "startDate": "2026-07-01",
    "endDate": "2026-07-31",
    "benefit": "데이터 추가 혜택"
  }
}
```

테스트 케이스의 핵심 정보는 다음과 같다.

| 필드             | 설명                |
| -------------- | ----------------- |
| `id`           | 테스트 케이스 식별자       |
| `prompt`       | LLM에 전달할 사용자 요구사항 |
| `requirements` | 정량적 검증에 사용할 요구사항  |
| `category`     | 생성/수정/행동 등 평가 유형  |

---

# 4. JSON 방식과 HTML 방식의 동일 테스트

하나의 테스트 케이스를 두 방식에서 공통으로 사용한다.

```text
TC-001
 │
 ├── JSON 방식
 │    └── Qwen → JSON Output
 │
 └── HTML 방식
      └── Qwen → HTML Output
```

따라서 다음 조건은 동일하다.

```text
Prompt
테스트 데이터
요구사항
LLM 모델
Temperature 등 생성 설정
테스트 횟수
```

변경되는 것은 출력 방식이다.

```text
JSON 방식 → Page Schema
HTML 방식 → HTML + Behavior Metadata
```

---

# 5. S3 Dataset 구성

Bedrock 평가에 사용할 데이터셋은 JSONL 형식으로 구성한다.

권장 구조:

```text
datasets/
├── generation.jsonl
├── edit.jsonl
└── behavior.jsonl
```

각 줄은 하나의 테스트 케이스를 나타낸다.

---

# 6. Generation Dataset

생성 테스트에서는 동일한 사용자 요구사항을 사용한다.

예:

```json
{"prompt":"여름 휴가 시즌을 맞아 7월 1일부터 7월 31일까지 데이터 추가 혜택을 제공하는 통신사 이벤트 페이지를 만들어줘.","category":"generation"}
{"prompt":"신규 가입 고객에게 첫 달 데이터 10GB를 추가 제공하는 이벤트 페이지를 만들어줘.","category":"generation"}
{"prompt":"주말 방문 고객에게 특별 혜택을 제공하는 이벤트 페이지를 만들어줘.","category":"generation"}
```

JSON 방식과 HTML 방식에서 이 Prompt Dataset을 동일하게 사용한다.

---

# 7. Edit Dataset

수정 테스트에서는 기존 페이지와 수정 요구사항을 함께 사용한다.

예:

```json
{
  "prompt": "현재 이벤트 페이지의 Hero 영역 제목을 '여름 데이터 페스티벌'로 변경해줘.",
  "category": "edit"
}
```

실제 평가에서는 기존 HTML 또는 기존 Page Schema를 LLM에 제공해야 한다.

따라서 테스트 데이터에는 다음 정보를 관리할 수 있다.

```text
TC-101
 ├── 기존 페이지
 ├── 수정 요청
 └── 기대되는 변경 범위
```

예:

```json
{
  "id": "TC-101",
  "prompt": "Hero 영역의 제목만 변경해줘.",
  "target": "hero",
  "requirements": {
    "title": "여름 데이터 페스티벌",
    "unchangedBlocks": [
      "benefit",
      "event-info",
      "cta"
    ]
  }
}
```

---

# 8. Behavior Dataset

HTML 방식에서 `data-behavior`를 사용하는 경우 별도의 행동 테스트를 구성한다.

예:

```text
사용자가 쿠폰 받기 버튼을 클릭하면
쿠폰 발급 API를 호출하고
성공하면 성공 Modal을 표시한다.
```

기대되는 구조:

```json
{
  "event": "click",
  "actions": [
    {
      "type": "api-request",
      "method": "POST",
      "endpoint": "/api/coupons/issue"
    },
    {
      "type": "show-modal",
      "target": "coupon-success-modal"
    }
  ]
}
```

---

# 9. 생성된 LLM 결과 수집

현재 프로젝트에서는 Qwen과 같은 로컬 LLM을 사용할 수 있으므로 다음 구조로 결과를 수집한다.

```text
Qwen
 ↓
Python / Spring Boot
 ↓
LLM Output 저장
 ↓
JSONL 생성
 ↓
S3 Upload
 ↓
Bedrock Evaluation
```

예:

```text
outputs/
├── json/
│   ├── TC-001.json
│   ├── TC-002.json
│   └── ...
│
└── html/
    ├── TC-001.html
    ├── TC-002.html
    └── ...
```

---

# 10. Bedrock의 역할

Bedrock은 LLM 결과를 직접 생성하는 용도로만 사용하는 것이 아니다.

본 프로젝트에서는 **LLM-as-a-Judge** 역할로 사용한다.

```text
로컬 LLM
    ↓
실제 결과 생성
    ↓
Bedrock Judge
    ↓
결과 평가
```

즉:

```text
Generator
→ Qwen

Evaluator / Judge
→ Bedrock에서 지정한 평가 모델
```

로 역할을 분리한다.

---

# 11. BYO Model Response 방식

로컬 LLM의 결과를 평가하는 경우 **이미 생성된 Model Response를 Bedrock 평가에 전달하는 방식**을 사용한다.

전체 흐름:

```text
Qwen2.5
   ↓
HTML / JSON 생성
   ↓
결과 저장
   ↓
JSONL 변환
   ↓
S3
   ↓
Bedrock Evaluation
   ↓
Judge Model
   ↓
평가 결과
```

이 구조에서는 Bedrock이 Generator 역할을 할 필요가 없다.

따라서 프로젝트에서 실제 사용할 로컬 모델의 결과를 그대로 평가할 수 있다.

---

# 12. JSON 방식 평가

JSON 방식은 LLM이 Page Schema 또는 Modification Command를 얼마나 정확하게 생성하는지 평가한다.

평가 영역:

```text
JSON 방식
├── Schema Compliance
├── Requirement Accuracy
├── Content Accuracy
└── Modification Accuracy
```

---

# 13. JSON — Schema Compliance

JSON 구조가 프로젝트에서 정의한 Schema를 준수하는지 평가한다.

평가 항목:

```text
JSON 파싱 가능 여부
필수 필드 존재 여부
필드 타입
허용되지 않은 필드
Component 구조
중첩 구조
```

예:

```text
0점
→ JSON 자체가 깨짐

1점
→ 대부분의 Schema를 준수하지 않음

2점
→ 일부 구조만 준수

3점
→ 주요 구조는 준수하지만 오류 존재

4점
→ 거의 모든 구조를 준수

5점
→ Schema를 완전히 준수
```

---

# 14. JSON — Requirement Accuracy

사용자의 요구사항을 얼마나 정확하게 반영했는지 평가한다.

평가 대상:

```text
이벤트 목적
기간
혜택
대상
CTA
명시된 수치
사용자가 제공하지 않은 정보의 임의 생성 여부
```

예를 들어 사용자가:

```text
7월 1일 ~ 7월 31일
```

이라고 명시했는데:

```text
7월 1일 ~ 8월 31일
```

로 생성하면 감점 대상이다.

---

# 15. JSON — Content Accuracy

생성된 콘텐츠가 사용자 요구사항과 의미적으로 일치하는지 평가한다.

평가 대상:

```text
이벤트 제목
설명
혜택 내용
CTA 문구
이벤트 대상
```

단순히 문자열이 같은지만 비교하지 않는다.

예:

```text
요구사항:
데이터 10GB 추가 제공

생성:
추가 데이터 10GB 제공
```

은 의미적으로 동일한 것으로 평가할 수 있다.

---

# 16. JSON — Modification Accuracy

수정 요청이 정확하게 반영되었는지 평가한다.

예:

```text
Hero 제목만 변경해줘.
```

평가:

```text
Hero 제목 변경
+
다른 Component 유지
```

가 제대로 이루어졌는지 확인한다.

---

# 17. HTML 방식 평가

HTML 방식은 다음 영역을 평가한다.

```text
HTML 방식
├── HTML Structure
├── Requirement Accuracy
├── Content Accuracy
├── Behavior Correctness
└── Modification Accuracy
```

추가적으로 안전성은 코드 기반 검증으로 측정한다.

---

# 18. HTML — Structure Compliance

HTML 구조가 프로젝트의 Block 규칙을 준수하는지 평가한다.

평가 항목:

```text
<section> 존재
data-block 존재
필수 Block 존재
Block 구조
최소 항목 수
불필요한 Block 생성 여부
서버 소유 Block 생성 여부
```

예:

```html
<section data-block="hero">
    ...
</section>
```

올바른 Block 구조인지 확인한다.

---

# 19. HTML — Requirement Accuracy

JSON 방식과 동일한 사용자 요구사항을 평가한다.

```text
이벤트 기간
혜택
대상
수치
이벤트 목적
CTA
```

JSON과 HTML의 차이와 관계없이 **사용자 요구사항을 얼마나 잘 반영했는가**를 평가한다.

따라서 이 지표는 두 방식 간 공통 비교 지표로 사용할 수 있다.

---

# 20. HTML — Content Accuracy

HTML 내부의 콘텐츠가 사용자 요구사항과 의미적으로 일치하는지 평가한다.

예:

```html
<h1>여름 데이터 대방출</h1>
```

```html
<p>7월 한 달간 추가 데이터를 제공합니다.</p>
```

등의 내용을 평가한다.

HTML 태그 자체의 구조는 별도의 Structure 평가에서 처리한다.

---

# 21. HTML — Behavior Correctness

`data-behavior`가 사용자 요구사항에 맞는지 평가한다.

예:

```html
<button
    data-behavior='{
        "event": "click",
        "action": "open-modal",
        "target": "coupon-modal"
    }'>
    쿠폰 받기
</button>
```

평가 항목:

```text
event
action
target
method
endpoint
actions 순서
```

특히 요구사항에 없는 동작을 임의로 추가했는지 확인한다.

---

# 22. HTML — Modification Accuracy

HTML 수정에서는 요청한 Block만 변경되었는지를 평가한다.

예:

```text
요청:
Hero 제목만 변경

정상:
hero 제목 변경
benefit 유지
cta 유지
footer 유지
```

평가 항목:

```text
대상 Block 변경
비대상 Block 유지
data-block 유지
data-slot 유지
기존 속성 유지
```

---

# 23. Deterministic Evaluation

모든 평가를 LLM Judge에게 맡기지 않는다.

현재 Java 구현으로 확정적으로 판단할 수 있는 항목은 코드로 평가한다.

```text
LLM Output
    ↓
Deterministic Validator
    ↓
Pass / Fail
```

예:

```text
JSON Parse
Schema
data-block
data-slot
HTML 구조
placeholder
허용 태그
CSS
Behavior JSON
```

---

# 24. HTML 방식의 코드 기반 평가

현재 `BlockValidator`를 이용하여 다음을 측정한다.

```text
validateGenerated()
validateEdited()
checkSlots()
sanitizeGenerated()
sanitizeEdited()
```

예:

```text
Generation
→ validateGenerated()

Edit
→ validateEdited()

Slot
→ checkSlots()

Security
→ sanitize()
```

이를 통해 Judge의 주관적 판단을 최소화한다.

---

# 25. LLM Judge Evaluation

LLM Judge는 코드로 쉽게 판단하기 어려운 의미적 품질을 평가한다.

```text
Deterministic
→ 구조 / 형식 / 안전성

LLM Judge
→ 의미 / 요구사항 / 콘텐츠 품질
```

Judge 평가 대상:

```text
요구사항 반영
내용 정확성
의미적 일치
수정 의도 반영
Behavior 의미적 정확성
```

---

# 26. 최종 평가 구조

최종적으로 다음 구조를 사용한다.

```text
                    LLM Output
                        │
             ┌──────────┴──────────┐
             ↓                     ↓
      Deterministic            LLM Judge
       Evaluation              Evaluation
             │                     │
             ↓                     ↓
       Pass / Fail              Score
             │                     │
             └──────────┬──────────┘
                        ↓
                 Benchmark Result
```

---

# 27. 평가 지표 정리

| 평가 항목                    | JSON | HTML | 평가 방식        |
| ------------------------ | :--: | :--: | ------------ |
| Requirement Accuracy     |   O  |   O  | Judge        |
| Content Accuracy         |   O  |   O  | Judge        |
| Schema Compliance        |   O  |   -  | Code + Judge |
| HTML Structure           |   -  |   O  | Code + Judge |
| Behavior Correctness     |  O*  |   O  | Code + Judge |
| Modification Accuracy    |   O  |   O  | Code + Judge |
| `data-slot` Preservation |   -  |   O  | Code         |
| HTML Sanitization        |   -  |   O  | Code         |
| JSON Parse               |   O  |  O*  | Code         |
| Placeholder Detection    |   O  |   O  | Code         |

`*` 프로젝트의 JSON 방식에서 Behavior를 Page Schema에 포함하는 경우에 해당한다.

---

# 28. 평가 점수의 분리

JSON과 HTML의 점수를 하나의 단일 점수로만 합치지 않는다.

다음과 같이 결과를 보관한다.

```text
JSON
├── Requirement Accuracy
├── Content Accuracy
├── Schema Compliance
└── Modification Accuracy

HTML
├── Requirement Accuracy
├── Content Accuracy
├── HTML Structure
├── Behavior Correctness
└── Modification Accuracy
```

그리고 별도로:

```text
Deterministic
├── Validation Pass Rate
├── Sanitization Violation Rate
├── Slot Preservation Rate
└── Parse Success Rate
```

를 기록한다.

---

# 29. Benchmark 결과 예시

최종 결과는 다음과 같이 정리할 수 있다.

| Metric                      | JSON | HTML |
| --------------------------- | ---: | ---: |
| Requirement Accuracy        |    - |    - |
| Content Accuracy            |    - |    - |
| Structure Compliance        |    - |    - |
| Modification Accuracy       |    - |    - |
| Behavior Correctness        |    - |    - |
| Validation Pass Rate        |    - |    - |
| Parse Success Rate          |    - |    - |
| Sanitization Violation Rate |    - |    - |
| 평균 생성 시간                    |    - |    - |
| 평균 출력 토큰                    |    - |    - |

실제 수치는 동일한 테스트 케이스를 실행한 후 기록한다.

---

# 30. 테스트 케이스별 결과 관리

단순 평균값만 저장하지 않고 테스트 케이스별 결과도 보관한다.

예:

```json
{
  "testCaseId": "TC-001",
  "json": {
    "requirementAccuracy": 5,
    "contentAccuracy": 4,
    "schemaCompliance": 5,
    "validation": true
  },
  "html": {
    "requirementAccuracy": 5,
    "contentAccuracy": 4,
    "structureCompliance": 5,
    "behaviorCorrectness": 4,
    "validation": true
  }
}
```

이를 통해 특정 테스트 케이스에서 어느 방식이 실패했는지 추적할 수 있다.

---

# 31. JSONL 파일 구성

권장 디렉터리:

```text
bedrock/
│
├── datasets/
│   ├── generation.jsonl
│   ├── edit.jsonl
│   └── behavior.jsonl
│
├── outputs/
│   ├── json/
│   └── html/
│
└── results/
    ├── json/
    └── html/
```

S3에서는 다음과 같이 구성할 수 있다.

```text
s3://<bucket>/
├── datasets/
├── outputs/
└── results/
```

---

# 32. JSON 방식의 Bedrock 평가 흐름

```text
Test Case
    ↓
동일 Prompt
    ↓
JSON LLM
    ↓
Page Schema
    ↓
Deterministic Validation
    ↓
Bedrock Judge
    ↓
JSON Evaluation Result
```

---

# 33. HTML 방식의 Bedrock 평가 흐름

```text
Test Case
    ↓
동일 Prompt
    ↓
HTML LLM
    ↓
HTML + data-behavior
    ↓
BlockValidator
    ↓
BehaviorValidator
    ↓
Sanitizer
    ↓
Bedrock Judge
    ↓
HTML Evaluation Result
```

---

# 34. 두 방식의 공정한 비교

두 방식의 비교에서 가장 중요한 조건은 **입력 조건을 동일하게 유지하는 것**이다.

```text
동일
├── Test Case
├── Prompt
├── 요구사항
├── LLM
├── 모델 파라미터
├── 테스트 횟수
└── 평가 Judge

차이
├── JSON 방식 → Page Schema
└── HTML 방식 → HTML + Behavior
```

따라서 출력 형식에 따른 차이를 비교할 수 있다.

---

# 35. 권장 평가 실험

1차 실험:

```text
Qwen2.5 7B
```

동일 모델로:

```text
JSON Prompt
vs
HTML Prompt
```

를 비교한다.

2차 실험:

```text
Qwen2.5 14B
```

동일한 조건에서 반복한다.

최종적으로:

```text
Model
 ×
Output Format
 ×
Task
```

형태로 결과를 정리한다.

예:

```text
Qwen 7B
 ├── JSON
 │   ├── Generation
 │   └── Edit
 │
 └── HTML
     ├── Generation
     └── Edit

Qwen 14B
 ├── JSON
 └── HTML
```

---

# 36. 평가 시 주의사항

## 36.1 HTML 문자열 완전 일치 비교 금지

HTML은 표현 방법이 다양하기 때문에 다음과 같은 단순 비교는 적절하지 않다.

```text
Generated HTML == Reference HTML
```

대신:

```text
HTML 구조
요구사항
콘텐츠
Behavior
```

를 분리해서 평가한다.

---

## 36.2 JSON 문자열 완전 일치 비교 금지

JSON 역시 필드 순서나 표현 방법이 다를 수 있다.

따라서 가능하면 JSON Parse 후 구조화된 형태로 비교한다.

```text
Raw JSON
 ↓
Parser
 ↓
Object
 ↓
Schema Validation
```

---

## 36.3 Judge에게 구조 검증을 전부 맡기지 않는다

예:

```text
data-block이 존재하는가?
```

는 Judge보다 Java Validator가 더 적합하다.

Judge는 다음에 집중한다.

```text
이 Block이 사용자의 요구사항에 적절한가?
```

---

# 37. 최종 평가 아키텍처

```text
                         Test Cases
                             │
                 ┌───────────┴───────────┐
                 ↓                       ↓
             JSON LLM                 HTML LLM
                 ↓                       ↓
            Page Schema             HTML + Behavior
                 │                       │
                 ↓                       ↓
         JSON Validator          BlockValidator
                                         │
                                  BehaviorValidator
                                         │
                 │                       ↓
                 │                   Sanitizer
                 │                       │
                 └───────────┬───────────┘
                             ↓
                    Deterministic Result
                             │
                             ↓
                       Bedrock Judge
                             │
                             ↓
                     Semantic Evaluation
                             │
                             ↓
                     Benchmark Report
```

---

# 38. 최종 목표

본 평가의 목적은 단순히 **JSON과 HTML 중 어느 쪽의 점수가 높은지를 판단하는 것**이 아니다.

각 방식에서 다음 요소가 어떻게 달라지는지 분석하는 것이 목적이다.

```text
생성 정확성
구조 준수
수정 정확성
행동 정의
검증 실패율
보안 위반율
생성 시간
출력 크기
모델 크기에 따른 성능 변화
```

이를 통해 최종적으로 다음을 판단할 수 있는 데이터를 확보한다.

```text
Qwen 7B에서
JSON 방식과 HTML 방식의 차이

Qwen 14B에서
JSON 방식과 HTML 방식의 차이

Generation과 Edit에서
각 방식의 차이
```

즉, **Bedrock은 의미적 품질을 평가하고, 프로젝트의 Validator는 구조적 정확성을 평가하는 이중 평가 구조**를 사용한다.
