# AI 이벤트 페이지 시스템 — 추가 구현 범위

## 1. 개요

본 시스템은 LLM이 HTML/CSS/JavaScript를 직접 생성하는 방식이 아니라, **페이지 구조와 변경 의도를 구조화된 데이터로 생성**하고 서버가 실제 HTML/CSS 및 동작을 생성하는 방식으로 구현한다.

전체적인 처리 구조는 다음과 같다.

```text
사용자 요구사항
      ↓
     LLM
      ↓
Page Schema / Modification Command
      ↓
    Validator
      ↓
 Operation Engine
      ↓
   Page Schema
      ↓
    Renderer
      ↓
 HTML + CSS + Behavior
      ↓
   Browser DOM
      ↓
  Runtime JavaScript
```

이를 통해 LLM의 자유로운 HTML/JS 생성에 따른 오류를 줄이고, 서버에서 페이지 구조와 동작을 통제할 수 있다.

---

# 2. 추가해야 하는 핵심 기능

프로젝트에서 추가로 구현해야 하는 핵심 영역은 다음과 같다.

| 영역                   | 역할                                           |
| -------------------- | -------------------------------------------- |
| Page Schema          | 페이지 구조와 상태를 JSON으로 표현                        |
| Renderer             | Page Schema를 HTML/CSS로 변환                    |
| Behavior Runtime     | 페이지의 공통 UI 동작 처리                             |
| Modification Command | 사용자의 페이지 수정 요청을 구조화                          |
| Operation Engine     | Modification Command를 실제 페이지에 적용             |
| Validator            | LLM 결과 및 변경 요청 검증                            |
| LLM 연동               | 자연어를 Page Schema 또는 Modification Command로 변환 |

---

# 3. Page Schema

## 3.1 목적

Page Schema는 시스템에서 사용하는 **페이지의 기준 데이터(Canonical State)**이다.

HTML이나 브라우저의 DOM을 원본으로 사용하지 않고 Page Schema를 원본으로 관리한다.

```text
Page Schema
    ↓
Renderer
    ↓
HTML
    ↓
Browser
    ↓
DOM
```

즉, DOM은 Page Schema를 렌더링한 결과이며 원본 데이터가 아니다.

---

## 3.2 기본 구조

```json
{
  "type": "page",
  "version": "1.0",
  "metadata": {
    "title": "2026 여름 이벤트"
  },
  "theme": {},
  "sections": [
    {
      "type": "section",
      "id": "section-hero",
      "variant": "hero",
      "layout": {},
      "style": {},
      "components": [
        {
          "type": "heading",
          "id": "hero-title",
          "content": {
            "text": "2026 여름 대축제"
          }
        },
        {
          "type": "text",
          "id": "hero-description",
          "content": {
            "text": "올여름 특별한 혜택을 만나보세요."
          }
        },
        {
          "type": "button",
          "id": "hero-button",
          "content": {
            "text": "지금 참여하기"
          },
          "behavior": {
            "event": "click",
            "action": "open-modal",
            "target": "event-info-modal"
          }
        }
      ]
    }
  ]
}
```

---

# 4. Page Schema 구성

## 4.1 Page

페이지 전체를 나타낸다.

```text
Page
├── metadata
├── theme
└── sections
```

---

## 4.2 Section

페이지의 주요 영역을 나타낸다.

```text
Page
├── Hero Section
├── Promotion Section
├── Product Section
├── Event Section
├── FAQ Section
└── Footer Section
```

대표적인 `variant`는 다음과 같이 구성할 수 있다.

```text
hero
intro
promotion
product
event
feature
benefit
banner
gallery
steps
timeline
countdown
review
faq
form
cta
notice
location
social
footer
```

`variant`는 디자인의 세부적인 형태보다는 **Section의 의미와 역할**을 나타내도록 한다.

예를 들어 다음과 같이 사용하지 않는다.

```text
hero_center
hero_left
hero_fullscreen
```

대신:

```json
{
  "variant": "hero",
  "layout": {
    "align": "center",
    "justify": "center"
  }
}
```

처럼 `variant`와 `layout`의 역할을 분리한다.

---

# 5. Component

Section 내부에 실제 UI 요소를 배치한다.

```text
Section
└── Components
    ├── Heading
    ├── Text
    ├── Image
    ├── Button
    ├── Card
    ├── Input
    └── ...
```

