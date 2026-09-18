# v5 — 신규 생성, 실제 크기로 재기 (S-T vs J-T)

**실행 완료.** 4개 모델(exaone3.5:7.8b·qwen2.5:7b·gemma3:4b·qwen2.5-coder:7b) ×
2기기(윤기·주호)로 측정 끝났습니다 — 결과는 §5 참고. 추가 기기에서
더 돌려서 재현성을 보강하고 싶다면 §4 "실행" 절대로 실행하면 됩니다.
`python base/run.py v5 --self-check`로 LLM 호출 없이 코드 검증만 할 수도
있습니다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md)를 그대로 따릅니다.

## 0. 왜 v5인가 — v4가 남긴 구멍

v4([docs/reports/v1/pipeline.md](../../docs/reports/v1/pipeline.md) §1)는 "수정"(S-E vs
K-T)만 실제 제품 템플릿 크기로 쟀습니다. "생성"(S-T vs J-T)은 실제 크기로
만들면 출력 토큰이 1,985~2,443인데 html 캡이 1536이라 **v4 범위에서
통째로 뺐습니다.**

그런데 v4의 핵심 발견 — "인공 문서에서 J가 유리해 보인 결론이 실제 크기에서
뒤집혔다" — 는 지금 신규 생성 축에서는 아직 검증된 적이 없습니다. v2의
S↔J 신규 생성 비교(McNemar 검정)는 **여전히 인공 문서(370~590자) 기준**이고,
qwen 계열은 그 비교에서 완전 동률(불일치 0쌍)이었습니다. v4가 수정 축에서
보여준 패턴("인공 문서 조건에서 유리해 보인 J가 실제 크기에서 밀린다")이
생성 축에도 똑같이 적용될지, 아니면 생성은 다를지 — **지금 데이터로는
확정할 수 없습니다.**

v5는 이 구멍 하나만 채웁니다. 새 버전인 이유는 두 가지입니다.

1. v4가 이미 "수정"이라는 이름으로 범위를 확정했고([docs/reports/v1/v-summary.md](../../docs/reports/v1/v-summary.md)
   §v4), "생성"은 애초에 다른 질문입니다 — 같은 버전에 욱여넣으면 v4
   결과 해석("S-E vs K-T")과 섞여 혼란만 커집니다.
2. `base/checks_v4.py`를 `versions/v4/`에서 `base/`로 옮겼습니다(v4
   README가 "팀 합의 후 v5부터 표준으로 쓸 거라면 그때 base/로 옮긴다"고
   예고해둔 대로). v4의 `cases_se.py`/`cases_kt.py`는 코드 변경 없이
   그대로 재현됩니다(옮긴 뒤 v4 self-check로 확인함) — import 위치만
   바뀌었지 로직은 그대로입니다.

## 1. 무엇을 재나

|  | S-T | J-T |
| --- | --- | --- |
| LLM이 내는 것 | `<section>` HTML 4개(hero·benefits·steps·cta) | 같은 4블록의 plan JSON |
| 마크업 소유 | LLM | 서버(`registry.render_plan()`) |
| 채점 | `checks_v4.check_product_rules` (블록별 class 계약) | 렌더링 후 같은 채점 + `check_tag_in_fields` |
| baseline | 없음(신규 생성이므로) | 없음 |

v4의 S-E/K-T는 baseline(실제 템플릿 블록)이 있어서 "그 클래스가 살아있는가"로
쟀지만, 신규 생성은 baseline이 없습니다. 그래서 `checks_v4.CONTRACT_CLASSES`의
최소 계약(블록당 2개 클래스, 예: hero → `ev-block block-hero`)을 씁니다.
**이 클래스 이름은 시스템 프롬프트에 명시적으로 박아뒀습니다** — 안
알려주면 모델이 맞힐 수 없는 기준이기 때문입니다(`cases_st.py`의
`self_check`가 프롬프트와 `CONTRACT_CLASSES`가 어긋나면 바로 잡습니다).

## 2. 케이스

요청 문구는 실제 템플릿 5종(`template/template_1~5.html`)의 주제를
참고했지만, 그 문서를 그대로 베끼라는 게 아니라 **같은 분량**(혜택
3개·참여 단계 3개)을 요구하는 신규 생성 요청입니다.

| S-T | J-T | 주제 |
| --- | --- | --- |
| ST1 | JT1 | 스포츠 응원 |
| ST2 | JT2 | 명절 선물 |
| ST3 | JT3 | 멤버십 감사 |
| ST4 | JT4 | 플래시 세일 |
| ST5 | JT5 | 사전예약 |

**요청 문구는 두 파일이 글자 그대로 같아야 합니다** — `cases_jt.py`의
self_check가 이걸 강제합니다(v4 `cases_se`/`cases_kt`, v1 `cases_ns`/v2
`cases_j`와 같은 규약).

## 3. num_predict — 케이스 단위로만 3072

```python
# 기본(base/engine.py)
NUM_PREDICT = {"html": 1536, "plan": 512, "patch": 256, "router": 128}

# v5 케이스만 오버라이드 (Case.num_predict, v3에서 도입)
NUM_PREDICT_T = 3072
```

