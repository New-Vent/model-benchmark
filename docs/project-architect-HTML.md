# AI 이벤트 페이지 시스템 — HTML 방식 구현 문서

## 1. 개요

HTML 방식은 LLM이 이벤트 페이지의 **HTML을 직접 생성하거나 수정**하는 방식이다.

JSON 방식에서 Page Schema를 기준으로 페이지를 구성하는 것과 달리, HTML 방식에서는 **HTML 자체가 페이지의 주요 표현(Primary Representation)** 이 된다.

다만 모든 것을 LLM에게 자유롭게 생성하도록 하지 않는다.

* HTML 구조는 `data-block`을 통해 영역을 식별한다.
* 서버가 관리하는 동적 데이터 영역은 `data-slot`으로 표시한다.
* 사용자 인터랙션은 `data-behavior`에 JSON 형태의 동작 정보를 선언한다.
* 서버는 LLM 결과를 검증하고 정제한다.
* 실제 동작은 공통 Runtime JavaScript가 수행한다.
* 임의의 JavaScript를 LLM이 직접 생성하지 못하도록 제한한다.

전체 구조는 다음과 같다.

```text
사용자 요구사항
      ↓
    Router
      ↓
     LLM
      ↓
 HTML + Behavior Metadata
      ↓
    Extract
      ↓
   Validator
      ↓
   Sanitizer
      ↓
     Merge
      ↓
  최종 HTML
      ↓
 Browser DOM
      ↓
 Runtime JavaScript
```

---

# 2. HTML 방식의 기본 원칙

HTML 방식에서는 다음 원칙을 적용한다.

### 2.1 HTML을 주요 페이지 표현으로 사용

LLM은 다음과 같은 HTML을 직접 생성한다.

```html
<section data-block="hero">
    <h1>여름 데이터 대방출</h1>
    <p>이번 여름 데이터 걱정 없이</p>
</section>

<section data-block="cta">
    <a href="#" class="btn">참여하기</a>
</section>
```

서버는 해당 HTML을 파싱하고 검증한 뒤 최종 페이지에 반영한다.

---

### 2.2 자유로운 HTML 생성은 허용하지 않는다

HTML 방식이라고 해서 LLM이 모든 HTML, CSS, JavaScript를 자유롭게 생성하는 것은 아니다.

LLM의 역할은 다음 범위로 제한한다.

```text
HTML 구조
텍스트 콘텐츠
허용된 스타일
Behavior Metadata
```

다음과 같은 요소는 서버에서 제한한다.

```text
임의 JavaScript
외부 Script 삽입
위험한 URL
임의 API Endpoint
허용되지 않은 HTML 태그
허용되지 않은 CSS
```

---

# 3. HTML 구성 요소

HTML 방식의 이벤트 페이지는 크게 다음 세 가지 메타데이터를 사용한다.

```text
data-block
data-slot
data-behavior
```

각각의 역할은 다르다.

| 속성              | 담당 영역  | 목적                  |
| --------------- | ------ | ------------------- |
| `data-block`    | 페이지 구조 | HTML 영역 식별          |
| `data-slot`     | 서버 데이터 | 서버가 값을 삽입할 위치       |
| `data-behavior` | 사용자 동작 | Runtime에서 실행할 동작 선언 |

---

# 4. data-block

## 4.1 개념

`data-block`은 이벤트 페이지를 구성하는 각각의 영역을 식별하기 위한 속성이다.

```html
<section data-block="hero">
    ...
</section>
```

```html
<section data-block="benefit">
    ...
</section>
```

```html
<section data-block="cta">
    ...
</section>
```

각 Block은 `Block` Registry에서 정의한다.

```text
Block Registry
    ↓
Block 목록
    ↓
PromptBuilder
    ↓
LLM Prompt
    ↓
BlockValidator
```

따라서 LLM에게 허용되는 페이지 영역과 서버가 소유하는 영역을 중앙에서 관리할 수 있다.

---

# 5. Block Registry

Block Registry는 페이지 영역의 정의를 담당한다.

각 Block은 다음 정보를 가질 수 있다.

```text
key
description
source
required
shape
selector
must
minItems
```

예시:

```text
hero
benefit
event-info
cta
footer
```