각 Component는 기본적으로 다음 정보를 가진다.

```text
Component
├── type
├── id
├── content
├── attributes
├── style
└── behavior
```

---

# 6. Component ID

각 Component에는 안정적인 `id`를 부여한다.

```json
{
  "type": "button",
  "id": "hero-button"
}
```

예:

```text
hero-title
hero-description
hero-button
product-card-1
product-card-2
faq-1
coupon-button
```

ID는 Modification Command에서 특정 Component를 찾는 데 사용한다.

따라서 LLM이 전체 HTML을 분석하여 수정할 필요 없이 다음과 같이 정확한 대상을 지정할 수 있다.

```text
hero-button
product-card-2
faq-1
```

---

# 7. Theme

페이지 전체에서 공통으로 사용하는 디자인 요소를 정의한다.

```json
{
  "theme": {
    "colors": {
      "primary": "#2563EB",
      "secondary": "#F59E0B",
      "background": "#FFFFFF",
      "surface": "#F9FAFB",
      "text": "#111827",
      "muted": "#6B7280"
    },
    "typography": {
      "fontFamily": "Pretendard",
      "headingWeight": "700",
      "bodyWeight": "400"
    },
    "spacing": {
      "sm": "8px",
      "md": "16px",
      "lg": "32px",
      "xl": "64px"
    },
    "radius": {
      "sm": "6px",
      "md": "12px",
      "lg": "20px"
    }
  }
}
```

Component의 Style은 가능한 한 직접적인 CSS 값보다 Theme Token을 사용한다.

```json
{
  "style": {
    "backgroundColor": "primary",
    "padding": "xl",
    "borderRadius": "md"
  }
}
```

이를 통해 LLM이 임의의 CSS를 생성하는 범위를 줄인다.

---

# 8. Renderer

## 8.1 역할

Renderer는 Page Schema를 실제 웹 페이지로 변환한다.

```text
Page Schema
      ↓
Theme Renderer
      ↓
Section Renderer
      ↓
Component Renderer
      ↓
Layout Renderer
      ↓
Style Renderer
      ↓
Behavior Renderer
      ↓
HTML + CSS + Behavior Metadata
```

---

## 8.2 예시

Page Schema:

```json
{
  "type": "button",
  "id": "hero-button",
  "content": {
    "text": "참여하기"
  }
}
```

Renderer 결과:

```html
<button id="hero-button">
    참여하기
</button>
```

즉, LLM이 다음과 같은 HTML을 직접 생성하지 않는다.

```html
<button
    class="btn-primary"
    style="..."
    onclick="..."
>
    참여하기
</button>
```

HTML 생성은 서버의 Renderer가 담당한다.

---

# 9. Behavior Runtime

## 9.1 목적

버튼 클릭, 모달, 탭, 토글 등의 일반적인 동작을 LLM이 JavaScript 코드로 직접 생성하지 않도록 한다.

페이지에는 Behavior Metadata만 저장한다.

```json
{
  "behavior": {
    "event": "click",
    "action": "open-modal",
    "target": "event-info-modal"
  }
}
```

공통 Runtime JavaScript가 이 정보를 해석한다.

---

## 9.2 Runtime JS

```text
runtime.js
├── openModal()
├── closeModal()
├── toggle()
├── switchTab()
├── navigate()
├── scroll()
├── show()
├── hide()
├── apiRequest()
└── countdown()
```

따라서 LLM은 다음과 같은 복잡한 코드를 생성할 필요가 없다.

```javascript
document
    .querySelector(...)
    .addEventListener(...);
```

대신 다음과 같은 구조화된 동작만 생성한다.

```json
{
  "event": "click",
  "action": "open-modal",
  "target": "event-modal"
}
```

## 9.3 Runtime Action
9.3.1 openModal()
function openModal(targetId)
{
    const modal = document.getElementById(targetId);

    if (!modal)
    {
        console.warn(`Modal not found: ${targetId}`);
        return;
    }

    modal.classList.add("is-open");
}
9.3.2 closeModal()
function closeModal(targetId)
{
    const modal = document.getElementById(targetId);

    if (!modal)
    {
        return;
    }

    modal.classList.remove("is-open");
}
9.3.3 toggle()
function toggle(targetId)
{
    const target = document.getElementById(targetId);

    if (!target)
    {
        return;
    }

    target.classList.toggle("is-visible");
}
9.3.4 show()
function show(targetId)
{
    const target = document.getElementById(targetId);

    if (!target)
    {
        return;
    }

    target.classList.remove("is-hidden");
}
9.3.5 hide()
function hide(targetId)
{
    const target = document.getElementById(targetId);

    if (!target)
    {
        return;
    }

    target.classList.add("is-hidden");
}
9.3.6 scroll()
function scroll(targetId)
{
    const target = document.getElementById(targetId);

    if (!target)
    {
        return;
    }

    target.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}