v3 때와 같은 이유입니다 — 전역 상수를 바꾸면 v1~v4를 재실행할 때도 값이
바뀌어버려 "예전 버전은 그 조건 그대로 재현 가능해야 한다"는 원칙과
충돌합니다. S-T·J-T 둘 다 케이스 단위로만 캡을 올렸습니다.

## 4. 실행

```bash
export RUNNER="<본인이름>"          # Windows: set RUNNER=<본인이름>
python base/run.py v5              # 전체 (S-T + J-T)
python base/run.py v5 S-T          # S-T군만
python base/run.py v5 J-T          # J-T군만
python base/run.py v5 --self-check # LLM 호출 없이 검증만
```

결과는 다른 버전과 동일한 위치로 들어간다: `versions/v5/result_csv/`,
`versions/v5/result_json/`, `versions/v5/raw_v5/`. 이 버전의 모든 케이스는
`num_predict`가 3072로 케이스 단위 오버라이드돼 있다 — v1·v2·v4보다
한 호출당 최대 대기 시간이 늘 수 있다는 점을 감안할 것.

비교표:

```bash
python tools/summarize.py versions/v5
```

> `tools/summarize.py`가 하이픈 포함 그룹명(v3의 JS-HTML 등)을 "모델 x 군"
> 표에서 누락시키는 버그가 있었습니다(세션에서 발견, 공식 CSV 재집계로
> 우회함). S-T/J-T도 하이픈이 있는 이름이라 같은 문제가 있을 수 있으니,
> 표가 비어 보이면 CSV를 직접 확인할 것.

## 5. 결과 / 결론

실행 완료. 2기기 종합(윤기 cuda, 주호 cuda/RTX 4060 8GB — CSV 라벨은
cpu로 잘못 찍혀 있음, 아래 "기기 표기" 참고), 4개 모델 × S-T/J-T ×
5케이스 × 5회차, 총 542행. 드리프트 윤기 0.978, 주호 0.998 — 둘 다
정상 범위.

### 최종 통과율 (재시도 포함, 2기기 합산)

| 모델 | J-T | S-T | 합계 |
| --- | --- | --- | --- |
| **qwen2.5:7b** | 50/50 | 50/50 | **100/100 (100%)** |
| **qwen2.5-coder:7b** | 50/50 | 50/50 | **100/100 (100%)** |
| gemma3:4b | 41/50 | 43/50 | 84/100 (84%) |
| exaone3.5:7.8b | **1/50** | 47/50 | 48/100 (48%) |

### 기기별 재현성

| 모델 | 군 | 윤기(cuda) | 주호(cuda, RTX 4060 — CSV엔 cpu로 오표시) |
| --- | --- | --- | --- |
| exaone3.5:7.8b | S-T | 23/25 | 24/25 |
| exaone3.5:7.8b | J-T | **0/25** | **1/25** |
| qwen2.5:7b | S-T | 25/25 | 25/25 |
| qwen2.5:7b | J-T | 25/25 | 25/25 |
| gemma3:4b | S-T | 21/25 | 22/25 |
| gemma3:4b | J-T | 22/25 | 19/25 |
| qwen2.5-coder:7b | S-T | 25/25 | 25/25 |
| qwen2.5-coder:7b | J-T | 25/25 | 25/25 |

exaone의 J-T 전멸은 기기 독립적으로 재현됨(0/25, 1/25) — 특정 기기의
우연이 아니라 모델 자체의 결함으로 판단.

### 핵심 발견 — v4의 "S가 J보다 안전하다"는 결론은 신규 생성에는 그대로 적용되지 않는다

v4([docs/reports/v1/v-summary.md](../../docs/reports/v1/v-summary.md) §v4)는
"수정" 경로에서 S(HTML)가 J(JSON)보다 확실히 우세했다. 그런데 "신규 생성"
에서는 그 격차가 사라지거나 반대로 나타난다.

- **qwen2.5:7b·qwen2.5-coder:7b — 완전 동률(둘 다 100%).** 두 후보 모델은
  S-T·J-T 어느 경로로 신규 생성을 시켜도 흠이 없다. v4에서 이미 "수정
  경로 1순위"였던 이 둘이, 생성 경로에서도 J를 써도 무방하다는 뜻이다.
- **gemma3:4b — 오히려 J-T가 근소 우위**(41 vs 43, 기기별로는 갈림). 수정
  경로에서 K-T가 전멸(v4, 0~1/25)했던 것과 대조적으로, 생성 경로의
  J-T는 그 정도로 나쁘지 않다 — "gemma3:4b는 JSON을 다 못한다"가 아니라
  "gemma3:4b는 기존 마크업을 JSON 패치로 바꾸는 걸 못한다"가 더 정확한
  진단이다.