Block의 역할은 단순한 HTML 태그 정의가 아니다.

```text
Block
 ├── LLM이 생성 가능한 영역인지
 ├── 필수 영역인지
 ├── 어떤 HTML 구조를 가져야 하는지
 ├── 최소 몇 개의 항목이 필요한지
 └── 어떤 Selector로 식별하는지
```

를 정의한다.

---

# 6. data-slot

## 6.1 개념

`data-slot`은 **서버가 소유하는 데이터 삽입 지점**이다.

예를 들어 이벤트 페이지에 서버가 관리하는 사용자 정보나 실시간 데이터를 삽입해야 하는 경우 다음과 같이 표시할 수 있다.

```html
<section data-block="hero">
    <h1 data-slot="event-title"></h1>
    <p data-slot="event-description"></p>
</section>
```

여기서 `data-slot`은 LLM이 관리하는 페이지 콘텐츠가 아니다.

```text
LLM
 ↓
HTML 구조 생성
 ↓
Server
 ↓
data-slot 값 삽입
```

구조를 사용한다.

---

## 6.2 data-slot의 소유권

`data-slot`은 서버가 소유한다.

따라서 LLM은 다음 행위를 하면 안 된다.

```text
기존 data-slot 삭제
새로운 data-slot 생성
data-slot 이름 변경
data-slot 내부 서버 데이터 임의 변경
```

수정 요청이 들어왔을 때 기존 슬롯을 그대로 유지해야 한다.

---

## 6.3 생성과 수정의 차이

### 생성

새로운 페이지를 만드는 경우에는 서버가 아직 `data-slot`을 삽입하지 않았으므로 LLM에게 `data-slot`을 알려줄 필요가 없다.

```text
LLM
 ↓
HTML 생성
 ↓
Server가 필요한 slot 삽입
```

### 수정

기존 HTML에는 이미 `data-slot`이 존재할 수 있다.

따라서 수정 Prompt에서는 다음 규칙을 전달한다.

```text
data-slot이 붙은 태그는 삭제하지 않는다.
태그와 속성을 그대로 유지한다.
data-slot을 새로 생성하지 않는다.
```

그리고 서버에서 다시 검증한다.

---

# 7. data-behavior

## 7.1 개념

`data-behavior`는 HTML 요소에 필요한 사용자 인터랙션을 JSON 형태로 선언하기 위한 메타데이터다.

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

HTML 안에 JSON을 포함하지만, 이것은 Page Schema가 아니다.

목적은 **HTML 요소의 동작을 선언하는 것**이다.

---

# 8. Behavior Metadata의 역할

HTML 방식에서 LLM이 직접 JavaScript를 생성하게 만들면 다음과 같은 문제가 발생할 수 있다.

```javascript
fetch("https://example.com/...");
```

또는

```javascript
<script>
    ...
</script>
```

따라서 LLM에게 임의 JavaScript를 생성하도록 하지 않는다.

대신 다음과 같은 선언만 허용한다.

```json
{
    "event": "click",
    "action": "open-modal",
    "target": "coupon-modal"
}
```

실제 동작은 Runtime JavaScript가 담당한다.

```text
LLM
 ↓
Behavior Metadata
 ↓
Validator
 ↓
Runtime JavaScript
 ↓
실제 동작
```

---

# 9. Behavior 실행 구조

Runtime JavaScript는 `data-behavior`를 읽는다.

```javascript
const behavior = JSON.parse(
    button.dataset.behavior
);

executeBehavior(behavior);
```

예를 들어 다음 HTML이 있다.

```html
<button
    data-behavior='{
        "event": "click",
        "action": "open-modal",
        "target": "coupon-modal"
    }'>
    참여하기
</button>
```

Runtime은 다음과 같이 처리한다.

```text
click
 ↓
open-modal
 ↓
coupon-modal
 ↓
Modal 표시
```

---

# 10. 복합 동작

하나의 이벤트에서 여러 동작을 순차적으로 실행할 수도 있다.

예:

```html
<button
    data-behavior='{
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
    }'>
    쿠폰 받기
</button>
```

실행 흐름:

```text
사용자 클릭
    ↓
POST /api/coupons/issue
    ↓
성공
    ↓
쿠폰 성공 Modal 표시
```