9.3.7 navigate()
function navigate(url)
{
    if (!url)
    {
        return;
    }

    window.location.href = url;
}

외부 URL 이동을 허용하는 경우에는 서버 측에서 허용된 URL인지 검증한다.

## 10 복잡한 동작

단순한 동작은 하나의 Action으로 처리한다.
```json
{
  "event": "click",
  "action": "open-modal",
  "target": "event-modal"
}
```

여러 동작이 필요한 경우 Workflow 형태로 구성한다.
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
실제 Runtime은 이 Action들을 순서대로 실행한다.

Button Click
    ↓
API Request
    ↓
Response
    ↓
Success
    ↓
Show Modal

---

# 11. Custom JavaScript

임의의 JavaScript를 LLM이 자유롭게 생성하도록 하는 방식은 기본 기능으로 사용하지 않는다.

필요한 경우에도 다음과 같은 제한이 필요하다.

```text
Custom JS
    ↓
Syntax Validation
    ↓
Allowlist
    ↓
Security Validation
    ↓
Sandbox
    ↓
Execution
```

기본적인 UI 동작은 Runtime JS의 Action으로 처리하고, Custom JS는 예외적인 고급 기능으로 제한한다.

---

# 12. Modification Command

페이지 수정에서는 Page Schema와 Modification Command를 분리한다.

```text
Page Schema
= 현재 페이지의 상태

Modification Command
= 페이지를 어떻게 변경할 것인지에 대한 명령
```

---

## 12.1 UPDATE

사용자:

> 히어로 버튼 문구를 이벤트 참여하기로 변경해줘.

LLM:

```json
{
  "operation": "update",
  "target": {
    "id": "hero-button"
  },
  "changes": {
    "content": {
      "text": "이벤트 참여하기"
    }
  }
}
```

---

## 12.2 DELETE

```json
{
  "operation": "delete",
  "target": {
    "id": "product-card-2"
  }
}
```

---

## 12.3 CREATE

```json
{
  "operation": "create",
  "parent": {
    "id": "section-product"
  },
  "component": {
    "type": "card",
    "id": "product-card-3",
    "content": {
      "title": "상품 C",
      "description": "새로운 특별 할인 상품입니다."
    }
  }
}
```

---

## 12.4 MOVE

Component의 위치를 변경한다.

```json
{
  "operation": "move",
  "target": {
    "id": "hero-button"
  },
  "parent": {
    "id": "section-cta"
  }
}
```

---

## 12.5 REPLACE

특정 Component를 새로운 Component로 교체한다.

```json
{
  "operation": "replace",
  "target": {
    "id": "product-card-1"
  },
  "component": {
    "type": "card",
    "id": "product-card-1",
    "content": {
      "title": "새로운 상품"
    }
  }
}
```

---

# 13. Operation Engine

Modification Command를 실제 Page Schema에 적용하는 역할을 담당한다.

```text
Modification Command
        ↓
Target Lookup
        ↓
Target Validation
        ↓
Operation Validation
        ↓
Operation Execution
        ↓
Page Schema 변경
```

예를 들어:

```text
UPDATE hero-button
        ↓
hero-button 검색
        ↓
존재 여부 확인
        ↓
content.text 변경
        ↓
Page Schema 저장
```

---

# 14. DOM 처리

DOM을 직접 수정하는 방식과 Page Schema를 수정하는 방식을 구분한다.

### 단순 변경

```text
버튼 텍스트 변경
        ↓
DOM Patch 가능
```

### 구조적 변경

```text
카드 추가
카드 삭제
Section 이동
Component 교체
        ↓
Page Schema 변경
        ↓
Renderer / Reconciliation
        ↓
DOM 변경
```

따라서 **Page Schema가 항상 기준 상태**가 된다.

```text
Page Schema
      ↓
   Renderer
      ↓
     DOM
```

