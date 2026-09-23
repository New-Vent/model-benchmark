## HTML 방식 — n=38 (전체 합계)
| Metric | 값 |
| --- | ---: |
| requirement_accuracy (요구사항 반영 정확도 — 날짜·혜택 등 명시값을 정확히 반영했는가, 안 준 값을 지어내면 감점) | 4.08 |
| content_accuracy (콘텐츠 의미 일치도 — 문구가 요구사항과 의미상 같은가(문자열 완전일치 아님)) | 4 |
| modification_accuracy (수정 반영 정확도 — 요청한 부분만 바뀌고 나머지는 그대로인가) | 4 |
| Validation Pass Rate (완전 통과율 — all_ok, 하드+소프트 0건) | 68.4% |
| Hard-Fail Pass Rate (핵심 결함 없음 비율 — hard_ok, code_fence 등 소프트는 무시) | 81.6% |
| ↳ 그중 소프트 실패만 남은 건 (code_fence/extra_text) | 5건 |
| Sanitization Violation Rate (정화(sanitize)가 출력을 손상시킨 비율) | 0.0% |
| Parse Success Rate (HTML/JSON 파싱(추출) 성공률) | 97.4% |

### 모델 4종 비교 (`versions/v8`와 같은 축)
| 모델 | n | all_ok | hard_ok | requirement_accuracy | content_accuracy | modification_accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| gemma | 8 | 87.5% | 87.5% | 4 | 3.8 | None |
| haiku | 8 | 12.5% | 75.0% | 4 | 4 | None |
| oss120 | 8 | 75.0% | 75.0% | 4.8 | 4.2 | None |
| qwen | 14 | 85.7% | 85.7% | 3.82 | 4 | 4 |

### 실패 유형 분포 (전체 38건 중, `docs/reports/v1_v1-v7/v-summary.md`와 같은 형식)
| 유형 | 건수 | 비율 | 모델 |
| --- | --- | --- | --- |
| lost_benefits | 5 | 13.2% | oss120×2, gemma×1, haiku×1, qwen×1 ⚠전모델 |
| slot_lost_period | 1 | 2.6% | qwen×1 |
| no_html | 1 | 2.6% | haiku×1 |

> ⚠전모델 — 관측된 모델 전부에서 같은 유형이 나왔다는 뜻. 모델 결함이 아니라 **케이스·채점기 쪽 결함일 가능성**을 먼저 의심할 것.

#### 소프트 실패 (§4-1 — hard_ok 판정에는 반영 안 됨)
| 유형 | 건수 | 비율 | 모델 |
| --- | --- | --- | --- |
| code_fence | 6 | 15.8% | haiku×6 |
| extra_text | 1 | 2.6% | haiku×1 |