단, `api-request`의 Endpoint는 서버에서 허용 목록을 검증해야 한다.

---

# 11. Behavior 보안 정책

`data-behavior`는 JSON이라고 해서 모든 값을 허용하지 않는다.

서버는 다음 항목을 검증한다.

```text
event
action
target
method
endpoint
```

예를 들어 Action은 다음과 같이 제한할 수 있다.

```text
open-modal
close-modal
scroll
show
hide
api-request
redirect
```

허용되지 않은 Action은 거부한다.

```text
unknown-action
execute-script
eval
custom-js
```

등은 허용하지 않는다.

---

# 12. API Endpoint 검증

`api-request` 역시 임의 Endpoint를 허용하지 않는다.

예:

```json
{
    "type": "api-request",
    "method": "POST",
    "endpoint": "/api/coupons/issue"
}
```

서버는 다음을 확인한다.

```text
HTTP Method 허용 여부
Endpoint 허용 여부
외부 URL 여부
Protocol 위험 여부
```

예를 들어 다음과 같은 값은 허용하지 않는다.

```text
javascript:
data:
http://external-site.com
https://unknown-site.com
```

프로젝트에서 필요한 API만 Allowlist로 관리한다.

---

# 13. Router JSON

HTML 방식에서도 JSON은 사용된다.

그러나 이것은 페이지 자체를 표현하는 JSON이 아니다.

Router가 사용하는 **제어용 JSON(Control-plane JSON)** 이다.

현재 Router는 다음과 같은 결과를 반환한다.

```json
{
    "op": "EDIT",
    "target": "hero"
}
```

지원하는 동작은 다음과 같다.

```text
EDIT
ADD
DELETE
STYLE
```

---

# 14. Router와 Behavior의 차이

두 JSON은 목적이 다르다.

| 구분    | Router JSON | Behavior Metadata    |
| ----- | ----------- | -------------------- |
| 목적    | 사용자 요청 분류   | 페이지 동작 정의            |
| 위치    | LLM 응답      | HTML 내부              |
| 대상    | 서버 처리 로직    | 브라우저 Runtime         |
| 예시    | `EDIT hero` | `click → open-modal` |
| 실행 시점 | HTML 처리 전   | 브라우저 실행 시            |

따라서 HTML 방식에서도 JSON을 사용하지만,

> JSON이 페이지의 Canonical Representation인 것은 아니다.

HTML이 페이지의 주요 표현이고 JSON은 Router와 Behavior를 위한 보조 데이터다.

---

# 15. PromptBuilder

현재 PromptBuilder는 생성, 수정, 라우팅 Prompt를 담당한다.

구조:

```text
PromptBuilder
 ├── generate()
 ├── edit(Block)
 └── router()
```

---

## 15.1 생성 Prompt

`generate()`는 전체 이벤트 페이지를 생성하도록 LLM에 지시한다.

주요 규칙:

```text
<section data-block="이름"> 사용
<html>, <head>, <body> 금지
코드블록 금지
설명 금지
필요한 Block 생성
서버 소유 Block 생성 금지
placeholder 금지
임의 날짜 생성 금지
임의 혜택/수치 생성 금지
```

예:

```html
<section data-block="hero">
    <h1>여름 데이터 대방출</h1>
    <p>이번 여름 데이터 걱정 없이</p>
</section>
```

---

# 16. 수정 Prompt

수정에서는 전체 페이지가 아니라 특정 Block만 LLM에게 전달한다.

예:

```text
사용자 요청
 ↓
Router
 ↓
EDIT
 ↓
target = hero
 ↓
PromptBuilder.edit(hero)
 ↓
LLM
```

LLM은 다음 형태만 반환한다.

```html
<section data-block="hero">
    ...
</section>
```

다른 Block은 생성하지 않는다.

---

# 17. 수정 시 data-slot 보호

수정 Prompt에서는 기존 `data-slot`을 보호한다.

```text
data-slot이 붙은 태그는 지우지 않는다.
태그와 속성을 그대로 둔다.
그 안의 내용을 채우지 않는다.
data-slot을 새로 만들지 않는다.
```

이 규칙은 Prompt만으로 끝나지 않는다.

서버에서도 `checkSlots()`를 사용하여 검증한다.

