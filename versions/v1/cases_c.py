"""
cases_c.py — C군: 누적 수정, 실제 산출물 위에서 — 스텁, 담당자 구현 필요
========================================================================
담당자만 이 파일을 건드리세요.

## 왜 이 군은 Case 하나로 표현이 안 되는가

다른 모든 군은 "고정된 입력 → 결과 → 검증"으로 끝나지만, C군은
**5단계가 서로 이어진 체인**이다 — 이전 단계의 출력이 다음 단계의
입력이 된다. engine.run_one()은 케이스 하나를 독립적으로 처리하도록
설계되어 있어서 이 체인을 표현할 수 없다.

그래서 engine.py는 Case.mode == "custom"일 때 Case.custom_run이라는
함수에 실행을 통째로 위임하는 탈출구를 제공한다. 이 파일은 그
custom_run을 구현하는 곳이다.

## 무엇을 만들어야 하는가 (planning.md §7 C군 참고)

```
묶음 A (LLM이 HTML 직접 생성)     묶음 B (서버가 조립)
  S1이 만든 HTML                   J1이 만든 plan
       ↓                              ↓
  ① 문구 수정   블록 왕복           ① 문구 수정   패치
  ② 혜택 추가   블록 왕복           ② 혜택 추가   패치
  ③ 버튼 색     블록 왕복           ③ 버튼 색     패치
  ④ 영역 추가   블록 왕복           ④ 영역 추가   패치
  ⑤ 제목 수정   블록 왕복           ⑤ 제목 수정   패치
```

**섞을 수 없다** — 묶음 A는 blocks-왕복 방식(E2/E5와 같은 방식,
cases_e.py의 블록 왕복 로직이 먼저 필요), 묶음 B는 패치(cases_k.py의
apply_patch를 그대로 재사용 가능)로 계속 이어간다.

## 구현 순서 제안

1. **cases_e.py의 블록 왕복(E2/E5)이 먼저 구현되어야 묶음 A를 만들
   수 있다.** E군 담당자와 먼저 이 부분 인터페이스를 맞출 것
   (예: `apply_block_roundtrip(current_html, block_key, new_block_html)`
   같은 순수 함수로 빼서 cases_e.py에서 export하면 여기서 import).
2. 묶음 B는 이미 다 있는 재료로 바로 만들 수 있다 —
   `checks.apply_patch`, `cases_j.SYSTEM_PLAN`(신규 생성), 여기서는
   J1의 초기 plan을 만든 뒤 K군과 같은 방식으로 5번 patch를 이어
   붙이면 된다.
3. 매 단계마다 기록할 것:
   ```
   매 단계 hard_ok
   매 단계 diff_unintended_changes         누적되며 엉뚱한 변화가 쌓이나
   입력 토큰이 단계마다 얼마나 커지나        패치의 약점이 여기 있음
   누적 출력 토큰 · 누적 시간               묶음 A 대 B
   5단계 후 최종 결과를 눈으로 확인
   ```

## custom_run 함수 시그니처 (engine.py가 호출하는 형태)

```python
def custom_run(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    '''
    engine.run_one()과 똑같은 반환 형태를 지켜야 한다: (first_hard_ok, final_ok)
    rows에는 engine._empty_row()를 사용해 CSV 스키마를 맞춰서 append할 것 —
    5단계 각각을 별도 행으로 기록한다(prompt_id를 "C_A1_step1"처럼 구분).
    '''
    ...
```

## 이 파일이 반드시 지켜야 할 규약(engine.py와의 계약)

- CASES: list[Case]  ← C군은 Case 2개(묶음A, 묶음B)만 두고, 각각
  mode="custom", custom_run=<위 함수>로 설정하면 된다.
- self_check(): 있으면 자동 호출됨.
"""

from engine import Case  # noqa: F401

STEPS = [
    "CTA 버튼 문구를 '지금 신청하기'로 바꿔줘.",
    "혜택 목록에 '친구 추천 시 5,000원 쿠폰 지급'을 추가해줘.",
    "CTA 버튼 색상을 초록색 계열로 바꿔줘.",
    "참여 방법(steps) 영역을 2단계로 추가해줘.",
    "hero 제목을 '여름엔 데이터가 두 배'로 바꿔줘.",
]


def custom_run_bundle_a(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    """TODO(C군 담당자): 묶음 A(블록 왕복 누적) 구현.
    cases_e.py의 블록 왕복 로직이 먼저 필요하다."""
    raise NotImplementedError(
        "묶음 A(블록 왕복 누적)는 cases_e.py의 E2/E5 구현 이후 채워주세요.")


def custom_run_bundle_b(model, case, runner, digest, backend, repeat_no, seed, rows, out_dir):
    """TODO(C군 담당자): 묶음 B(패치 누적) 구현.
    checks.apply_patch, cases_j.SYSTEM_PLAN을 재사용하면 된다."""
    raise NotImplementedError("묶음 B(패치 누적)를 채워주세요. 필요한 함수는 checks.py에 이미 있습니다.")


# TODO: 구현 완료 후 주석 해제
# CASES = [
#     Case("C_A", "누적수정_묶음A_블록왕복", "C", "", "", "custom",
#          custom_run=custom_run_bundle_a),
#     Case("C_B", "누적수정_묶음B_패치", "C", "", "", "custom",
#          custom_run=custom_run_bundle_b),
# ]
# 아직 CASES가 비어 있는 스텁이라 run.py가 군 이름을 못 찾는다.
# GROUPS를 선언해두면 `python base/run.py v1 C` 로 지정은 할 수 있다
# (누적 수정 — 구현되면 이 줄은 지워도 CASES에서 자동으로 뽑힌다).
GROUPS = ["C"]

CASES: list = []


def self_check():
    assert len(STEPS) == 5
    # TODO: CASES가 채워지면 아래를 채우세요.
    # assert len(CASES) == 2
