# playground — J/S 생성 → K/S 수정 수동 테스트

`versions/*`는 seed 반복·다수 모델 비교를 하는 통계적 벤치마크라 결과가
CSV로 쌓이지만, 이 폴더는 **직접 한 번 돌려보고 브라우저로 눈으로
확인하는 용도**다. 그래서 `versions/`가 아니라 최상위에 따로 뒀고,
seed·반복 횟수 같은 게 없다.

## 1. 전체 프로세스

```
              ┌─ J (plan JSON)  ──────┐
  [시작] ──┬──┤                       ├──▶ 상태: plan 있음 ──┬─ 수정=K (patch)  ──┐
           │  └─ S (직접 HTML) ───────┤                      │                     │
           │                          ├──▶ 상태: plan 없음 ──┴─ 수정=S (블록 왕복) ─┤
           └─ 템플릿 불러오기(S) ──────┘                                            │
                                                                                    ▼
                                                                    [미리보기 갱신 + 로그 기록]
                                                                     "수정 방식" 다시 선택 → 반복
```

**핵심 규칙 — K(patch)는 구조화된 `plan`이 있을 때만 가능하다.**
`checks.apply_patch()`가 `{"blocks":[...], "theme":{...}}` 구조를 전제로
동작하기 때문이다. 그래서:

| 시작 방법 | plan 존재? | 이후 수정 |
| --- | --- | --- |
| J로 생성 | 있음 | **K 또는 S** 둘 다 가능 |
| S로 생성 | 없음 | **S만** 가능 |
| 템플릿 불러오기 | 없음 | **S만** 가능 |
| (J로 생성 후) S로 한 번 수정 | **그 순간 무효화** | 그 뒤로는 **S만** 가능 |

마지막 줄이 중요하다 — S로 블록을 직접 고치면 그 결과는 plan에 반영되지
않으므로 plan과 실제 화면이 어긋난다. GUI는 이 순간 "수정" 드롭다운에서
K 옵션을 자동으로 비활성화하고, 서버(`/api/edit`)도 `plan=null`로 K를
요청하면 명시적으로 거부한다(이중 안전장치 — 클라이언트 버그와 무관하게
항상 막힘).

## 2. 생성/수정 방식 4가지

| | 무엇을 내나 | 안전장치 | 나오는 마크업 |
| --- | --- | --- | --- |
| **생성 J** | plan JSON (`PLAN_SCHEMA`) | JSON 스키마로 필드·타입 강제 | 합성 Tailwind (`base/component_library.py`) |
| **생성 S** | `<section>` HTML 직접 (v5 `cases_st.py`와 동일) | 없음(자유 형식) | `ev-block block-*` 클래스 — `event.css` 적용됨 |
| **템플릿 불러오기** | (생성 아님) 실제 파일 그대로 로드 | — | 진짜 제품 템플릿 + `event.css` |
| **수정 K** | patch 오퍼레이션(`PATCH_SCHEMA`) | JSON 스키마 + `apply_patch()`가 화이트리스트 연산만 허용 | 원래 상태 유지 |
| **수정 S** | 블록의 새 outerHTML 통째로 (`edit_lib.py`) | 없음 — `no_ops`/`class_lost` 같은 실패가 코드로 안 걸러짐 | 원래 상태 유지(모델이 잘 지키면) |

**요청한 6가지 시나리오는 K와 S가 표현 방식이 다르다:**

| 시나리오 | K(패치) 표현 | S(직접 편집) 표현 |
| --- | --- | --- |
| 구조 추가 | `add_block` | 지시문으로 요청 → 모델이 블록 HTML에 항목 추가 |
| 구조/문구 삭제 | `remove_block` / `set_field`로 빈 값 | 지시문으로 요청 |
| 문구 변경 | `set_field` | 지시문으로 요청 |
| 크기 변경 | `set_theme` (`baseFontSize`) | 지시문 → 모델이 클래스/인라인 스타일 직접 수정 |
| 테마 변경 | `apply_preset` (vivid/cool/minimal/warm) | 지시문으로 요청 |
| 색깔 변경 | `set_theme` (`primaryColor`/`buttonColor`) | 지시문으로 요청 |
| JS 추가 | `add_block` (poll/rating/coupon/checklist/carousel/countdown/faq/tabs) | 해당 블록이 등록돼 있어야 함(현재 실제 템플릿엔 없음 — J/K 전용) |