DOM을 수정했다고 Page Schema가 변경되는 구조로 만들지 않는다.

---

# 15. Validator

LLM이 생성한 결과를 바로 실행하지 않는다.

전체 검증 과정은 다음과 같다.

```text
LLM Output
    ↓
JSON Parse
    ↓
Schema Validation
    ↓
Semantic Validation
    ↓
Target Validation
    ↓
Operation Validation
    ↓
Execution
```

### Schema Validation

```text
필수 필드 존재
자료형 확인
type 확인
variant 확인
style 형식 확인
```

### Semantic Validation

```text
ID 중복 확인
부모 존재 여부
Component 구조 확인
```

### Behavior Validation

```text
event 허용 여부
action 허용 여부
target 존재 여부
```

### Operation Validation

```text
CREATE
UPDATE
DELETE
MOVE
REPLACE
```

각 Operation의 필수 조건을 검증한다.

---

# 16. LLM의 역할

LLM의 책임은 가능한 한 작게 유지한다.

## Generation

```text
사용자 요구사항
      ↓
     LLM
      ↓
Page Schema
```

## Modification

```text
기존 Page Schema
+
사용자 수정 요청
      ↓
     LLM
      ↓
Modification Command
```

LLM이 담당하지 않는 영역:

```text
HTML 렌더링
CSS 생성
DOM 직접 조작
JavaScript 실행
DB 저장
페이지 검증
```

이 영역은 서버 및 Runtime이 담당한다.

---

# 17. 전체 생성 Pipeline

```text
사용자 요구사항
        ↓
      Prompt
        ↓
       LLM
        ↓
   Page Schema
        ↓
     Validator
        ↓
       Save
        ↓
     Renderer
        ↓
 HTML + CSS + Behavior
        ↓
      Browser
        ↓
 DOM + Runtime JS
        ↓
      Preview
        ↓
      Publish
```

---

# 18. 전체 수정 Pipeline

```text
기존 Page Schema
        +
사용자 수정 요청
        ↓
       LLM
        ↓
Modification Command
        ↓
Schema Validation
        ↓
Target Validation
        ↓
Operation Engine
        ↓
Page Schema 변경
        ↓
Renderer / Reconciliation
        ↓
HTML + CSS + Behavior
        ↓
Browser DOM
```

---

# 19. 데이터 저장

DB에는 HTML을 기준 데이터로 저장하지 않고 Page Schema와 버전을 저장한다.

```text
Page
├── pageId
├── version
├── status
└── schema
```

버전 관리:

```text
Version 1
    ↓
Version 2
    ↓
Version 3
```

이를 통해 페이지 수정 이력과 Rollback을 구현할 수 있다.

---

# 20. Spring Boot 구현 구조

```text
src/main/java
└── com.example.event
    │
    ├── controller
    │   └── PageController.java
    │
    ├── service
    │   ├── PageService.java
    │   ├── GenerationService.java
    │   └── ModificationService.java
    │
    ├── schema
    │   ├── PageSchema.java
    │   ├── PageMetadata.java
    │   ├── Theme.java
    │   ├── Section.java
    │   ├── Component.java
    │   └── Behavior.java
    │
    ├── modification
    │   ├── ModificationCommand.java
    │   ├── Operation.java
    │   └── OperationEngine.java
    │
    ├── renderer
    │   ├── PageRenderer.java
    │   ├── SectionRenderer.java
    │   └── ComponentRenderer.java
    │
    ├── validator
    │   ├── SchemaValidator.java
    │   ├── TargetValidator.java
    │   └── OperationValidator.java
    │
    └── llm
        ├── LlmClient.java
        ├── GenerationPrompt.java
        └── ModificationPrompt.java
```

---

# 21. 개발 순서

전체 기능을 한 번에 구현하지 않고 다음 순서로 진행한다.

## Phase 1 — Schema

먼저 LLM 없이 Page Schema를 직접 작성한다.

```text
직접 작성한 JSON
        ↓
Page Schema
```

---

## Phase 2 — Renderer

```text
Page Schema
        ↓
Renderer
        ↓
HTML + CSS
        ↓
Browser
```

이 단계에서 실제 이벤트 페이지가 정상적으로 출력되는지 확인한다.

---

## Phase 3 — Behavior Runtime

```text
Behavior Metadata
        ↓
Runtime JS
        ↓
Modal / Tab / Toggle / API 등
```

---

