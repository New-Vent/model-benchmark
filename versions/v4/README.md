# v4 — 실제 제품 템플릿으로 S와 J를 같은 자로 재기

v1-v3은 인공 문서(370-590자)를 `ul li` 같은 **벤치마크 전용 규격**으로 채점했습니다.
v4는 **실제 서비스 템플릿**(`template/template_1~5.html`, 4,351~5,356자)을 baseline으로 쓰고,
두 노선을 **같은 검사기**로 채점합니다.

공통 원칙은 [docs/common/methodology.md](../../docs/common/methodology.md)

---

# 결론

## 1. 수정 경로는 S(HTML 블록 편집)가 낫다

| 모델 | S-E 도하 · 주호 | K-T 도하 · 주호 |
| --- | --- | --- |
| **qwen2.5:7b** | **25/25 · 25/25** | 15/25 · 15/25 |
| **qwen2.5-coder:7b** | **25/25 · 25/25** | 13/25 · 13/25 |
| exaone3.5:7.8b | 20/25 · 20/25 | 13/25 · 15/25 |
| gemma3:4b | 16/25 · 19/25 | 0/25 · 1/25 |

**v2에서 J·K가 유리해 보였던 것은 인공 문서 조건이었습니다.** 실제 제품 마크업에서는 뒤집힙니다.

## 2. 클래스가 안 깨지는 건 J,S가 똑같다

J를 쓰는 핵심 이유가 "서버가 마크업을 소유하니 클래스가 안 깨진다"였는데,
**적절한 모델을 고르면 S도 안 깨뜨립니다.**

```
S-E 제품 규격 위반 (class_lost · inline_style · theme_leaked · nested_section · data_block_changed)
  qwen2.5:7b        도하 0건 · 주호 0건   (50행)
  qwen2.5-coder:7b  도하 0건 · 주호 0건   (50행)
  exaone3.5:7.8b    도하 15건 · 주호 15건  ← 모델 특성, 두 기기 동일
```

## 3. K는 구조 변경을 못 한다

| 모델 | 문구 교체 (KT1·KT2) | 구조 변경 (KT3·KT4) |
| --- | --- | --- |
| qwen2.5:7b | **20/20** | 7/20 |
| qwen2.5-coder:7b | **20/20** | 4/20 |
| exaone3.5:7.8b | **20/20** | 3/20 |

지배적 실패는 `no_ops` — **패치 오퍼레이션을 아예 안 냅니다.**
"혜택 하나 빼줘"는 실사용에서 흔한 요청인데 KT3는 네 모델 전부 0/5입니다.

## 4. 모델

| 모델 | 판정 |
| --- | --- |
| **qwen2.5:7b** | S-E 만점 · 규격 위반 0 · 기기 재현 — **선정 후보** |
| **qwen2.5-coder:7b** | 동급. S-E·K-T 모두 두 기기 수치 완전 일치 |
| exaone3.5:7.8b | S-E 20/25 — `class_lost` 15 · `item_count_steps` 15 (재현되는 모델 특성) |
| gemma3:4b | **탈락** — K-T 0/25, 마크업 파손, 기기 일치도 80%로 최저 |

## 5. 아직 결정 못 하는 것 3가지

| | 왜 |
| --- | --- |
| **신규 생성 (S-T vs J-T)** | `num_predict` 초과(2,000~2,400 tok > 1536)로 미측정 |
| **누적 수정 5단계** | v3의 CHAIN5(E×5) ↔ CHAIN6(K×5) 소관 |
| **전역 CSS 전파** | J만 가능 — 성능이 아니라 **제품 요구사항 판단** |

---

# 무엇을 봤나

## 채점기를 통일한 것이 핵심입니다

이전까지 S는 `check_html`, J는 `check_plan`으로 **서로 다른 함수**로 채점한 점수를 나란히
비교하고 있었습니다. 실패 이름도 검사 항목도 달랐습니다.

```
S :  LLM ─────────────────────→ HTML  ┐
                                       ├→ 같은 검사기 → 비교 성립
J :  LLM → plan → render_plan() → HTML ┘
```

