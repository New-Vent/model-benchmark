# v8 — Bedrock, 백엔드 레지스트리 기준으로 다시 재기

**구현 완료, 실행 전.** `python versions/v8/run_v8.py --self-check` 로 호출 없이 검증만 가능합니다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md)를 따르되, **v1~v7과
기준선이 다릅니다.** 아래 §1을 먼저 읽으세요.

---

## 1. v8이 v1~v7과 다른 점 세 가지

### ① 기준이 백엔드 레지스트리다 — 템플릿도, 벤치마크 고유 규격도 아니다

| | v1~v3 | v4~v7 | **v8** |
| --- | --- | --- | --- |
| baseline | 인공 문서 | 디자이너 템플릿 5종 | **백엔드 `Block.shape`** |
| 채점 | 벤치마크 `checks.py` | `checks_v4.py` | **백엔드 `BlockValidator` 이식** |
| 프롬프트 | 벤치마크 자체 정의 | 자체 정의 | **백엔드 `PromptBuilder` 이식** |

v4~v7이 쓴 `template/*.html`은 **백엔드가 모델에게 시키는 형태와 다릅니다.**
레지스트리의 cta는 `<a href="#" class="btn">`인데 템플릿은 `<button class="cta-btn">`입니다.
섞으면 v4 때처럼 채점이 또 틀어지므로, v8의 기준은 **레지스트리 하나뿐**입니다.

### ② ★ 정화(sanitize) 뒤를 채점한다

지금까지 벤치마크는 `raw → extract → check` 였습니다.
실제 서비스는 `raw → extract → sanitize → validate` 입니다.

이 차이가 실제 버그를 숨겼습니다 (§3).

v8은 **정화 전과 후를 둘 다 채점**해서 책임을 가릅니다.

| 컬럼 | 뜻 |
| --- | --- |
| `model_fails` | 정화 전에도 실패 → **모델 탓** |
| `pipeline_fails` | 정화 후에만 실패 → **정화 탓.** 모델을 바꿔도 안 고쳐진다 |
| `sanitize_damaged` | 정화가 망가뜨린 출력인가 |

**모델 비교를 하면서 정화 버그를 모델 탓으로 돌리면 엉뚱한 모델을 고르게 됩니다.**

### ③ `base/`를 건드리지 않는다

`base/engine.py`는 Ollama에 깊게 묶여 있고(캘리브레이션·digest·`/api/tags`),
팀 공용이라 "합의 없이 개인이 고치지 않는다"가 규칙입니다. v8은 독립 러너를
씁니다 — **v1~v7 결과는 그대로 재현 가능한 채로 남습니다.**

---

## 2. 군

**HTML 부분 재생성이 기본**입니다 — 매 턴 `edit(block)` 프롬프트에 **그 블록만**
넣어 보냅니다. 전체 문서를 모델에 넘기지 않습니다. 백엔드가 확정한 방식이고
토큰도 훨씬 쌉니다.

| 군 | 대응 | 케이스 | 캡 |
| --- | --- | ---: | ---: |
| **R** 라우터 | `router()` | 8 | 256 |
| **E** 수정 | `edit(block)` | 4 | 1536 |
| **G** 생성 | `generate()` | 2 | 1536 |
| **C** 누적 수정 | `edit` + `merge` 반복 | 2 (6턴) | 1536 |

### v8에 없는 비교축 — 그리고 없는 이유

v1~v7은 **설계를 고르는** 실험이었고, v8은 설계가 확정된 뒤 **모델을 고르는**
실험입니다. 그래서 아래 축은 v8에 없습니다.

| 축 | 결론난 곳 | 백엔드 현재 | v8 |
| --- | --- | --- | --- |
| JSON / HTML | v4·v5 | `PromptBuilder`에 **JSON 경로 없음** | 비교 대상 없음 |
| 부분 / 전체 재생성 | v1 E군·v4 | `edit(block)`+`merge` **확정** | 비교 대상 없음 |

여기에 J 노선을 넣어 비교하려면 **백엔드에 없는 경로를 벤치마크가 새로 만들어야**
합니다. 그건 v4가 저지른 실수(실제와 다른 조건으로 재고 결론 내기)의 반복입니다.

**G·E·R·C는 비교군이 아니라 커버리지입니다** — 넷 다 서비스가 쓰는 경로라
넷 다 통과해야 하고, 서로 우열을 겨루지 않습니다. v8의 비교축은 §2-1입니다.

### 2-1. v8의 실제 비교축 셋

| 축 | 보는 것 |
| --- | --- |
| **모델 × 같은 케이스** | Haiku → 통과하면 멈춤, 실패하면 상위. 로컬 qwen을 대조군으로 |
| **모델 탓 vs 정화 탓** | `model_fails` vs `pipeline_fails` — ★ v8 고유 |
| **1차 vs 최종** | 재시도 의존도 = 과금 2배 |

