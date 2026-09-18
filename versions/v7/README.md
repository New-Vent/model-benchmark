# v7 — CHAIN7: 확정된 조합을 실제 템플릿 스케일로 잇기

**구현 완료.** `python base/run.py v7 --self-check`로 LLM 호출 없이 검증
가능합니다(v1~v5 회귀도 함께 확인함). 아직 실제 모델로 돌려서 결과를 낸
적은 없습니다 — §5 "구현 상태"에 실제 코드 구조와 다음 단계를 적어뒀습니다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md)를 그대로 따릅니다.

CHAIN7은 [docs/methodology.md](../../docs/methodology.md) §6 "버전을 새로 파는 기준"에 그대로 걸립니다 — 새 프롬프트(실제 템플릿 스케일), 새
케이스(CHAIN7-J-E/CHAIN7-J-K/CHAIN7-S), 기존 CHAIN2~6과 다른 검증 로직
(내용 보존 diff 체크, 아래 §4)이 전부 새로 생기므로 기존 v3에 끼워 넣을
수 없습니다.

**CHAIN7 자체는 팀이 이미 정한 다음 단계입니다** — [docs/reports/v1/pipeline.md:80](../../docs/reports/v1/pipeline.md)
이 명시:

> 다음 단계: 신규 생성 캡을 올려 S/J를 확정한 뒤, "그 결과 → E수정 →
> JS-PLAN추가 → 값수정" 조합을 그대로 재는 CHAIN7이 필요, 표본(1기기·5회)도
> 재실행으로 보강

v5가 "신규 생성 캡을 올려 S/J를 확정"하는 부분을 끝냈으니(qwen 계열은
S-T/J-T 완전 동률 — [versions/v5/README.md](../v5/README.md) §5), 이제
CHAIN7을 실제로 설계할 조건이 갖춰졌습니다.

## 1. CHAIN2~6 중 어느 것도 "JS-PLAN"을 실제로 쓴 적이 없다

이번 설계를 시작하면서 `versions/v3/cases_chain.py`를 다시 읽다가 확인한
사실입니다. pipeline.md §"축별 결론"은 "인터랙션 추가 = **JS-PLAN**(생성
시점에 포함)"을 채택 근거로 적어뒀지만, 실제 CHAIN2~6의 3단계("JS 추가")는:

| CHAIN | 3단계(JS 추가) 실제 방식 |
| --- | --- |
| CHAIN2 | JS-PATCH (카운트다운 `add_block`) |
| CHAIN3 | JS-HTML (카운트다운 직접 작성) |
| CHAIN5 | JS-HTML (카운트다운 직접 작성) |
| CHAIN6 | JS-PATCH류 (카운트다운을 단일 JSON 블록으로 추가 — `_run_add_single_block_stage` 우회법) |