| # | 문제 | 변경 | 결과 |
| --- | --- | --- | --- |
| 1 | 채점기가 둘로 갈려 있었음 | 최종 HTML 기준 `check_rendered()` | 비교가 처음으로 같은 의미를 가짐 |
| 2 | `check_plan`에 `bad_tag_*` 없음 | `tag_in_field_*` 신설 | J 점수의 부풀림 제거 |
| 3 | 클래스 보존을 아무도 검사 안 함 | 제품 규격 5종 신설 | S가 지켜야 할 것을 실제로 잼 |
| 4 | 인공 문서로만 측정 | 실제 템플릿 baseline | **결론이 뒤집힘** |
| 5 | 검사 항목 수 비대칭 | `split_fails()` 공통/전용 분리 | 항목 수가 점수를 왜곡하지 않음 |

**신설된 실패 이름**

```
class_lost            디자인 클래스 유실        (baseline 대조 — 고정 목록 아님)
data_block_changed    data-block 값 변경·삭제
inline_style          인라인 CSS 주입
theme_leaked          theme-* 를 블록 안에 복사
nested_section        section 중첩 (innerHTML만 반환)
item_count_<블록>      수정 후 항목 수가 기대와 다름
tag_in_field_<블록>_<필드>   plan 텍스트 필드에 태그 주입
```

`base/checks.py`·`engine.py`·`registry.py`는 건드리지 않음. v1·v2 결과는 그대로 재현됩니다.

## 문서가 커지자 새 실패가 나타났습니다

| 대상 | 마크업 파손 |
| --- | --- |
| v1 (인공 370~590자, 4,172행) | **0건** |
| v2 (인공, JSON, 857행) | **0건** |
| **v4 S-E (실제 1,000~1,500자)** | `unmatched_closing_tag_div` · `mismatched_nesting_section` |

전부 gemma3:4b입니다. **"232자 HTML은 세 모델이 완벽히 복사했다"(v1)는 관찰이
크기 조건부였음이 확인됐습니다.**

## 기기 간 재현성 — 90%

| 모델 | 케이스 단위 판정 일치 |
| --- | --- |
| qwen2.5:7b | 48/50 = **96%** |
| exaone3.5:7.8b | 46/50 = 92% |
| qwen2.5-coder:7b | 46/50 = 92% |
| gemma3:4b | 40/50 = **80%** |
| 전체 | 180/200 = **90%** |

methodology §9의 "다른 기기, 통과 여부 일치 92%"와 같은 수준입니다.
**gemma만 80%로 낮은데**, 마크업 파손·`no_json` 같은 불안정한 실패를 내기 때문입니다 —
부동소수점 차이로 판정이 뒤집힐 만큼 아슬아슬한 출력이라는 뜻입니다.

exaone의 `class_lost` 15건과 `item_count_steps` 15건은 **두 기기에서 정확히 같은 수**입니다.
기기 노이즈가 아니라 재현되는 모델 특성입니다.

## 사고 기록 

`registry.py`의 `must` 셀렉터(`ul li` / `ol li` / `a`)가 벤치마크 전용 규격이라
**실제 템플릿 원본을 넣어도 20개 중 15개가 떨어졌습니다.** 그 오탐이 재시도를 유발했고,
재시도 되먹임("`<ul><li>`로 나열하세요")을 모델이 충실히 따라 **클래스를 깨뜨렸습니다.**

```
class_lost 발생 시점 — 1차 0건 · 2차 20건 · 3차 20건
```

**틀린 지시가 모델을 망가뜨린 것**이지 모델 탓이 아니었습니다.
역설적으로 "재시도 되먹임은 '무엇을 고쳐라'를 말할 때 작동한다"는 발견을 재확인합니다.

재발 방지로 `cases_se.py`의 `self_check()`에 **"실제 템플릿 원본을 그대로 넣으면 통과해야 한다"**
회귀 검사를 넣었습니다. `keep`을 다시 채우면 self-check가 바로 실패합니다.

---

# 구성

| 파일 | 내용 |
| --- | --- |
| `checks_v4.py` | 통일 채점기 + 제품 규격 5종 |
| `templates.py` | 실제 템플릿 로더 — `block_html()` · `plan_of()` |
| `cases_se.py` | S-E — 실제 블록을 HTML로 수정 (5) |
| `cases_kt.py` | K-T — 같은 요청을 패치 JSON으로 (5) |

**요청 문구는 S-E와 K-T가 글자 그대로 같습니다.** `cases_kt.self_check()`가 `cases_se`를
import해서 강제하므로, 한쪽만 고치면 self-check가 실패합니다.