## Phase 4 — Validator

```text
Page Schema
        ↓
Schema Validation
        ↓
Semantic Validation
```

---

## Phase 5 — LLM Generation

```text
사용자 요구사항
        ↓
Qwen
        ↓
Page Schema
        ↓
Validator
        ↓
Renderer
```

이 단계부터 LLM을 시스템에 연결한다.

---

## Phase 6 — Modification

```text
사용자 수정 요청
        ↓
Qwen
        ↓
Modification Command
        ↓
Operation Engine
        ↓
Page Schema 변경
```

---

## Phase 7 — 평가

Generation과 Modification을 각각 평가한다.

### Generation

```text
요구사항
 ↓
LLM
 ↓
Page Schema
 ↓
Renderer
 ↓
HTML / DOM
```

평가 항목:

* Requirement Satisfaction
* Schema Validity
* HTML Validity
* DOM Structure
* Render Success
* Visual Quality
* Content Quality

### Modification

```text
Original Page
+
Modification Request
 ↓
LLM
 ↓
Modification Command
 ↓
Operation Engine
 ↓
Modified Page
```

평가 항목:

* Modification Accuracy
* Target Accuracy
* Requirement Satisfaction
* Existing Feature Preservation
* Unintended Change
* DOM Validity
* Render Success

LLM Judge만 사용하지 않고 HTML Parser, Playwright 등의 결정론적 검증도 함께 사용하는 것을 권장한다.

---

# 22. 최종 책임 분리

| 영역                   | 책임                  |
| -------------------- | ------------------- |
| LLM                  | 자연어 → 구조화된 의도 변환    |
| Page Schema          | 페이지 구조와 상태 표현       |
| Theme                | 공통 디자인 정의           |
| Section              | 페이지 영역 정의           |
| Component            | UI 요소 정의            |
| Behavior             | UI 동작 정의            |
| Modification Command | 페이지 변경 의도 표현        |
| Operation Engine     | 변경 실행               |
| Validator            | 결과 검증               |
| Renderer             | HTML/CSS 생성         |
| Runtime JS           | 브라우저 동작 실행          |
| DOM                  | 실제 브라우저 UI 상태       |
| Database             | Page Schema 및 버전 저장 |

---

# 23. 최종 시스템 구조

```text
                         ┌──────────────┐
                         │    사용자     │
                         └──────┬───────┘
                                │
                       자연어 요구사항
                                │
                                ▼
                         ┌──────────────┐
                         │     LLM      │
                         │ Qwen / API   │
                         └──────┬───────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
          ┌──────────────┐             ┌──────────────────┐
          │ Page Schema  │             │ Modification     │
          │              │             │ Command          │
          └──────┬───────┘             └────────┬─────────┘
                 │                              │
                 │                       ┌──────▼───────┐
                 │                       │   Validator  │
                 │                       └──────┬───────┘
                 │                              │
                 │                       ┌──────▼───────┐
                 │                       │ Operation    │
                 │                       │ Engine       │
                 │                       └──────┬───────┘
                 │                              │
                 └──────────────┬───────────────┘
                                ▼
                       ┌────────────────┐
                       │  Page Schema   │
                       │  Canonical     │
                       │  State         │
                       └───────┬────────┘
                               │
                               ▼
                       ┌───────────────┐
                       │   Renderer    │
                       └───────┬───────┘
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
                   HTML                 CSS
                     │
                     ▼
                  Browser
                     │
                     ▼
                    DOM
                     │
                     ▼
              ┌───────────────┐
              │ Runtime JS    │
              │ Behavior 처리 │
              └───────────────┘
```

## 핵심 원칙

이 구조에서 가장 중요한 원칙은 다음과 같다.

> **LLM은 페이지를 직접 구현하는 역할이 아니라, 페이지를 어떻게 구성하거나 변경할지에 대한 구조화된 의도를 생성한다.**

따라서 LLM의 역할을 최소화하고, **페이지 구조는 Page Schema가 소유하며 HTML/CSS 렌더링은 서버가, UI 동작은 Runtime JS가, 변경 실행은 Operation Engine이 담당**하도록 구성한다.

이렇게 하면 Qwen2.5 7B와 같이 상대적으로 작은 모델을 사용할 때도 생성해야 하는 출력의 복잡도를 줄일 수 있고, 생성 결과에 대한 검증과 재현성 확보도 용이해진다.