**JS-PLAN을 쓴 체인이 하나도 없습니다.** `cases_js_plan.py`의 자체 정의를
보면(`P_COUNTDOWN = GEN_P1 + " 카운트다운도 넣어줘"`), JS-PLAN은 "기존
요청에 카운트다운 요청을 더해서, **전체 페이지 plan을 통째로 다시
받는다**"는 뜻입니다 — 델타(patch)가 아니라 **재생성**입니다. 이건 체인
안에서 쓰려면 "이미 수정된 현재 문서를 보여주고, 그 내용을 그대로 보존한
채 새 블록만 추가된 전체 plan을 다시 뽑아야" 하는데, 그 방식은 CHAIN2~6
어디에도 없었습니다 — 전부 "새 블록 하나만" 다루는 patch/add_block류로
우회했습니다(CHAIN6 docstring이 이 우회 이유를 직접 설명합니다: "HTML을
JSON으로 되돌리는 역변환 파서가 없다").

**CHAIN7의 존재 이유는 정확히 이 구멍입니다** — pipeline.md가 approved한
"JS-PLAN" 방식을, 최초로, 실전 체인 안에서 재 봅니다.

## 2. 단계 설계 — 두 노선 (CHAIN7-J / CHAIN7-S)

S-T 노선도 같이 봅니다. 다만 §1에서 설명한 "JS-PLAN(전체 plan 재출력)"을 S-T 위에서 하려면, J-T와는 전혀 다른 난이도의 작업이 됩니다 — 그래서 **두 노선을 같은 파일 안에 나란히 두되, 3단계의 실제 동작은 다르게 설계**합니다.

```
                CHAIN7-J (JSON 노선)          CHAIN7-S (HTML 노선)
1. 생성          J-T (v5 프롬프트)              S-T (v5 프롬프트)
2. 수정          E (cta 블록 왕복 편집)          E (cta 블록 왕복 편집, 동일)
3. JS 추가       JS-PLAN — "JSON 뼈대 있음"     JS-PLAN — "맨눈 변환"
                 (원래 plan + 수정된 HTML을      (HTML 문서만 보여주고 전체를
                 같이 보여주고 병합 요청)         JSON으로 변환+countdown 추가)
4. 값 수정       CHAIN7-J-E / CHAIN7-J-K 2변형   CHAIN7-S (K만, 이유는 §3)
                 (§3)
```

### 3단계가 노선마다 왜 다른가

JS-PLAN은 태생적으로 JSON 경로입니다(모델이 plan을 다시 낸다). 두 노선
모두 결국 3단계에서 "JSON plan"을 내야 하지만, 그 plan을 만드는 난이도가
다릅니다:

- **CHAIN7-J**: 1단계가 이미 J-T라서 원본 JSON plan을 우리가 그대로 쥐고
  있습니다. 3단계에서는 모델에게 "이 원본 plan + 2단계에서 바뀐 cta HTML"을
  같이 보여주고 "cta는 이 내용으로 바꾸고 countdown만 추가해서 plan
  전체를 다시 내라"고 요청합니다 — **이미 정답에 가까운 JSON 뼈대가
  있는 상태에서 한 필드만 갱신 + 블록 하나 추가**하는 작업입니다.
- **CHAIN7-S**: 1단계가 S-T라서 JSON이 아예 없습니다. 3단계에서는 모델에게
  **순수 HTML 문서만** 보여주고 "이 내용을 그대로 JSON plan으로 바꾸고
  countdown도 추가하라"고 요청합니다 — 뼈대 없이 **맨눈으로 HTML→JSON
  변환**까지 해야 합니다(변환 자체가 CHAIN6 docstring이 "역변환 파서가
  없다"고 한 바로 그 문제 — 여기서는 파서 대신 모델 자신에게 그 일을
  시킵니다).

그래서 CHAIN7-S는 CHAIN7-J보다 실패 지점이 하나 더 많습니다: 변환 과정에서
`unknown_type`/`unknown_variant`(스키마에 없는 값을 지어냄), 필드 누락,
내용 왜곡이 전부 가능합니다. 이건 버그가 아니라 **CHAIN7-S가 실제로
재려는 질문 자체**입니다 — "HTML 노선으로 쭉 가다가 인터랙션만 JSON으로
안전하게 추가하는 게 실제로 되는가."

### 왜 수정(E)이 cta 블록인가

두 노선 공통으로 CHAIN2~6과 동일한 관례를 따릅니다(`EDIT_REQUEST_TEXT`/
`EDIT_WANT_TEXT` 재사용) — 작은 블록이라 num_predict 부담이 적고, 이미
검증된 채점 로직(`check_block_text_edit`)을 그대로 쓸 수 있습니다.

## 3. 세 변형과, 각각이 무엇을 "한 가지만" 갈라서 보는가

pipeline.md §4는 CHAIN2(순수 JSON, 1/15)와 CHAIN6(HTML+JSON 교차,
15/15)의 격차를 "생성 방식 차이 때문인지 값수정 방식 차이 때문인지
분리가 안 된다"는 이유로 "보류"로 남겼습니다 — **두 체인이 한 번에 여러
변수를 동시에 바꿔서 비교했기 때문**입니다(생성 방식도 다르고 JS추가
방식도 다르고 값수정 방식도 다름).

CHAIN7은 그 실수를 반복하지 않도록, **매번 딱 하나의 변수만** 바꿉니다.

| 변형 | 생성 노선 | 값 수정 방법 |
| --- | --- | --- |
| **CHAIN7-J-E** | J-T | 3단계에서 받은 전체 plan을 렌더링한 HTML을 통째로 다시 쓰게 해서 날짜만 바꾼다(전체재작성, CHAIN2/3/5 계열) |
| **CHAIN7-J-K** | J-T | 3단계에서 받은 countdown 블록의 JSON만 떼어내 미니 plan으로 K 패치(`set_field target_date`, CHAIN6 계열 — 15/15로 이미 검증됨) |
| **CHAIN7-S** | S-T | K 패치만(CHAIN7-J-K와 동일한 값수정 방법) |

**CHAIN7-S에 -E 변형을 따로 안 만드는 이유**: 만들면 4개 조합(2노선×2값수정)이
되어 다시 여러 변수가 섞입니다. 대신 CHAIN7-S는 **값수정 방법을 이미
확실한 쪽(K, CHAIN6 선례)으로 고정**해서, 딱 "노선(J-T vs S-T)"이라는
한 변수만 갈라 봅니다.

이렇게 하면 두 개의 독립적인 비교가 성립합니다:

- **CHAIN7-J-E vs CHAIN7-J-K** → 노선을 J-T로 고정한 채 **값 수정 방법**만
  다름 (pipeline.md §4의 원래 질문)
- **CHAIN7-J-K vs CHAIN7-S** → 값 수정 방법을 K로 고정한 채 **생성 노선**만
  다름 (§2가 설명한 "맨눈 변환이 실제로 버티는가")

CHAIN7-J-K가 CHAIN7-J-E를 이기고, CHAIN7-S가 CHAIN7-J-K보다 낮게 나올
걸로 예상되지만(CHAIN6 선례 + §2의 위험 분석), 실제 템플릿 스케일에서
처음 재는 것이므로 예단하지 않습니다.

## 4. 위험 요소 / 아직 코드로 안 풀린 것

- **3단계의 "내용 보존" 검증이 새로 필요합니다(두 노선 공통).** 기존
  CHAIN2~6의 JS추가 검증은 "새 블록이 잘 붙었는가"만 봤습니다
  (`check_js_structure`, `check_countdown_value_format`). CHAIN7의
  JS-PLAN 방식은 모델이 전체 plan을 **재출력**하므로, "2단계에서 바뀐
  cta 문구가 3단계 재출력에서도 그대로 살아있는가"를 별도로 diff
  체크해야 합니다 — 이게 없으면 "재출력하다가 기존 내용을 슬쩍
  되돌리거나 바꿔버리는" 실패를 놓칩니다. `cases_chain7.py` 작성 시
  `check_content_preserved(before, after, block)`류의 새 검사가
  필요합니다(기존 CHAIN 파일에는 없던 검사).
- **CHAIN7-S는 3단계에서 hero/benefits/steps까지 통째로 다시 틀릴 수
  있습니다.** CHAIN7-J는 cta 하나만 갱신하면 되지만(§2), CHAIN7-S는
  건드리지도 않은 hero/benefits/steps까지 처음부터 다시 JSON으로
  옮겨야 하므로, 위 "내용 보존" 검사를 **네 블록 전부**에 대해 해야
  합니다 — CHAIN7-J보다 검증 범위가 넓고, `unknown_type`/`unknown_variant`
  (스키마에 없는 값을 지어냄) 같은 CHAIN7-J에는 없는 실패 유형도
  새로 생깁니다.
- **countdown은 실제 템플릿 5종 어디에도 없습니다** — `templates.py`의
  `self_check()`가 `blocks_of(n) == ["hero","benefits","steps","notices","cta"]`
  를 강제하는 데서 확인됩니다. 그래서 countdown 렌더링은 여전히
  `component_library.py`의 Tailwind풍 variant를 씁니다 — v5 README §6가
  이미 지적한 "실제 제품 마크업과 다르다"는 한계가 여기도 그대로
  적용됩니다.
- **num_predict**: 1단계(J-T/S-T + countdown 필드까지 포함한 실제 스케일
  생성)는 v5의 3072보다 더 필요할 수 있습니다(블록이 하나 늘었으므로).
  잠정 3584로 잡고, 실측 후 조정합니다. CHAIN7-S의 3단계(전체 HTML을
  JSON으로 통째로 재작성)는 출력 분량이 더 클 수 있어 별도로 확인이
  필요합니다.

## 5. 구현 상태

`versions/v7/cases_chain7.py` 구현 완료, `--self-check` 통과. `CASES`에는
**Case가 2개뿐**입니다 — `CHAIN7J`, `CHAIN7S`. §3의 세 변형(CHAIN7-J-E/
CHAIN7-J-K/CHAIN7-S)은 이 2개 Case 안에서 **CSV 행 단위**로 갈립니다
(아래 표). 이렇게 한 이유: CHAIN7-J-E와 CHAIN7-J-K는 1~3단계(생성·수정·
JS추가)가 완전히 동일하므로, Case를 따로 만들면 그 비싼 실제 스케일 LLM
호출(1~3단계)을 seed·모델·기기마다 두 번씩 중복 실행하게 됩니다 — 대신
`custom_run_chain7_j()`가 1~3단계를 한 번만 돌리고 그 결과를 값수정
단계에서만 E/K로 갈라 각각 별도 CSV 행을 남깁니다.

| Case (`prompt_id` 접두어) | 단계별 `prompt_id` | 분석 시 필터 |
| --- | --- | --- |
| `CHAIN7J` | `CHAIN7J_GEN` → `CHAIN7J_EDIT` → `CHAIN7J_JSADD` → `CHAIN7J_VALE` **와** `CHAIN7J_VALK` (둘 다 찍힘) | E 변형 = `..._VALE`, K 변형 = `..._VALK` |
| `CHAIN7S` | `CHAIN7S_GEN` → `CHAIN7S_EDIT` → `CHAIN7S_JSADD` → `CHAIN7S_VAL` | — |

각 단계 구현 출처(재사용 vs 새로 작성):
- 1단계 생성: `SYSTEM_JT7`/`SYSTEM_ST7`(파일 안에 로컬 정의, `versions/v5/cases_jt.py`·
  `cases_st.py`의 SYSTEM과 글자 그대로 동일 — cross-version import가
  안 돼서 복붙, 모듈 docstring 참고)
- 2단계(E수정, 공통): `edit_lib.build_block_edit_system`/`block_of`/
  `replace_block`(base/, 그대로 import) + 로컬 `check_block_text_edit`
- 3단계(JS-PLAN추가): 새로 작성 — `_current_plan_system_j`(JSON 뼈대
  버전) / `_blind_transcribe_system_s`(맨눈 변환 버전), 공통으로 새
  검사 `_content_drift_fails`(§4가 예고한 `check_content_preserved`를
  실제로 구현한 것 — `_extract_json_block_content`/`_extract_html_block_content`
  로 블록별 텍스트만 뽑아 정확히 일치하는지 본다, variant는 제외)
- 4단계(값수정): E변형은 로컬 `SYSTEM_WHOLE_EDIT`+`check_date_updated`,
  K변형은 `_mini_patch_system` + `registry.build_patch_json_schema()`
  (CHAIN6 방식과 동일한 미니 패치, 스키마만 `cases_js_patch.PATCH_SCHEMA`
  대신 범용 `registry` 스키마를 씀 — add_block 콘텐츠 확장이 필요 없어서
  더 단순한 쪽을 골랐다)
- 실행 골격(`_run_stage`, `_blocked_row`)은 `versions/v3/cases_chain.py`에서
  그대로 복붙 — `base/`로 옮길지는 여전히 미결정(§6)

**내용보존 검사는 "글자 하나까지 정확히 일치"로 구현했습니다**(§4가
예고한 애매함 중 하나를 이번에 실제로 결정한 것) — 공백만 정규화하고
(`get_text(" ", strip=True)`), 그 외에는 완전 일치를 요구합니다. 너무
엄격할 수 있다는 위험은 여전히 남아있고, 실제로 돌려보고 나서
"모델이 사소하게 다듬은 것까지 실패로 잡는지" 확인이 필요합니다 — 그때
가서 느슨하게 바꿀지는 실측 데이터로 판단합니다.

다음 순서:

1. 실제 모델로 소규모 파일럿(1모델·1회차)을 돌려서 프롬프트·검사가
   말이 되는지(특히 3단계 "내용보존" 검사가 오탐/누락 없이 작동하는지)
   먼저 확인 — 바로 5모델·5회차 풀런으로 가지 않는다
2. num_predict(3584 잠정치)가 충분한지 `truncated` 비율로 확인, 필요하면
   조정
3. 문제 없으면 `python base/run.py v7`로 본실행, 이 절과 §5를 결과로 채움

## 6. 남은 확인 사항 (v7으로도 안 풀리는 것)

- **CHAIN7-S의 값수정도 -E 변형을 볼지 여부** — §3에서 4개 조합을 막으려고
  일부러 K만 뒀는데, CHAIN7-S가 예상보다 결과가 좋게 나오면 이 노선의
  값수정 방법도 마저 갈라보는 게 다음 후보가 됩니다.
- `_run_stage`/`_run_add_single_block_stage`를 `base/`로 옮길지 여부 —
  v3와 v7이 같은 로직을 복사해서 쓰는 중복이 생기므로, v7 구현 후 팀
  합의가 있으면 `checks_v4.py` 선례처럼 승격 고려