| pair | 요청 | 템플릿 · 블록 |
| --- | --- | --- |
| SE1 ↔ KT1 | 버튼 문구를 '지금 응원하기'로 | 1 sports · cta |
| SE2 ↔ KT2 | 제목을 '설 선물 대축제'로 | 2 holiday · hero |
| SE3 ↔ KT3 | 혜택 마지막 항목 삭제 | 3 vip · benefits |
| SE4 ↔ KT4 | 혜택 항목 추가 | 4 sale · benefits |
| SE5 ↔ KT5 | 단계 설명 짧게 | 5 launch · steps |

## 왜 수정 경로만 다루나

| 대상 | 출력 토큰 | 캡 | |
| --- | --- | --- | --- |
| 블록 하나 수정 | 133 ~ 660 | html 1536 | OK |
| 패치 오퍼레이션 | 30 ~ 46 | patch 256 | OK |
| 전체 페이지 생성 | 1,985 ~ 2,443 | html 1536 | **초과** |

제품의 주 경로도 블록 단위 수정입니다 — LLM이 전체 문서를 생성하지 않고,
관리자가 클릭해 지정한 단일 `section`만 고칩니다.

## CSV — `run_stamp` 컬럼
여러 번 나눠 실행했고 도하 것은 **CSV 하나로 합쳤습니다.** 기존 29개 컬럼 끝에
`run_stamp`(30번째)를 붙여 각 행이 어느 실행에서 나왔는지 남깁니다.
`env_v4_<runner>_<run_stamp>.json` 과 1:1로 대응합니다.

| runner | backend | 기기 | drift |
| --- | --- | --- | --- |
| 도하 | metal | Apple M3 Pro / macOS 26.6 | 1.037 · 0.977 · 1.111 |
| 주호 | cpu | AMD Ryzen 6000번대 / Windows 11 | 1.000 |

행 수가 모델마다 다른 것은 **재시도** 때문입니다 — 실패가 많을수록 행이 늘어납니다.

## 실행

```bash
export RUNNER="<본인이름>"
python base/run.py v4              # S-E + K-T (10케이스 × 5회)
python base/run.py v4 S-E
python base/run.py v4 --self-check
python tools/summarize.py versions/v4
```

---

# 한계

- **신규 생성(S-T·J-T) 미측정** — `num_predict` 초과. 캡 상향이 선행돼야 함
- **K-T는 클래스 검사를 못 합니다** — `component_library.py`가 Tailwind 마크업을 내므로 렌더 결과가 실제 템플릿과 다름. 그래서 S-E ↔ K-T 비교는 `split_fails()`의 **공통 실패만** 써야 함. 다만 이번 실패는 `no_ops`·`lost_*` 같은 plan 단계 실패라 이 비대칭과 무관
- **`backend=cpu` 라벨 부정확** — `engine.py`가 `nvidia-smi` 유무로만 판단해 AMD·내장 GPU를 못 봄
- `PLACEHOLDER` 정규식이 template_3 steps의 실제 문구 `[쿠폰팩 한번에 받기]`를 자리표시자로 오인. 이번 케이스엔 미사용이나 정규식을 좁힐 필요

---

# 부수 발견 — 공통 클래스 어휘는 이미 있다

5개 템플릿 전부에 있는 클래스를 뽑아보니 **접두사 규칙(`sp-`/`hl-`/`vp-`/`fs-`/`lc-`)이 이미
잘 지켜지고 있습니다.** 서버 소유인 notices는 테마 전용 클래스가 0개입니다.

| 블록 | 5종 공통 클래스 |
| --- | --- |
| hero | `ev-block` `block-hero` `hero-title` `hero-desc` |
| benefits | `ev-block` `block-benefits` `block-header` `sub-label` `title` |
| steps | 위 + `step-content` `step-title` `step-desc` |
| notices | 6개 전부 공통 |
| cta | `ev-block` `block-cta` `cta-btn` `cta-subtext` `btn` |

빠진 건 **반복 항목 컨테이너 하나**뿐입니다.

| | 1 sports | 2 holiday | 3 vip | 4 sale | 5 launch |
| --- | --- | --- | --- | --- | --- |
| benefits 항목 | `benefit-card` | `hl-pouch-card` | `vp-coupon` | `fs-deal-item` | `lc-milestone-item` |
| steps 항목 | `step-card` | `hl-step-item` | `vp-step-row` | `step-card` | `step-card` |

template_1·4가 이미 **공통 + 테마 병기** 방식입니다(`class="benefit-card sp-prize-sub"`).
나머지 셋도 같게 하면 `querySelectorAll('.benefit-card').length` 같은 규칙이 **5종 전부에서
동작하고**, `templates.py`의 `ITEM_SELECTORS` 테이블이 필요 없어집니다.