```text
수정 전 slot 목록
        ↓
수정 후 slot 목록
        ↓
비교
```

---

# 18. HTML 추출

LLM이 다음과 같이 출력할 가능성이 있기 때문에 별도의 HTML 추출 단계가 존재한다.

````text
```html
<section ...>
...
</section>
````

````

`extract()`는 코드펜스를 제거하고 HTML 부분만 추출한다.

```java
String t = raw
        .replace("```html", "")
        .replace("```", "");
````

이후 첫 번째 `<`부터 마지막 `>`까지 추출한다.

---

# 19. HTML Validator

LLM 출력은 신뢰하지 않는다.

따라서 HTML을 서버에서 검증한다.

```text
LLM Output
    ↓
BlockValidator
    ↓
Validation Result
```

검증 항목:

```text
HTML 존재 여부
section 존재 여부
data-block 존재 여부
필수 Block 존재 여부
Block 구조
최소 항목 수
서버 소유 Block 생성 여부
placeholder 존재 여부
```

---

# 20. 생성 결과 검증

`validateGenerated()`는 전체 페이지 생성 결과를 검증한다.

대표적인 실패 유형:

```text
no_html
no_section
no_data_block
lost_hero
lost_benefit
wrote_server_block
placeholder
```

예를 들어 필수 `hero` 영역이 없다면:

```text
lost_hero
```

가 발생한다.

---

# 21. HTML 구조 검증

각 Block에는 필요한 HTML 형태를 정의할 수 있다.

예:

```text
hero
  → h1 필요

benefit
  → li 최소 3개

cta
  → a 또는 button 필요
```

따라서 단순히 HTML이 존재하는지만 검사하지 않는다.

```text
Block 존재
 +
필수 HTML 구조
 +
최소 항목 수
```

를 함께 검증한다.

---

# 22. 수정 결과 검증

수정에서는 `validateEdited()`를 사용한다.

검증 내용:

```text
수정 대상 Block 존재
다른 Block 생성 여부
Block 구조
data-slot 유지 여부
```

예를 들어 `hero`만 수정하도록 요청했는데 LLM이 다음과 같이 출력하면:

```html
<section data-block="hero">
    ...
</section>

<section data-block="cta">
    ...
</section>
```

다음 오류가 발생한다.

```text
extra_cta
```

---

# 23. data-slot 검증

수정 전:

```html
<h1 data-slot="event-title"></h1>
```

수정 후:

```html
<h1></h1>
```

라면 `slot_lost_event-title` 오류가 발생한다.

반대로:

```html
<h1 data-slot="event-title"></h1>
<p data-slot="new-slot"></p>
```

처럼 새로운 Slot을 생성하면:

```text
slot_invented_new-slot
```

오류가 발생한다.

즉, Prompt와 Validator를 함께 사용한다.

```text
Prompt
 └── 모델에게 규칙 전달

Validator
 └── 실제 결과가 규칙을 지켰는지 확인
```

---

# 24. Sanitizer

Validator가 구조적인 문제를 검사한다면 Sanitizer는 HTML에서 위험하거나 허용되지 않은 요소를 제거한다.

현재 구현에서는 Jsoup의 `Safelist`를 사용한다.

```text
HTML
 ↓
Jsoup Sanitizer
 ↓
안전한 HTML
```

허용되는 HTML과 속성을 제한한다.

---

# 25. CSS Sanitizer

Inline CSS도 제한한다.

현재 허용 CSS:

```text
color
background-color
font-size
font-weight
font-style
line-height
text-align
text-decoration

padding
margin

border
border-color
border-width
border-style
border-radius
```

다음과 같은 위험한 값은 제거한다.

```text
url()
expression()
javascript:
@import
주석 기반 우회
```

따라서 LLM이 생성한 CSS를 그대로 브라우저에 전달하지 않는다.

---

# 26. data-behavior Sanitizer

`data-behavior`를 사용하는 경우 Sanitizer에서 해당 속성을 보존해야 한다.

예:

```java
.addAttributes(
    ":all",
    "style",
    "data-block",
    "class",
    "data-behavior"
)
```

그러나 단순히 속성을 보존하는 것만으로는 충분하지 않다.

Sanitizer 이후 별도의 Behavior 검증이 필요하다.