- **exaone3.5:7.8b만 J-T에서 전멸(1/50).** CSV의 `fails` 컬럼을 직접
  까보면 실패 사유가 전부 `placeholder`(대괄호 자리표시자 잔존) 또는
  `tag_in_field_steps_items`/`tag_in_field_benefits_items`(plan의 텍스트
  필드에 HTML 태그를 섞어 넣음) 조합이다. 같은 모델의 S-T는 47/50으로
  정상 — **HTML을 직접 쓰게 하면 문제없이 잘 만드는데, "plan JSON의
  텍스트 필드에는 태그를 넣지 마라"는 규칙만 못 지킨다.** exaone이 v2에서
  K(패치)에 강했던 것과는 다른 결함 지점 — 패치 오퍼레이션 자체보다
  "텍스트 필드에만 순수 텍스트를 넣기"라는 더 기초적인 지시를 어긴다.

### 실패 유형 분포 (전체 542건)

| 유형 | 건수 | 비율 |
| --- | --- | --- |
| placeholder | 175 | 32% |
| tag_in_field_steps_items | 66 | 12% |
| tag_in_field_benefits_items | 30 | 6% |
| mismatched_nesting_ol | 12 | 2% |
| mismatched_nesting_li | 7 | 1% |
| duplicate_data_block_benefits | 2 | 0% |
| unclosed_tags_h1 / class_lost / lost_cta | 각 1 | 0% |

`tag_in_field_*`는 J-T 전용 검사(`checks_v4.check_tag_in_fields`)라
S-T에는 나타나지 않는다 — S-T/J-T는 채점 대상 실패 종류 자체가 다르므로
(§1 표 참고), 이 표는 "어느 군이 더 많이 틀렸나"가 아니라 "어떤 실패가
실제로 발생했나"로만 읽을 것.

### 기기 표기에 대한 주의

주호 기기의 `backend`는 "cpu"로 기록됐지만(`gpu`: "cpu-only 또는 감지
실패"), 실제 사양은 32GB RAM / **NVIDIA RTX 4060 8GB** — GPU가 분명히
있는데 감지가 실패해 "cpu"로 잘못 찍힌 것으로 확인됐다. 실측 생성
속도(gemma3:4b 기준 회차 평균 57~61 tok/s)가 순수 CPU 추론치고
비정상적으로 빨랐던 것도 이걸로 설명된다. v4 README가 이미 지적한
한계("`backend` 라벨이 `nvidia-smi` 유무로만 판단해 GPU 기기를 잘못
표시")가 NVIDIA GPU에서도 재현된 셈이다(드라이버 인식 문제 등으로
`nvidia-smi`가 이 기기에서 실패한 것으로 추정 — 원인은 미확인).
위 재현성 표의 pass/fail 결과 자체는 이 라벨 오류와 무관하지만(정확도
채점은 backend와 무관), **절대 응답시간을 근거로 쓰지 말 것** — §4의
원칙(같은 runner 열 안에서만 비교) 그대로 유지한다. 이 라벨링 버그
자체는 v5 범위 밖이니 `base/engine.py`의 `nvidia-smi` 기반 backend
감지 로직 쪽을 팀에 공유해서 별도로 고치는 게 맞다.

### 결론

- **qwen2.5:7b·qwen2.5-coder:7b는 "수정"에 이어 "신규 생성"에서도
  S/J 경로 무관 완전 무결점** — v4에서 내린 1순위 판정이 생성 축에서도
  그대로 유지되고 오히려 더 강화됨(J 경로도 부담 없이 쓸 수 있음이
  확인됨).
- **exaone3.5:7.8b는 J(JSON) 경로를 "생성"에 쓰면 안 된다** — 수정
  경로(K-T, v4)에서도 `class_lost`가 재현됐고, 생성 경로(J-T)에서는
  아예 텍스트 필드 규칙을 못 지켜 전멸한다. S(HTML) 경로 단독으로만
  쓴다면 이 모델도 47/50으로 쓸 만하다.
- **gemma3:4b는 여전히 탈락권** — 생성 경로 자체는 84%로 나쁘지 않지만,
  v2·v3·v4에 걸쳐 반복 확인된 "수정·패치·JS-PATCH 전멸" 패턴([docs/reports/v1/모델선정_종합보고서.md](../../docs/reports/v1/모델선정_종합보고서.md)
  §3)이 더 크게 작용한다. 신규 생성만 시키는 용도가 아니라면 후보에서
  제외 유지.

## 6. 남은 확인 사항 (v5로도 안 풀리는 것)

- **CHAIN7**: 신규 생성 축(S-T vs J-T)이 여기서 확정되면, "그 결과 →
  E수정 → JS-PLAN추가 → 값수정"까지 이어지는 전체 파이프라인을 그대로
  재는 CHAIN7이 필요합니다([docs/reports/v1/pipeline.md](../../docs/reports/v1/pipeline.md)
  §4 "다음 단계"). v5 범위 밖입니다.
- **전역 CSS 전파**: J만 가능한 기능 — 성능이 아니라 제품 요구사항
  판단이라 이 문서가 답할 문제가 아닙니다.
- K-T와 마찬가지로 J-T도 `component_library.py`가 실제 템플릿과 다른
  Tailwind 마크업을 내므로, J-T의 class 계약 검사는 `check_rendered`가
  대신 잡아줍니다(렌더 결과 기준) — 다만 S-T와 J-T를 비교할 때는
  `checks_v4.split_fails()`의 공통 실패만 쓸 것(v4와 동일한 원칙).