### R을 제일 먼저 돌리는 이유

v1에서 **R군이 가장 나빴습니다** — 최고가 60% 언저리(exaone 95/240, qwen2.5 144/240).
그런데 백엔드 구조상 라우터는 **모든 기능의 입구**입니다. `op`이나 `target`을
틀리면 멀쩡한 블록을 지우거나 엉뚱한 데를 고칩니다. 생성·수정이 아무리 좋아도
라우터가 틀리면 제품이 안 됩니다.

게다가 라우터는 **제일 쌉니다**(캡 256, 출력 JSON 한 줄).
**가장 위험한 축이 가장 싼 축**이라 여기부터 재는 게 맞습니다.

### 눈여겨볼 케이스

| 케이스 | 무엇을 보나 |
| --- | --- |
| `R1` vs `R4` | "혜택 하나 더 넣어줘"(EDIT) vs "영역이 없는데 새로 넣어줘"(ADD) — 헷갈리는 짝 |
| `R6` | SERVER 블록(notices). 라우터는 target을 맞혀야 하고, **거절은 `Block.denyReason`이 한다** |
| `R8` | 필수 블록 삭제. 라우터는 의도대로 분류하고, **막는 건 서버** |
| `E4` | 구조 줄이기 — v2·v4·v6에서 로컬 모델이 일관되게 회피한 축(K-T 삭제 0/5 전 모델) |
| `E1`·`E2` | `href`·`class`·`data-slot`이 살아남는가 |
| `C1` | 서로 다른 블록 3턴 — **앞 턴의 변경이 끝까지 남는가** |
| `C2` | 같은 블록 3턴, 늘렸다 줄였다 — 구조 축소가 누적에서도 버티는가 |

### C군이 여기서만 볼 수 있는 것 — 정화 손상의 누적

백엔드 실사용은 한 턴으로 안 끝납니다.

```
doc → 그 블록만 꺼내서 edit → sanitize → merge → doc' → (또 고침) → ...
```

**정화는 턴마다 걸립니다.** 1턴에서 잘려나간 채로 문서에 병합되면 그 손상은
**영구히 남습니다.** 1턴짜리 E군으로는 "한 번 잘린다"까지만 보이고, 쌓이는 건
안 보입니다.

`LLM_PROVIDER=mock`(= 아무것도 안 바꾸는 완벽한 모델)로 C1을 3턴 돌린 결과:

```
START_DOC  슬롯: ['period', 'cta-link']   href: ['#']
FINAL_DOC  슬롯: 전부 사라짐               href: 전부 사라짐
```

**모델은 한 글자도 안 틀렸는데 문서가 망가졌습니다.**

---

## 3. 실행 전에 이미 확인된 것 — 호출 0원

`--self-check`가 **백엔드 PR ②번 버그를 그대로 재현합니다.**

```
프롬프트가 예시로 준 것 : <section data-block="cta"><a href="#" class="btn">참여하기</a></section>
정화 후               : <section data-block="cta"><a class="btn">참여하기</a></section>
검증 결과             : 통과 ✅  ← 링크가 죽었는데 통과
```

`Safelist.relaxed()`의 `a[href]` 허용 프로토콜은 `ftp/http/https/mailto`뿐인데,
`Jsoup.clean(html, "", safelist)`로 **baseUri가 비어 있어** 절대화가 실패하고
원래 값(`#`)으로 검사를 받습니다. 어디에도 안 맞아 **속성째 제거**됩니다.

**`#`만의 문제가 아닙니다** — 상대 경로가 전부 같은 이유로 죽습니다.

| href | 결과 |
| --- | --- |
| `#` · `/events/1` · `./next.html` · `?page=2` | **제거** |
| `https://...` | 유지 |

그리고 **`data-slot`도 정화가 지웁니다.** 수정 경로에서는 이게 곧 `slot_lost`입니다
(백엔드 PR이 고치는 중인 ①번 항목).

> 이 두 가지는 **모델을 아무리 바꿔도 안 고쳐집니다.** Bedrock 호출을 한 번도
> 하기 전에 잡을 수 있는 것이라, v8의 첫 성과는 여기입니다.

---

## 4. 실행

```bash
pip install -r requirements.txt      # boto3 포함

# ① 0원 — 배선 확인. mock은 "완벽한 모델"이라 남는 실패는 전부 파이프라인 탓
LLM_PROVIDER=mock RUNNER=도하 python versions/v8/run_v8.py --repeats 1

# ② 호출 없이 코드 검증만
python versions/v8/run_v8.py --self-check

# ③ 라우터만 — 가장 위험하고 가장 싼 축
export BEDROCK_REGION=us-east-1
export BEDROCK_MODEL="anthropic.claude-haiku-4-5-20251001-v1:0"
LLM_PROVIDER=bedrock RUNNER=도하 python versions/v8/run_v8.py --groups R

# ④ 누적 수정만
LLM_PROVIDER=bedrock RUNNER=도하 python versions/v8/run_v8.py --groups C

# ⑤ 전체
LLM_PROVIDER=bedrock RUNNER=도하 python versions/v8/run_v8.py

# 대조군 — 같은 케이스를 로컬로
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b python versions/v8/run_v8.py
```