```text
data-behavior
      ↓
JSON Parse
      ↓
Schema 검증
      ↓
Action Allowlist
      ↓
Endpoint Allowlist
```

---

# 27. BehaviorValidator

Behavior 검증은 별도의 `BehaviorValidator`로 분리하는 것을 권장한다.

예:

```text
BehaviorValidator
 ├── validateJson()
 ├── validateEvent()
 ├── validateAction()
 ├── validateTarget()
 ├── validateMethod()
 └── validateEndpoint()
```

역할은 HTML Validator와 분리한다.

```text
BlockValidator
    ↓
HTML 구조 검증

BehaviorValidator
    ↓
Behavior JSON 검증
```

---

# 28. HTML Merge

수정 요청에서는 LLM이 전체 HTML을 반환하지 않는다.

대상 Block만 반환한다.

예:

```html
<section data-block="hero">
    ...
</section>
```

서버는 기존 문서에서 동일한 Block을 찾아 교체한다.

```text
현재 HTML
    ↓
target Block 탐색
    ↓
LLM 결과 Block
    ↓
기존 Block replace
    ↓
최종 HTML
```

현재 `merge()`가 이 역할을 담당한다.

---

# 29. Merge의 중요성

전체 HTML을 LLM에게 다시 생성시키지 않는 이유는 페이지 전체가 불필요하게 변경되는 것을 방지하기 위해서다.

예를 들어:

```text
기존 페이지

hero
benefit
event-info
cta
footer
```

사용자가:

```text
hero 문구만 변경해줘
```

라고 요청하면,

```text
LLM
 ↓
hero만 생성
 ↓
Validator
 ↓
Merge
 ↓
기존 hero 교체
```

한다.

다른 Block은 유지된다.

---

# 30. 전체 생성 Pipeline

전체 페이지 생성은 다음과 같다.

```text
사용자 요구사항
      ↓
PromptBuilder.generate()
      ↓
LLM
      ↓
Raw HTML
      ↓
extract()
      ↓
validateGenerated()
      ↓
sanitizeGenerated()
      ↓
최종 HTML
```

필요한 서버 소유 데이터가 있다면 이후 `data-slot`을 통해 서버에서 삽입한다.

---

# 31. 페이지 수정 Pipeline

수정은 다음과 같다.

```text
사용자 수정 요청
      ↓
router()
      ↓
{
    "op": "EDIT",
    "target": "hero"
}
      ↓
현재 hero HTML 추출
      ↓
PromptBuilder.edit(hero)
      ↓
LLM
      ↓
수정된 hero HTML
      ↓
validateEdited()
      ↓
sanitizeEdited()
      ↓
merge()
      ↓
최종 HTML
```

---

# 32. Router Pipeline

Router는 페이지 HTML을 직접 생성하는 역할이 아니다.

```text
사용자 요청
      ↓
Router LLM
      ↓
JSON
```

예:

```json
{
    "op": "EDIT",
    "target": "hero"
}
```

서버는 JSON을 기반으로 실제 작업을 결정한다.

```text
EDIT
 ↓
Block 조회
 ↓
edit(Block)
 ↓
LLM
```

---

# 33. 서버와 LLM의 책임 분리

HTML 방식에서 가장 중요한 부분은 책임 분리다.

### LLM

```text
HTML 생성
텍스트 생성
HTML 구조 결정
Behavior Metadata 생성
```

### 서버

```text
Block Registry
HTML 검증
Behavior 검증
HTML Sanitization
data-slot 관리
Block Merge
API Endpoint Allowlist
최종 데이터 삽입
```

### Runtime JavaScript

```text
data-behavior 해석
Event Listener 등록
허용된 Action 실행
API 호출
Modal 표시
Scroll
DOM 조작
```

---

# 34. 전체 시스템 구조

```text
                    ┌──────────────┐
                    │    사용자     │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │    Router    │
                    │    JSON      │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │     LLM      │
                    └──────┬───────┘
                           ↓
                 HTML + Behavior Metadata
                           ↓
                    ┌──────────────┐
                    │    Extract   │
                    └──────┬───────┘
                           ↓
              ┌─────────────────────────┐
              │       Validator         │
              │                         │
              │ BlockValidator           │
              │ BehaviorValidator        │
              └───────────┬─────────────┘
                          ↓
                    ┌──────────────┐
                    │  Sanitizer   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │    Merge     │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │  Final HTML  │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │    Browser   │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ Runtime JS  │
                    └──────────────┘
```

