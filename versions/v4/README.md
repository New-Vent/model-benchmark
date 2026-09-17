# v4 — 실제 제품 템플릿으로 S와 J를 같은 자로 재기

v1~v3은 인공 문서(370~590자)에 `ul li` 같은 벤치마크 전용 규격으로 측정했습니다.
v4는 **실제 서비스 템플릿**(`template/template_1~5.html`, 4,351~5,356자)을 baseline으로 쓰고,
두 노선을 **같은 검사기**로 채점합니다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md).

## 상태

| 파일 | 내용 | 상태 |
| --- | --- | --- |
| `checks_v4.py` | 통일 채점기 + 제품 규격 검사 5종 | - |
| `templates.py` | 실제 템플릿 로더 (`block_html` · `plan_of`) | - |
| `cases_se.py` | S-E — 실제 블록을 HTML로 수정 (5) | - |
| `cases_kt.py` | K-T — 같은 요청을 패치 JSON으로 (5) | - |

`base/checks.py`·`engine.py`·`registry.py`는 **건드리지 않았습니다.** v1·v2 결과는 그대로 재현됩니다.

---

## 버전4 중점

1. **모델이 `AI_EDIT_RULES.md` §3(클래스 보존)을 지킬 수 있는가** — 못 지키면 HTML 노선 탈락
2. 실제 크기(1,000~1,500자 블록)에서 S와 J 중 무엇이 나은가 — 같은 검사기로 테스트 
3. J의 텍스트 필드 태그 주입이 실제로 얼마나 되는가
4. 실제 분량에서 재시도율·소요시간이 얼마나 늘어나는가

## 1. 문제 → 변경 → 이유 → 바뀌는 것

| # | 문제 | 변경 | 이유 | 바뀌는 것 |
| --- | --- | --- | --- | --- |
| 1 | **S와 J를 다른 채점기로 재고 있었다** (`check_html` vs `check_plan`) | 최종 HTML 기준 `check_rendered()` 신설 | 두 노선의 산출물은 결국 같은 HTML. 다른 자로 잰 숫자는 비교할 수 없음 | "S 100% vs J 77%"가 처음으로 같은 의미를 갖게 됨 |
| 2 | `check_plan`에 **`bad_tag_*` 검사가 없음** | `tag_in_field_*` 신설 | 텍스트 필드에 `<strong>`·`<script>`가 섞여도 통과. v3 감사가 지적한 22건이 이 구멍 | **J 점수가 내려감** (지금은 부풀어 있음) |
| 3 | `AI_EDIT_RULES.md` §3을 **아무도 검사하지 않음** | 제품 규격 5종 신설 | 클래스가 깨지면 디자인이 무너지는데 감점이 없었음 | **S 점수가 내려감** |
| 4 | 인공 문서로만 측정 | 실제 템플릿을 baseline으로 | 실제는 인공의 **8배**. 모든 결론이 작은 문서 조건부였음 | 재시도율·소요시간·실패 분포 전부 재측정 |
| 5 | 검사 항목 수가 비대칭 | `split_fails()` — 공통/전용 분리 | J 전용(`unknown_variant` 등)이 점수를 왜곡 | **공통 실패만으로 비교** |

### 신설된 실패 이름

```
class_lost            디자인 클래스 유실
data_block_changed    data-block 값 변경·삭제
inline_style          인라인 CSS 주입
theme_leaked          theme-* 를 블록 안에 복사
nested_section        section 중첩 (innerHTML만 반환)
tag_in_field_<블록>_<필드>   plan 텍스트 필드에 태그 주입
```

`class_lost`는 **고정 목록이 아니라 baseline 대조**입니다 — 그 템플릿에 실제로 있던 클래스를
뽑아 비교합니다. 테마마다 클래스가 다르므로 고정 목록으로는 5종을 다 못 덮습니다(§3 참고).

---

## 2. `num_predict`를 안 고치고 돌리기 위해 범위를 좁혔다

| 대상 | 출력 토큰 (실측/추정) | 현재 캡 | |
| --- | --- | --- | --- |
| 블록 하나 수정 | hero 660 · benefits 572 · steps 471 · cta 133 | html 1536 | **OK** |
| 패치 오퍼레이션 | 30~46 (v2 실측) | patch 256 | **OK** |
| 전체 페이지 생성 | 1,985 ~ 2,443 | html 1536 | **초과** |

그래서 v4는 **수정(편집) 경로만** 다룹니다. `AI_EDIT_RULES.md` §1-1이 제품의 주 경로를
그렇게 정의합니다 — *"LLM은 전체 HTML 문서를 생성하지 않고, 관리자가 클릭하여 지정한 단일
section을 수정합니다."*

