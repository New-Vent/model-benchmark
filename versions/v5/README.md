# v5 — 신규 생성, 실제 크기로 재기 (S-T vs J-T)

**구현 완료.** `python base/run.py v5 --self-check`로 LLM 호출 없이 검증 가능합니다.
아직 실제 모델로 돌려서 결과를 낸 적은 없습니다 — 그건 팀이 각자 기기에서
실행해야 하는 다음 단계입니다(§4·§5 "실행"·"결과/결론" 절 참고).

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

_(미착수 — 아직 실제 모델로 돌린 적이 없다. 위 실행 명령으로 각자 기기에서
실행하고 CSV가 모이면 `python tools/summarize.py versions/v5`로 비교표를
뽑아 이 절을 채운다. 우선 qwen2.5:7b·qwen2.5-coder:7b·exaone3.5:7.8b·
gemma3:4b 4개 모델로 — v4와 같은 후보군 — 최소 2기기 이상 채우는 걸
우선한다.)_

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