---

# 35. 핵심 데이터 흐름

HTML 방식의 핵심 데이터 흐름은 다음과 같다.

```text
HTML
 ├── data-block
 │      └── 페이지 영역 식별
 │
 ├── data-slot
 │      └── 서버 데이터 삽입 지점
 │
 └── data-behavior
        └── Runtime 동작 정의
```

각 데이터의 소유권도 분리한다.

```text
data-block
    → Registry / Server

data-slot
    → Server

data-behavior
    → LLM 생성 가능
    → Server 검증
    → Runtime 실행
```

---

# 36. HTML 방식에서 JSON의 위치

HTML 방식에서는 JSON을 완전히 제거하지 않는다.

다만 JSON의 역할을 제한한다.

```text
┌──────────────────────────────────┐
│          HTML 방식                │
├──────────────────────────────────┤
│                                  │
│ HTML                             │
│  ├── data-block                  │
│  ├── data-slot                   │
│  └── data-behavior(JSON)         │
│                                  │
│ Router JSON                      │
│  └── 요청 처리 제어               │
│                                  │
└──────────────────────────────────┘
```

따라서 JSON 방식과 HTML 방식의 차이는

```text
JSON 방식
→ JSON이 페이지의 Canonical Representation

HTML 방식
→ HTML이 페이지의 Primary Representation
→ JSON은 Router / Behavior 등의 보조 역할
```

로 정의한다.

---

# 37. HTML 방식의 장점

### 37.1 브라우저 구조와 직접 대응

LLM 결과가 최종 HTML과 직접적으로 연결된다.

```text
LLM Output
   ↓
HTML
   ↓
DOM
```

중간의 별도 Renderer가 필요하지 않다.

### 37.2 기존 웹 기술 활용

HTML/CSS/DOM을 그대로 활용할 수 있다.

### 37.3 부분 수정이 간단하다

`data-block`을 기준으로 특정 영역만 교체할 수 있다.

### 37.4 LLM이 이해하기 쉬운 출력 형식

별도의 Page Schema 문법을 학습시키지 않아도 일반적인 HTML을 생성할 수 있다.

---

# 38. HTML 방식의 한계

### 38.1 HTML 구조 검증 필요

LLM이 잘못된 HTML 구조를 생성할 수 있다.

따라서 Validator가 필요하다.

### 38.2 Sanitization 필요

LLM 결과를 그대로 브라우저에 삽입하면 보안 문제가 발생할 수 있다.

### 38.3 Behavior 관리가 필요

HTML만으로 복잡한 동작을 표현하면 JavaScript 생성 문제가 발생한다.

따라서 `data-behavior`와 Runtime을 사용한다.

### 38.4 서버 소유 데이터 보호 필요

LLM이 `data-slot`을 변경하면 서버 데이터 처리에 문제가 발생할 수 있다.

따라서 Slot 보존 검증이 필요하다.

---

# 39. 구현 클래스 구조

현재 구현을 기준으로 다음 구조를 사용할 수 있다.

```text
com.newvent
│
├── registry
│   ├── Block.java
│   ├── PromptBuilder.java
│   ├── BlockValidator.java
│   └── BehaviorValidator.java
│
├── llm
│   └── ...
│
├── service
│   └── ...
│
└── runtime
    └── runtime.js
```

핵심 클래스의 책임은 다음과 같다.

| 클래스                 | 책임               |
| ------------------- | ---------------- |
| `Block`             | 페이지 Block 정의     |
| `PromptBuilder`     | LLM Prompt 생성    |
| `BlockValidator`    | HTML 구조 검증       |
| `BehaviorValidator` | Behavior JSON 검증 |
| `runtime.js`        | 브라우저 동작 실행       |

---

# 40. 생성과 수정의 책임 차이