K는 전용 오퍼레이션이 있어서 **강제**되고, S는 모델의 자유 편집 능력에
**그대로 의존**한다 — 이 차이 자체가 `docs/bedrock-migration.md` §8("K는
구조 변경에 약하고 S는 강하다")과 정확히 대응되는 비교 지점이다.

## 3. 실행

### GUI (권장 — 4가지 방식 전부 지원)

```bash
pip install -r requirements.txt   # flask 포함
python playground/app.py          # http://127.0.0.1:5050
```

- 왼쪽 "생성"(J/S) · "수정"(K/S, plan 없으면 K 비활성화) 드롭다운으로
  방식 선택. 템플릿을 쓰려면 "템플릿" 드롭다운 + "불러오기(S)" 버튼.
- "수정영역" 드롭다운은 현재 HTML에 실제로 있는 `data-block`을 매 응답마다
  다시 채운다(J든 S든 템플릿이든 동일하게 동작).
- 템플릿을 불러오면 실제 원본의 `theme-*` 클래스(`theme-sports`,
  `theme-sale` 등)도 함께 읽어서 미리보기 `<body>`에 그대로 유지한다 —
  `event.css`의 색상·레이아웃 규칙 대부분이 이 클래스에 스코프돼 있어서
  (`.theme-sports .sp-hero`처럼), 빠뜨리면 템플릿 5개가 전부 테마 없는
  기본값으로 똑같아 보인다(실제로 겪은 버그, `template_loader.py`/
  `util.wrap_with_css()` 참고). S로 블록을 수정해도 이 테마는 계속
  유지된다.
- 오른쪽 미리보기는 `template/index.html` 쇼케이스의 뷰어 UI를 그대로
  가져왔다 — **🖥️ 데스크톱/📱 모바일** 뷰포트 토글, **🛡️ 관리자 뷰** 토글
  (`event.css`의 `.admin-preview` 규칙 — S 생성·템플릿 로드 결과에서만
  의미 있음, J의 합성 마크업엔 해당 클래스가 없음). `srcdoc`이 갱신될
  때마다 관리자 뷰 상태가 자동으로 재적용된다.
- 모델이 낸 patch JSON(K)이나 수정 전/후 블록 HTML(S)은 왼쪽 로그에
  그대로 찍힌다 — 요청이 거부되면(`action`이 `clarify`/`unsupported`)
  로그에 빨간색으로 표시된다.
- "새로 시작" 버튼으로 언제든 리셋. 매 단계는 `playground/output/<시각>_gui_*/`
  에 CLI와 같은 형식(`NN_라벨.plan.json`+`.html`)으로 파일 기록도 남는다.

### CLI (⚠ J/K만 지원 — S 생성·S 편집·템플릿 불러오기는 GUI 전용)

```bash
python playground/generate.py "여름 데이터 프로모션 이벤트 페이지를 만들어줘"
#  → playground/output/<시각>_gen/01_generate.html 을 브라우저로 열어서 확인

python playground/edit.py playground/output/<시각>_gen/01_generate.plan.json \
    "혜택 항목 중 마지막 하나를 삭제해줘"
python playground/edit.py playground/output/<시각>_gen/02_edit_*.plan.json \
    "전체적으로 화사한(vivid) 느낌으로 바꿔줘"
```

스크립트로 자동화하고 싶을 때 쓴다. `edit.py`도 모델이 낸 patch를 실행
때마다 화면에 그대로 찍는다 — `action`이 `clarify`/`unsupported`면
`question`/`reason` 필드에 거부 이유가 나온다.

### 백엔드 전환 (기본: 로컬 Ollama)

```bash
export PLAYGROUND_BACKEND=bedrock
export BEDROCK_MODEL_ID="anthropic.claude-sonnet-4-5-20250929-v1:0"
```

## 4. 벤치마크 실측 결과와 비교하는 법

`docs/bedrock-migration.md` §8: 구조 추가/삭제는 K(패치)로 시도하면
실패율이 높았다(`no_ops`가 지배적 실패). 여기서 "수정=K"로 같은 시나리오를
직접 돌려보면 그 실패가 재현되는지 눈으로 볼 수 있다 — 로그에 찍히는
patch가 빈 `ops:[]`이거나 `action:"unsupported"`면 그게 그 실패다.
"수정=S"로 바꿔서 같은 요청이 성공하는지 비교하면 §8의 "S가 K보다
안전하다"는 결론이 재현되는지도 바로 확인된다.

## 5. 파일 구조

```
playground/
  backend.py          call() 백엔드 선택 — Ollama(base/engine.call, 기본) / Bedrock(bedrock/bedrock_call.call)
  schemas.py           PLAN_SCHEMA(registry 원본) + PATCH_SCHEMA(add_block에 콘텐츠 필드 확장, v9와 동일 이유)
  template_loader.py   실제 템플릿(template/template_1~5.html) + event.css 로더 — versions/v4/templates.py 재사용
  core.py               GUI·CLI 공용 핵심 로직 (아래 4개 함수)
  util.py               세션 폴더 관리, JSON 파싱, 결과를 볼 수 있는 HTML 문서로 감싸기(합성용/실제 CSS용 2종)
  app.py                GUI — Flask, 왼쪽 입력·오른쪽 미리보기(뷰포트·관리자뷰 토글 포함)
  generate.py           CLI 1단계 — J 생성만 (core.generate_page)
  edit.py                CLI 2단계 — K 수정만 (core.edit_page), 반복 가능
  output/                실행할 때마다 쌓이는 결과물 (git 제외)
```

**`core.py`의 4개 핵심 함수** (GUI·CLI가 전부 이 함수만 호출 — 로직이
두 곳에 따로 있지 않아 결과가 어긋날 일이 없다):

| 함수 | 방식 | 반환 |
| --- | --- | --- |
| `generate_page(prompt, model)` | J | `{plan, html}` |
| `generate_page_html(prompt, model)` | S(생성) | `{html}` — plan 없음 |
| `edit_page(current_plan, instruction, model)` | K | `{patch, plan, html, rejected}` |
| `edit_block_direct(current_html, block_key, instruction, model)` | S(수정) | `{html, block_before, block_after}` |
| `blocks_in_html(html)` | (공용 헬퍼) | 현재 HTML의 `data-block` 목록 — "수정영역" 드롭다운용 |

**`app.py`의 API 라우트** (GUI 전용, `core.py`를 그대로 호출):

| 라우트 | 방식 |
| --- | --- |
| `POST /api/generate` | J 생성 |
| `POST /api/generate_html` | S 생성 |
| `POST /api/edit` | K 수정 (plan 없으면 서버가 거부) |
| `POST /api/edit_block` | S 수정 |
| `POST /api/load_template` | 실제 템플릿 로드 |

### 5-1. 외부 의존성 — playground 밖에서 가져다 쓰는 것

playground 안의 파일은 전부 여기 걸려 있다. **어느 것도 고치지 않고
가져다 쓰기만 한다** — 전부 v1~v9가 의존하거나(`base/*`) 실제 제품
자산(`template/*`)이라, 여기서 손대면 다른 곳이 조용히 깨진다.

| playground 파일 | 가져다 쓰는 곳 | 가져오는 것 |
| --- | --- | --- |
| `backend.py` | `base/engine.py` | `call()` — 기본 백엔드(로컬 Ollama) |
| `backend.py` (`PLAYGROUND_BACKEND=bedrock`일 때) | `bedrock/bedrock_call.py` | `call()` — Bedrock 백엔드 |
| `core.py`, `schemas.py` | `base/registry.py` | `render_plan`/`render_theme_style`/`THEME_DEFAULTS`/`THEME_FIELDS`/`STYLE_PRESETS`/`LLM_BLOCKS`/`build_plan_json_schema` |
| `core.py` | `base/checks.py` | `apply_patch`(K 패치 적용), `extract`(LLM 응답에서 HTML만 추출) |
| `core.py` | `base/edit_lib.py` | `block_of`/`replace_block`/`build_block_edit_system` — S 방식 블록 왕복편집 |
| `template_loader.py` | `versions/v4/templates.py` | `container`/`block_html`/`blocks_of` — 읽기 전용, v4 폴더 자체는 안 건드림 |
| `template_loader.py` | `template/event.css` | 실제 스타일시트 원문(인라인 삽입용) |
| `template_loader.py` | `template/template_1~5.html` | 실제 제품 템플릿 5종 |

**스키마 확장(`schemas.py`)이나 백엔드 선택(`backend.py`)처럼 playground
전용으로 필요한 건 위 표의 원본을 고치지 않고 playground 안에 별도
파일로 둔다** — `bedrock/bedrock_call.py`를 `base/engine.py` 옆에 뒀던
것과 같은 원칙(§ `docs/bedrock-migration.md`).
