# v7 — CHAIN7: 확정된 조합을 실제 템플릿 스케일로 잇기

**실행 완료.** 4개 모델(exaone3.5:7.8b·qwen2.5:7b·gemma3:4b·qwen2.5-coder:7b)
× 5회차로 2기기(윤기·주호)에서 측정 끝났습니다 — 결과는 §7 참고. `python
base/run.py v7 --self-check`로 LLM 호출 없이 코드 검증만 할 수도 있습니다.

공통 원칙은 [docs/common/methodology.md](../../docs/common/methodology.md)를 그대로 따릅니다.

CHAIN7은 [docs/common/methodology.md](../../docs/common/methodology.md) §6 "버전을 새로 파는 기준"에 그대로 걸립니다 — 새 프롬프트(실제 템플릿 스케일), 새
케이스(CHAIN7-J-E/CHAIN7-J-K/CHAIN7-S), 기존 CHAIN2~6과 다른 검증 로직
(내용 보존 diff 체크, 아래 §4)이 전부 새로 생기므로 기존 v3에 끼워 넣을
수 없습니다.

**CHAIN7 자체는 팀이 이미 정한 다음 단계입니다** — [docs/reports/v1_v1-v7/pipeline.md:80](../../docs/reports/v1_v1-v7/pipeline.md)
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

**파일럿(qwen2.5:7b 1모델·1회차, 직접 호출) 결과**: 세 변형 모두 첫
시도 또는 재시도로 완주. 원문을 직접 대조해서 3단계 내용보존 검사가
오탐 없이 작동함을 확인함(J노선: hero/benefits/steps 글자 그대로 유지
+ cta는 2단계 수정값 반영 + countdown 정상 추가. S노선: HTML→JSON
맨눈 변환도 글자 하나 안 틀리고 옮겨짐). 값수정 1차 실패(VALE의
"나머지 그대로 출력해" 지시를 모델이 오해해서 countdown만 출력·
VALK의 `no_ops`)는 전부 재시도로 복구 — 이 파일럿 덕분에 본실행 전에
프롬프트·검사 버그가 아님을 확인하고 넘어갈 수 있었습니다.

## 6. 남은 확인 사항 (v7으로도 안 풀리는 것)

- **CHAIN7-S의 값수정도 -E 변형을 볼지 여부** — §3에서 4개 조합을 막으려고
  일부러 K만 뒀는데, CHAIN7-S가 예상보다 결과가 좋게 나오면 이 노선의
  값수정 방법도 마저 갈라보는 게 다음 후보가 됩니다.
- `_run_stage`/`_run_add_single_block_stage`를 `base/`로 옮길지 여부 —
  v3와 v7이 같은 로직을 복사해서 쓰는 중복이 생기므로, v7 구현 후 팀
  합의가 있으면 `checks_v4.py` 선례처럼 승격 고려

## 7. 결과 / 결론

실행 완료. 2기기 종합(윤기 cuda, 주호 cuda/RTX 4060 8GB), 4개 모델 ×
5회차, 총 497행. 드리프트 윤기 1.045, 주호 0.996 — 둘 다 정상 범위.

### 완주율 (4단계 전부 성공 = 완주, 2기기 합산 /10회)

| 모델 | CHAIN7-J-E | CHAIN7-J-K | CHAIN7-S |
| --- | --- | --- | --- |
| **qwen2.5:7b** | 10/10 | 10/10 | 9/10 |
| **qwen2.5-coder:7b** | 10/10 | 10/10 | 10/10 |
| gemma3:4b | 6/10 | 0/10 | 0/10 |
| exaone3.5:7.8b | **0/10** | **0/10** | **0/10** |

### 기기별 재현성

| 모델 | | 윤기(cuda) | 주호(cuda) |
| --- | --- | --- | --- |
| exaone3.5:7.8b | J-E / J-K / S | 0/5 · 0/5 · 0/5 | 0/5 · 0/5 · 0/5 |
| qwen2.5:7b | J-E / J-K / S | 5/5 · 5/5 · 5/5 | 5/5 · 5/5 · **4/5** |
| gemma3:4b | J-E / J-K / S | **4/5** · 0/5 · 0/5 | **2/5** · 0/5 · 0/5 |
| qwen2.5-coder:7b | J-E / J-K / S | 5/5 · 5/5 · 5/5 | 5/5 · 5/5 · 5/5 |

exaone의 전멸과 qwen2.5-coder:7b의 완주는 기기 독립적으로 재현됩니다.
gemma3:4b의 "E가 K보다 우세" 방향은 두 기기에서 같지만 폭은 다릅니다
(4/5 vs 2/5) — 표본이 작아 기기별 편차인지 우연인지는 더 봐야 압니다.
qwen2.5:7b의 S 1회 실패(주호, rep4/seed45)는 3단계(`CHAIN7S_JSADD`)에서
`lost_cta`로 3회 재시도 전부 실패 — cta 블록을 통째로 빠뜨린 경우로,
qwen2.5:7b치고는 드문 실패라 우연 변동으로 보입니다.

### §3의 두 비교가 실제로 무엇을 보여줬나