| 구분              | 생성                    | 수정                 |
| --------------- | --------------------- | ------------------ |
| 대상              | 전체 페이지                | 특정 Block           |
| `data-block`    | 생성                    | 유지                 |
| `data-slot`     | 서버에서 후처리              | 반드시 유지             |
| `data-behavior` | 생성 가능                 | 필요한 경우 수정          |
| Validator       | `validateGenerated()` | `validateEdited()` |
| Sanitizer       | `sanitizeGenerated()` | `sanitizeEdited()` |
| Merge           | 필요 없음                 | `merge()`          |

---

# 41. 최종 HTML 예시

최종적으로 생성되는 페이지는 다음과 같은 구조를 가질 수 있다.

```html
<section data-block="hero">
    <h1 data-slot="event-title">
        여름 데이터 대방출
    </h1>

    <p>
        이번 여름 데이터 걱정 없이
    </p>
</section>

<section data-block="benefit">
    <ul>
        <li>데이터 추가 제공</li>
        <li>온라인 전용 혜택</li>
        <li>이벤트 기간 한정 혜택</li>
    </ul>
</section>

<section data-block="cta">
    <button
        data-behavior='{
            "event": "click",
            "action": "open-modal",
            "target": "coupon-modal"
        }'>
        참여하기
    </button>
</section>
```

이 HTML에서:

```text
data-block
→ 페이지 구조

data-slot
→ 서버 데이터

data-behavior
→ 사용자 인터랙션
```

으로 역할이 명확하게 분리된다.

---

# 42. 개발 순서

HTML 방식은 다음 순서로 구현한다.

```text
1. Block Registry
       ↓
2. PromptBuilder
       ↓
3. HTML Validator
       ↓
4. HTML Sanitizer
       ↓
5. Block Merge
       ↓
6. data-slot 처리
       ↓
7. Behavior Metadata
       ↓
8. BehaviorValidator
       ↓
9. Runtime JavaScript
       ↓
10. 생성/수정 통합
       ↓
11. LLM Benchmark
```

---

# 43. 벤치마크 범위

HTML 방식의 LLM 성능을 비교하기 위해서는 LLM이 담당하는 범위를 명확하게 고정해야 한다.

기본 벤치마크 범위:

```text
LLM
 ├── HTML 생성
 ├── HTML 수정
 └── Behavior Metadata 생성
```

서버가 담당:

```text
HTML Sanitization
HTML Validation
Block Merge
data-slot 처리
Runtime JS
```

이를 통해 LLM의 HTML 생성 및 수정 능력을 독립적으로 평가할 수 있다.

---

# 44. 평가 항목

HTML 생성 결과는 다음 항목으로 평가할 수 있다.

### 구조 정확성

```text
필수 Block 존재
data-block 정확성
HTML 구조 준수
최소 항목 수
```

### 콘텐츠 정확성

```text
요청 내용 반영
주어진 날짜 사용
주어진 혜택 사용
임의 정보 생성 여부
placeholder 존재 여부
```

### 수정 정확성

```text
요청한 Block만 수정
다른 Block 보존
data-slot 보존
기존 속성 보존
```

### Behavior 정확성

```text
event 정확성
action 정확성
target 정확성
endpoint 정확성
허용되지 않은 동작 생성 여부
```

### 안전성

```text
Script 삽입
위험한 URL
허용되지 않은 HTML
허용되지 않은 CSS
임의 API 호출
```

---

# 45. HTML 방식 최종 구조

최종적으로 HTML 방식은 다음 구조로 정의한다.

```text
                    LLM
                     │
          ┌──────────┴──────────┐
          │                     │
      HTML 생성             Behavior
          │                   Metadata
          └──────────┬──────────┘
                     ↓
                  Validator
                     ↓
                  Sanitizer
                     ↓
              Server-side Merge
                     ↓
                 Final HTML
                     ↓
                  Browser
                     ↓
               Runtime JS
```

핵심 원칙은 다음과 같다.

> **HTML은 페이지의 주요 표현이고, `data-block`은 구조를 식별하며, `data-slot`은 서버 데이터를 보호하고, `data-behavior`는 사용자 동작을 선언한다. LLM의 결과는 서버에서 반드시 검증·정제한 뒤 사용한다.**

이 구조를 통해 HTML 방식은 HTML의 자유로운 표현력을 유지하면서도 서버가 구조, 데이터, 동작에 대한 통제권을 유지할 수 있다.