신규 생성은 캡 상향이 선행돼야 합니다. `base/engine.py`가 버전 공용이라 값을 바꾸면 v1·v2
재현성이 깨지므로, **버전별 오버라이드 방식을 먼저 정해야 합니다.**

---

### 3. 공통 클래스 어휘는 이미 있다 — 항목 컨테이너만 안 통일됐다

5개 템플릿 전부에 있는 클래스(= 공통 계약)를 뽑아봤습니다.

| 블록 | 공통 클래스 | 테마 전용 |
| --- | --- | --- |
| hero | `ev-block` `block-hero` `hero-title` `hero-desc` | `sp-` `hl-` `vp-` `fs-` `lc-` |
| benefits | `ev-block` `block-benefits` `block-header` `sub-label` `title` | 〃 |
| steps | `ev-block` `block-steps` `block-header` `sub-label` `title` `step-content` `step-title` `step-desc` | 〃 |
| **notices** | 6개 **전부 공통** (테마 전용 0개) | — |
| cta | `ev-block` `block-cta` `cta-btn` `cta-subtext` `btn` | 〃 |

**접두사 규칙(`sp-`/`hl-`/`vp-`/`fs-`/`lc-`)이 이미 깔끔하게 지켜지고 있습니다.**
서버 소유인 notices는 테마 전용 클래스가 아예 0개라는 점도 설계 의도와 맞습니다.

빠진 건 **반복 항목 컨테이너 하나**뿐입니다.

| 블록 | 1 sports | 2 holiday | 3 vip | 4 sale | 5 launch |
| --- | --- | --- | --- | --- | --- |
| benefits 항목 | `benefit-card` | `hl-pouch-card` | `vp-coupon` | `fs-deal-item` | `lc-milestone-item` |
| steps 항목 | `step-card` | `hl-step-item` | `vp-step-row` | `step-card` | `step-card` |

**통일 가능하고, template_1·4가 이미 그 방식입니다** — `class="benefit-card sp-prize-sub"`,
`class="step-card sp-ticket"`처럼 **공통 클래스 + 테마 클래스를 병기**합니다.
나머지 세 템플릿도 같은 규칙을 적용하면 `.benefit-card` / `.step-card`가 5종 공통이 됩니다.

그렇게 하면 얻는 것:

- `BENCHMARK_TEMPLATE_DIFF.md`가 제안한 `querySelectorAll('.benefit-card').length` 규칙이
  **실제로 동작합니다** (지금은 template_1에서만 맞습니다)
- 프롬프트에 "필수 클래스"를 **한 벌**만 적으면 됩니다 — 테마마다 다른 목록을 줄 필요가 없음
- `templates.py`의 `ITEM_SELECTORS` 테이블이 필요 없어집니다

> **제안**: 공통 어휘를 `event.css` 옆에 문서로 고정하고, 테마 전용은 접두사로만 추가.
> LLM에게는 공통 어휘만 노출하고 테마 클래스는 서버가 붙이는 쪽이 안전합니다.

---

## 4. 남은 비대칭 하나

**K-T는 클래스 보존 검사를 할 수 없습니다.** `component_library.py`가 Tailwind 마크업을 내므로
렌더 결과가 실제 템플릿과 다릅니다.

그래서 **S-E ↔ K-T 비교는 `split_fails()`의 공통 실패만 써야 합니다.**
`class_lost`를 한쪽에만 적용하면 비교가 무너집니다. §3-1의 교체가 끝나면 해소됩니다.

---

## 5. 케이스

요청 문구는 S-E와 K-T가 **글자 그대로 같습니다.** `cases_kt.self_check()`가 `cases_se`를
import해서 이를 강제하므로, 한쪽만 고치면 self-check가 바로 실패합니다.

| pair | 요청 | 템플릿 | 블록 |
| --- | --- | --- | --- |
| SE1 ↔ KT1 | 버튼 문구를 '지금 응원하기'로 | 1 sports | cta |
| SE2 ↔ KT2 | 제목을 '설 선물 대축제'로 | 2 holiday | hero |
| SE3 ↔ KT3 | 혜택 마지막 항목 삭제 | 3 vip | benefits |
| SE4 ↔ KT4 | 혜택 항목 추가 | 4 sale | benefits |
| SE5 ↔ KT5 | 단계 설명 짧게 | 5 launch | steps |

---

## 실행

```bash
export RUNNER="<본인이름>"
python base/run.py v4              # S-E + K-T (10케이스 × 5회)
python base/run.py v4 S-E
python base/run.py v4 --self-check
python tools/summarize.py versions/v4
```

## 결과

_(미실행)_

## 결론

_(미정)_