- **CHAIN7-J-E vs CHAIN7-J-K(값 수정 방법)** — qwen 두 모델은 동률(10/10
  둘 다)이라 이 표본에서는 갈리지 않았습니다. gemma3:4b에서만 격차가
  뚜렷합니다(E 6/10 vs K 0/10, 두 기기 모두 같은 방향) — pipeline.md §4가
  "보류"로 남긴 질문에 대해, 적어도 gemma3:4b 기준으로는 **E(전체재작성)가
  K(미니패치)보다 실제 템플릿 스케일에서도 우세**하다는 증거입니다.
  CHAIN6(인공 문서, K가 15/15로 만점)과 반대 방향인데, CHAIN6은 애초에
  이 축만 단독으로 격리해서 잰 게 아니었으므로(§3) 직접 비교는 불가 —
  이 축만 격리해서 잰 건 v7이 처음입니다.
- **CHAIN7-J-K vs CHAIN7-S(생성 노선)** — qwen2.5-coder:7b는 동률(10/10
  둘 다), qwen2.5:7b는 근소한 차이(10/10 vs 9/10, 우연 변동으로 보임 —
  위 "기기별 재현성" 참고), gemma3:4b는 둘 다 0/10이라 이 표본에서는
  "노선 차이"가 뚜렷하게 드러나지 않았습니다(값수정 단계 이전에 이미
  막히는 모델은 노선 비교 자체가 무의미 — gemma3:4b의 CHAIN7-S 실패는
  3단계 맨눈변환에서 나는데, CHAIN7-J-K도 4단계에서 막히므로 "어느
  단계가 원인인지"는 또 다른 얘기입니다. 아래 참고).

### 모델별 실패 지점 (CSV `fails` 컬럼 직접 대조)

- **exaone3.5:7.8b — 세 변형 전부 0/10(2기기 모두), 그런데 원인은 두
  가지로 갈립니다**:
  - CHAIN7-J는 **1단계(J-T 생성)에서부터 막힘** — 10/10 전부 `placeholder`
    (대괄호·마크다운 강조 기호를 필드 값에 섞어 냄). v5의 J-T 결과
    (exaone 1/50)와 정확히 같은 결함이 여기서도 재현됩니다. 1단계가
    막히니 2~4단계는 전부 `chain_blocked_by_previous_stage_failure`로
    스킵됩니다.
  - CHAIN7-S는 **1·2단계(S-T 생성, E수정)는 10/10 전원 성공**(v5의 S-T
    결과 47/50과 일치) — 그런데 **3단계(맨눈 HTML→JSON 변환)에서
    10/10 전부 실패**합니다. 원문을 직접 열어보니 원인이 명확합니다 —
    `title`/`items`/`label` 같은 JSON 텍스트 필드 안에 `<h1>`, `<li>`,
    `<strong>`, 심지어 `<style>` 블록까지 그대로 박아 넣습니다(예:
    `"label":"<button ...><span>...</span></button></div><style>..."`).
    이건 v5가 이미 확인한 exaone의 결함(`tag_in_field_*`, J-T 전체
    실패의 핵심 원인)이 "맨눈 변환"이라는 새 과제에서도 똑같이
    나타난다는 뜻입니다 — **exaone은 순수 텍스트만 담아야 하는 JSON
    필드에 마크업을 못 뺍니다.** 저희 내용보존 검사(`content_drift_*`)는
    이 마크업 오염을 "원본과 안 맞음"으로 부수적으로 잡아냈습니다(따로
    태그 검사를 안 만들었는데도 잡힌 것 — 검사 설계가 예상보다 더
    잘 작동한 사례).
- **gemma3:4b — CHAIN7-J-K 실패 원인은 `no_ops` 계열**(`missing_reason`
  + `countdown_setfield_missing`, 각 27건, 2기기 합산) — v2·v4에서 이미
  반복 확인된 "패치 오퍼레이션을 아예 안 냄" 패턴이 여기서도 재현.
  CHAIN7-S 3단계 실패는 `content_drift_benefits`/`content_drift_steps`
  (각 27건) — exaone과 달리 태그 오염이 아니라 **항목 내용 자체가
  바뀜**(재작성·요약 추정, 원문 재확인 필요).
- **qwen2.5:7b·qwen2.5-coder:7b — 거의 전 변형 만점.** qwen2.5-coder:7b는
  2기기·3변형 전부 10/10, qwen2.5:7b는 J-E/J-K 10/10·S만 9/10(주호
  1회, 우연 변동으로 보임). v4(수정)·v5(생성)에 이어 이번(생성→수정→
  JS-PLAN추가→값수정 전체 파이프라인)에서도 사실상 무결점 —
  지금까지의 모든 버전을 통틀어 가장 일관된 결과입니다.

### 결론

- **qwen2.5:7b·qwen2.5-coder:7b는 최종 후보 판정을 다시 한번 강화합니다**
  — 전체 파이프라인(생성→수정→JS-PLAN추가→값수정)을 노선·값수정 방법
  무관하게, 2기기에 걸쳐 거의 완주합니다.
- **exaone3.5:7.8b는 J(JSON) 관련 모든 축에서 탈락 사유가 겹칩니다** —
  생성(J-T, v5)·수정(K-T, v4)·이번 맨눈변환(v7) 전부 "텍스트 필드에
  마크업을 못 뺀다"는 같은 결함의 변주이고, 2기기 모두에서 재현됩니다.
  S(HTML) 경로 단독으로만 쓴다면(생성 47/50, 수정 20/25) 여전히 쓸
  만하지만, JSON을 다뤄야 하는 어떤 단계에도 이 모델을 넣으면 안 됩니다.
- **gemma3:4b는 값수정 축에서 E가 K보다 우세하다는 증거**를
  냈습니다(6/10 vs 0/10, 두 기기 모두 같은 방향) — pipeline.md §4의
  "보류"를 푸는 데 2기기 표본으로는 이 정도가 현재까지의 근거입니다.
  더 많은 기기·회차로 재확인하면 더 굳어질 여지가 있습니다.

## 8. 참고 자료 — 팀 원류 문서(Notion)

[Ollama 모델 테스트 (Notion)](https://app.notion.com/p/kwondoha/Ollama-3dc7b7c7e4b080fbb303d723af223d2c) —
`benchmark_v8.py`의 개발 로그 + 실측 결과 문서. git
저장소보다 먼저 있었던 원류 문서로, exaone3.5:7.8b digest
(`c7c4e3d1ca22fe92`)가 이 세션의 v5·v7 결과와 정확히 일치해서 같은
계보임을 확인했습니다. v1~v7 전체에 깔린 설계 원칙 상당수가 여기서
나온 실측 근거입니다 — CHAIN7과 특히 관련 있는 것만 추립니다.

| 이 문서의 발견 | CHAIN7(v7)과의 연결 |
| --- | --- |
| ①형태규칙 없으면 1차 통과 0/20(재시도로 복구는 되나 비용 2배) | `SYSTEM_JT7`/`SYSTEM_ST7`가 태그 형태를 명시하는 이유. CHAIN7의 3·4단계 프롬프트도 동일 원칙 적용 |
| ②장문+전체재생성=붕괴(exaone E4 0/10), 블록왕복은 안 무너짐 | CHAIN7의 2단계가 항상 "cta 블록만" 왕복 편집인 이유. §7에서 CHAIN7-J-E(전체재작성)가 gemma3:4b에서 실패하는 것도 같은 계열 위험 |
| ③출력범위를 프롬프트로 통제 못함 → 서버가 조각/전체 판별 | CHAIN7-J의 3단계는 반대로 **모델에게 "전체 재출력"을 정면으로 요구**하는 설계라, 이 위험을 그대로 안고 갑니다 — §4 위험요소의 근거 |
| ④요청 외 영역 오염(`diff_unintended`), exaone 최다 | CHAIN7의 새 "내용보존" 검사(`content_drift_*`, §5)는 사실상 이 `diff_unintended` 개념을 JS-PLAN 재출력 상황에 맞게 새로 구현한 것 — §7에서 exaone의 CHAIN7-S 실패(태그 오염)와 gemma3:4b의 CHAIN7-S 실패(내용 왜곡)가 전부 이 계열 |
| ⑤환각은 재시도로 안 고쳐짐 → 혜택은 폼으로만 | CHAIN7도 benefits/steps 값을 프롬프트가 준 대로만 쓰게 하고, 지어낼 여지를 주지 않음(v5 ST/JT 프롬프트 그대로 상속) |
| ⑥JS는 모델마다 갈림("7~8B는 JS 못한다"는 틀린 통념) | CHAIN7이 처음으로 JS-PLAN(인터랙션) 자체를 실전 체인에 넣어본 이유와 맞닿음 — §1 |
| ⑧코드펜스 52%, 파서 필수 | `_run_stage`가 `extract()`/`FENCE.sub()`로 코드펜스를 항상 벗겨내는 이유(v3에서 그대로 복붙) |

**모델 순위 관련 — 참고할 차이점**: 이 문서의 최종 결론(6개 모델
전체, 재시도 제외 1차 시도 기준)은 **qwen2.5-coder:7b가 명확한
1위**(442/600, 74%)였고 qwen2.5:7b는 2위(410/600, 68%)였습니다 —
근거는 "C군(누적 5단계 수정)을 4환경 전부 유일하게 완주" +
"diff_unintended 0회". 이 세션의 v4·v5·v7(실제 템플릿 스케일, 재시도
포함 최종 기준)에서는 둘이 **완전 동률**로 나왔습니다(§7 포함).
측정 조건(인공 문서·1차시도 vs 실제 템플릿·최종)이 다르니 모순은
아니지만, "이 둘 중 굳이 하나만 고른다면" 이라는 질문에는 원류
문서가 이미 qwen2.5-coder:7b 쪽 근거(체인 완주·diff_unintended 0)를
갖고 있었다는 점은 기록해 둘 가치가 있습니다 — CHAIN7-J-K는 정확히
이 "체인 완주 능력"을 다시 재는 축이기도 합니다(§3).