### 비용

| 범위 | 호출 (재시도 제외) |
| --- | ---: |
| `--groups R --repeats 3` | 24 (전부 캡 256) |
| `--groups E --repeats 3` | 12 |
| `--groups C --repeats 3` | 18 (2케이스 × 3턴 × 3회) |
| 전체 `--repeats 3` | 60 |

### 리전

계정 기본값은 서울(`ap-northeast-2`)인데 **거기엔 Anthropic 모델이 없습니다.**
`AWS_REGION`을 바꾸면 다른 AWS 작업까지 영향을 받으므로, Bedrock 전용으로
`BEDROCK_REGION`을 따로 둡니다(기본 `us-east-1`). 지연 차이 0.2초는 이
워크로드에서 무의미합니다.

실행 끝에 실측 토큰과 단가 계산식을 같이 찍습니다.

```
비용: awk -v i=<입력단가> -v o=<출력단가> 'BEGIN{printf "%.4f USD\n", .../1e6*i + .../1e6*o}'
```

### 싸게 도는 법

1. **`--groups R` 부터.** 가장 위험한 축이 가장 쌉니다.
2. **싼 모델부터, 통과하면 멈춥니다.** 로컬 7B가 0%였던 걸 Haiku가 내면 상위 모델을 살 이유가 없습니다.
3. **`--repeats 3`.** 로컬은 5회였지만 그건 기기 축이 있어서였고, Bedrock은 관리형이라 그 축이 없습니다.
4. **`MAX_RETRY=2`.** 로컬에선 재시도가 시간만 들었지만 여기선 **1회 = 과금 2배**입니다.
5. **1차 통과율을 주지표로.** Bedrock에서는 이게 곧 운영 비용입니다.

---

## 5. 파일

| 파일 | 원본 |
| --- | --- |
| `registry_v8.py` | `registry/Block.java` + `Slot.java` |
| `prompts_v8.py` | `registry/PromptBuilder.java` |
| `checks_v8.py` | `registry/BlockValidator.java` (extract·sanitize·validate·merge) |
| `provider.py` | `infra/llm/LlmClient.java` + Bedrock 구현 |
| `cases_v8.py` | — (v8 고유) |
| `run_v8.py` | — (v8 고유) |

### ⚠ 두 저장소가 갈라지는 문제

v3 README가 경고한 "같은 프롬프트가 두 파일에 중복 보관"이 이제 **저장소를
넘어서** 생겼습니다 — 벤치마크(Python)와 서비스(Java).

**백엔드가 프롬프트·레지스트리·정화를 건드리면 여기도 같이 고쳐야 합니다.**
자동으로 감지할 방법이 없습니다. `self_check()`는 Python 쪽 일관성만 봅니다.

### 현재 백엔드 기준점

`develop` @ `8f39d6a` (`fix: PERIOD 를 슬롯으로 분리하고 CSS 정화 추가`).

**PR(정화 2종 분리 · `validateEdited(Block, before, after)` · 슬롯 규칙)은 아직
머지 전**이라, `prompts_v8.edit()`에는 슬롯 문장이 없습니다 — 지금 `develop`과
일치시키는 쪽을 골랐습니다. 머지되면:

- `prompts_v8.edit()`에 슬롯 규칙 추가
- `checks_v8.sanitize()`를 `sanitize_generated` / `sanitize_edited`로 분리
- `checks_v8.self_check()`의 "버그가 재현되는지" 단언 2개를 뒤집기

---

## 6. 결과 / 결론

*실행 전입니다.*

---

## 7. PR 머지 전에 나눠 돌리기 — 파일은 안 고칩니다

```bash
# 머지 전 — 슬롯 케이스(E1·E2·C1)를 자동으로 뺀다. 20 → 15호출
LLM_PROVIDER=bedrock RUNNER=도하 python versions/v8/run_v8.py --skip-slot-cases

# 머지 후 — 플래그만 떼면 된다
LLM_PROVIDER=bedrock RUNNER=도하 python versions/v8/run_v8.py

# 케이스를 직접 고를 수도 있다
python versions/v8/run_v8.py --cases E3,E4,C2
```

`uses_slots()` 가 baseline 에 `data-slot` 이 있는지 보고 자동으로 판별하므로,
케이스를 추가해도 목록을 손댈 필요가 없습니다.

**다만 PR 이 머지되면 §5의 미러 3곳은 손대야 합니다** — 그건 "나눠 돌리기"와
다른 문제로, 백엔드와 벤치마크를 일치시키는 작업이라 피할 수 없습니다.
