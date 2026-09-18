# v6 — J-STRUCT · K-COUNT

v4 결론("K는 구조 변경을 못 한다, 지배적 실패는 `no_ops`")과 v5 결론("qwen
계열은 신규 생성에서 S-T·J-T가 동률")을 이어받아, "모델에게 판단·생성을
얼마나 좁혀서 시키느냐"를 검증하는 두 실험만 이 문서에 남긴다.

공통 원칙은 [docs/methodology.md](../../docs/methodology.md)

---

## J-STRUCT — 신규 생성을 "문구 없이 구조만"으로 시켜본다

**동기**: v5의 J-T(신규 페이지를 JSON plan으로 생성)를 실행해보니 qwen
계열은 S-T와 동률이었지만 exaone은 96%→4%로 붕괴했다. raw 응답을 열어보면
전부 **"내용을 지어내야 하는" 지점**에서 났다 — `placeholder`(대괄호
자리표시자 미채움), `tag_in_field_*`(텍스트에 HTML 태그 주입),
`duplicate_data_block_*`(혜택 3개를 `benefits` 블록 1개+items 3개가 아니라
`benefits` 블록을 3번 만드는 식으로 잘못 구조화).

**조치**: LLM에게 문구를 아예 안 시킨다. 스키마 자체에 `title`/`items`
같은 텍스트 필드가 없고(`additionalProperties:false`), `type`(블록 종류)과
`itemCount`(항목 개수, 2~4)만 낼 수 있다. 실제 문구는 이 구조를 보고
서버가 자동 생성한 폼에 사람이 입력한다는 게 제품 쪽 설계 방향이다(세션
논의 참고) — 이 케이스는 그 폼을 만들기 전 단계, "구조 결정" 정확도만
따로 잰다.

```
지금(J-T):   {"type":"benefits","variant":"flowbite_cards","items":["혜택1","혜택2","혜택3"]}
J-STRUCT:    {"type":"benefits","itemCount":3}
```

`STRUCT1~5`는 v5 `JT1~5`(=`ST1~5`)와 **글자 그대로 같은 요청 문구**를 쓴다
(문구를 그대로 복사해왔다 — v2 `cases_j.py`가 v1 `cases_ns.py`와 짝지을
때처럼 import 없이 `pair` 문자열만 걸었으니, 한쪽 문구를 고치면 반드시
`versions/v5/cases_jt.py`도 같이 확인할 것. `self_check()`는 `pair`가
지정됐는지만 확인하고 문구 내용까지 자동으로 대조하진 않는다).

**읽는 법**: `J-STRUCT`가 `J-T`보다 뚜렷이 높으면(특히 exaone) "J-T의
실패는 콘텐츠 생성 부담 때문이었다"가 지지된다. `duplicate_type_*`가
그래도 나오면, "개수를 필드로 표현할지 블록 반복으로 표현할지" 구조
이해 자체가 별개의 약점이라는 뜻이다.

### 1차 실행 결과 — 가설이 그대로 지지됨(4개 모델, 주호 1기기)

**최종 통과율 100%, 4개 모델 전부·5케이스 전부** — gemma3:4b(K 패치 상시
전멸)와 exaone(J-T 4%로 붕괴)까지 포함해서다. placeholder·환각·
tag_in_field·duplicate_data_block이 전부 사라졌다 — 문구를 안 시키니
지어낼 게 없어졌기 때문이다.

다만 **1차(재시도 전) 통과율은 qwen2.5:7b가 0/25**였다 — 원인은
`missing_block_hero|missing_block_cta`, 5케이스 25행 전부 정확히 같은
패턴:

```
1차:  {"blocks":[{"type":"benefits","itemCount":3},{"type":"steps","itemCount":3}]}
      ← itemCount가 없는 hero·cta를 통째로 생략
재시도(피드백 후): {"type":"hero"}·{"type":"cta"}까지 포함해서 즉시 완벽하게 고침(25/25)
```

"결정할 값이 없는 블록은 안 내도 된다"고 판단한 것으로 보인다 — gemma3:4b도
같은 패턴을 약하게 보였다(STRUCT1/2에서 cta만 누락, 2/5). **재시도로
25/25 전부 회복됐다**는 게 v4의 "재시도 되먹임은 '무엇을 고쳐라'를
구체적으로 말하면 작동한다"는 패턴과 정확히 일치한다.

**조치 완료**: 위 SYSTEM 프롬프트에 "itemCount가 없는 블록(hero·cta)도
절대 생략하지 마라"를 명시적으로 추가했다.

⚠ **이 프롬프트 변경 이후 재실행 필요** — `docs/methodology.md` §6 기준
SYSTEM 프롬프트 변경은 새 조건이다. 위 100%/0% 수치는 **프롬프트 수정
전** 결과이므로, 특히 qwen2.5:7b의 1차 통과율(0/25)은 이 CSV(`results_v6_주호_20260918_143504_708069.csv`)에서만
유효하고 그대로 최종 결론으로 쓰면 안 된다 — 최종 통과율(100%)은 수정
후에도 유지되거나 더 나아질 것으로 예상되지만(재시도가 필요 없어질
뿐), 재실행해서 확인하기 전까지는 예상일 뿐이다.

### 테스트 범위 확장 — STRUCT6~9 + J-STRUCT-V(아직 미실행)

1차 실행(STRUCT1~5)이 전부 "hero+benefits(3)+steps(3)+cta"라는 똑같은
구조라는 지적에 따라 두 방향으로 넓혔다. **둘 다 아직 실제 모델로
돌리지 않았다** — `--self-check`만 통과한 상태.

**① 선택 블록·개수 미지정(STRUCT6~9, 같은 `J-STRUCT` 군)**

| 케이스 | 요청 요지 | 겨냥하는 것 |
| --- | --- | --- |
| STRUCT6 | 혜택 2개 + **카운트다운** | 선택 블록(countdown, itemCount 없음) 인식 |
| STRUCT7 | **FAQ** 3개 + cta | 선택 블록(faq, itemCount 있음) 인식 |
| STRUCT8 | **탭** 3개 + cta | 선택 블록(tabs, itemCount 있음) 인식 |
| STRUCT9 | 혜택 목록(개수 미명시) + cta | "몇 개인지 안 나와 있을 때" — `keep_counts`에 `ANY_COUNT` 도입, 2~4 범위(스키마가 이미 강제)면 개수 불문 정답 |

STRUCT6~9는 v5 `JT1~5`에 대응하는 요청이 없어서 pair가 없다(비교용이
아니라 커버리지 확장용 신규 케이스). `SYSTEM` 프롬프트도 hero·benefits·
steps·cta 4개만 나열하던 걸 countdown·faq·tabs까지 7개 전부로 넓히고,
"개수가 요청에 안 나와 있으면 2~4 중 적절히 골라 내라"는 규칙을 추가했다.

**② variant(디자인 스타일)까지 시켜보기(`J-STRUCT-V`, 새 군)**

`STRUCTV1~5`는 `STRUCT1~5`와 **글자 그대로 같은 요청**을 쓰되(같은 파일
안이라 `self_check`가 문구 일치를 실제로 대조한다 — cases_jt.py 때와
달리 cross-file이 아니어서 게으르게 pair 문자열만 믿지 않아도 된다),
스키마에 `variant`(그 블록에 실제 등록된 이름 중 하나, enum)를 필수로
더한다. 프롬프트에는 `registry`의 `Variant.desc`를 그대로 재사용해
"이 블록엔 이런 스타일이 있다"는 설명을 붙였다 — v1 결론("안 알려주면
모델이 맞힐 수 없는 기준")을 그대로 따른 것이다.

**읽는 법**: `J-STRUCT-V`가 `J-STRUCT`(같은 요청, variant 없음)보다
뚜렷이 낮으면 "스타일 선택까지 얹으면 구조 결정 정확도가 떨어진다" —
그러면 variant는 사람이 고르거나 서버가 기본값을 주는 쪽으로 설계해야
한다는 뜻이다. 비슷하면 "variant까지 LLM에 맡겨도 안전하다"가 지지된다.

---

## K-COUNT — "삭제"라는 오퍼레이션 이름 자체를 없앤다

**동기**: K-T5·K-IDX 둘 다 KT3(항목 삭제)에서 정확히 0%였다. raw 응답을
보면 지목 방법(텍스트/인덱스)이 문제가 아니라, **`remove_item`이라는
이름의 오퍼레이션을 고르는 행위 자체**를 회피하는 것으로 보였다 —
인덱스를 참고표로 줘도 exaone은 "clarify"로, qwen2.5:7b는 스스로
`remove_item`을 옵션에 나열까지 하면서 "unsupported"를 골랐다.

**조치**: 이미 100%인 `set_field`를 그대로 쓰되, `field`를 `"itemCount"`로
고정한다. "혜택 하나 지워줘"를 `remove_item` 대신:

```json
{"op":"set_field","block_key":"benefits","field":"itemCount","value":2}
```

로 표현한다 — "삭제"·"제거" 같은 단어가 스키마에도, 모델이 골라야 할
오퍼레이션 이름에도 등장하지 않는다. 어떤 항목이 실제로 없어지는지는
이 군의 관심사가 아니다(UI가 처리한다는 게 세션 결론) — "itemCount라는
숫자를 순순히 바꾸는가"만 잰다.

⚠ **K-T5/K-IDX와 완전한 pair가 아니다.** baseline 자체가 다르다 —
K-T5/K-IDX는 실제 템플릿 콘텐츠(`cases_se.py`)를, K-COUNT는 J-STRUCT가
실제로 만들어내는 "구조만"(`{"blocks":[{"type":"hero"}, ...]}`, 문구 없음)
표현을 baseline으로 쓴다. `KCOUNT1`/`KCOUNT2`는 `KT3`/`KT4`와 요청
문구만 같고(`self_check`가 강제), baseline 성격은 다르므로 통과율을
직접 빼서 비교하지 말 것 — "오퍼레이션 이름을 바꾸면 회피 반사가
사라지는가"라는 질문에만 쓴다.

| 케이스 | 요청 | 기대 변화 |
| --- | --- | --- |
| KCOUNT1 | 혜택 마지막 하나 삭제 (=KT3와 동일 문구) | benefits 3→2 |
| KCOUNT2 | 혜택 하나 추가 (=KT4와 동일 문구) | benefits 3→4 |
| KCOUNT3 | 참여 단계 마지막 하나 삭제 | steps 3→2 |
| KCOUNT4 | 참여 단계 하나 추가 | steps 3→4 |

**읽는 법**: KCOUNT1(삭제 방향)이 KT3/KTIDX3(0%)보다 뚜렷이 높으면 —
특히 KCOUNT2(추가 방향, 이미 잘 되던 부류)와 비슷한 수준까지 올라오면
— "오퍼레이션 이름 자체가 방아쇠"라는 가설이 지지된다. 여전히 낮으면,
지목·이름 문제가 아니라 "구조를 줄이는 모든 조작"에 대한 더 근본적인
회피 성향이라는 뜻이 된다.

### 1차 실행 결과 — 가설 지지됨(4개 모델, 주호 1기기)

**최종 통과율(재시도 포함)**

| | KCOUNT1(삭제) | KCOUNT2(추가) | KCOUNT3(삭제) | KCOUNT4(추가) |
| --- | --- | --- | --- | --- |
| qwen2.5:7b | 5/5 | 5/5 | 5/5 | 5/5 |
| qwen2.5-coder:7b | 5/5 | 5/5 | 5/5 | 5/5 |
| gemma3:4b | 1/5 | 3/5 | 0/5 | 5/5 |
| exaone3.5:7.8b | 2/5 | 2/5 | 2/5 | 4/5 |

**KT3/KTIDX3(옛 remove_item 방식)는 4개 모델 전부 0/5였다. qwen 계열은
삭제 방향(KCOUNT1/3)도 100%로 완전히 뒤집혔다** — 항목 추가(KCOUNT2/4,
원래도 잘 되던 부류)와 동률이라는 게 핵심이다.

**다만 1차(재시도 전) 통과율은 qwen2.5:7b·exaone 둘 다 0/20** — raw를
보면 첫 응답은 여전히 `{"action":"unsupported",...}`로 망설인다. K-T5/
K-IDX와 결정적으로 다른 점은, 거기선 3번 재시도해도 절대 안 풀렸는데
(0/5 고정) 여기선 "이 요청은 set_field로 표현 가능합니다" 피드백
한 번이면 qwen2.5:7b는 20/20 전부 뚫린다는 것이다 — **회피 반사
자체는 완전히 없어지지 않았지만, 더 이상 고정된 벽이 아니라 재시도로
회복 가능한 장애물로 바뀌었다.** qwen2.5-coder:7b는 1차부터 20/20 —
처음부터 망설임이 없다.

**gemma3:4b는 부분 개선에 그쳤다** — KCOUNT3(단계 삭제)은 5번 다
`unsupported_rejected`로 재시도해도 안 뚫린다. v2·v4·K-T5·K-IDX에서
계속 확인된 "gemma는 K 자체를 잘 못한다"는 패턴이 완전히는 안 없어졌지만,
예전처럼 무조건 0%는 아니라는 신호는 처음 나왔다.

⚠ **실제 백엔드 구현 시 필수 조건**: qwen2.5:7b의 회복은 "재시도 루프 +
구체적인 되먹임 문구"에 의존한다. 이게 없으면 1차 응답(거부)만 남아
실사용에서는 이 결과가 재현되지 않는다.

---

## 구성

| 파일 | 내용 |
| --- | --- |
| `cases_jstruct.py` | **J-STRUCT** + **J-STRUCT-V** |
| `cases_kcount.py` | **K-COUNT** |

## 실행

```bash
export RUNNER="<본인이름>"
python base/run.py v6 J-STRUCT           # 구조 결정 실험 (STRUCT1~9)
python base/run.py v6 J-STRUCT-V         # variant까지 포함한 비교판 (STRUCTV1~5)
python base/run.py v6 K-COUNT            # "삭제" 이름 없이 itemCount만 바꾸는 실험
python base/run.py v6 --self-check       # LLM 호출 없이 검증만
python tools/summarize.py versions/v6
```
