# 증거-우선 완료 규율 (evidence-before-completion)

> 출처: `vendors/obra-superpowers/upstream-verification-before-completion.md` (MIT). 하네스 advisory.
> 원칙: **주장 전에 증거** ("evidence before assertions, always"). 단계 생략 = 검증이 아니라 거짓([[feedback-figure-read-verify]]·글로벌 §2 허위준수 금지와 결속).

## 5-step 게이트 (완료/수정/통과 주장 직전)
1. **IDENTIFY** — 그 주장을 입증할 명령이 무엇인지 결정.
2. **RUN** — 그 명령을 **fresh 실행**(캐시·가정 결과 금지).
3. **READ** — 전체 출력·exit code 정독, 실패 수 카운트.
4. **VERIFY** — 출력 ↔ 주장 대조. 음성이면 실제 상태를 증거와 함께 표기 / 양성이면 주장 + 증거 첨부.
5. **THEN CLAIM** — 그 다음에야 주장.

## 주장 유형별 필수 증거
| 주장 | 증거 |
|---|---|
| 테스트 통과 | 실패 0 보이는 테스트 출력 |
| 린트 클린 | 에러 0 린터 출력 |
| 빌드 성공 | exit 0 빌드 |
| 버그 fix | 원 증상이 테스트로 재현→통과 |
| 수용기준 충족 | 기준별 체크리스트 + 검증 |
| **그림 산출 완료** | **Read 시각검증**(빈캔버스·잘림·깨짐 0, [[feedback-figure-read-verify]]) |
| **fleet 배포 완료** | **md5/byte-identity 실측**(머신별) |
| **코드 동작/값 의미 (분석 주장)** | **생산 함수 `file:line` 원문 인용**(serena `find_symbol`). 컨테이너≠측정. 정본 code-claim-evidence-rules |

## ralph와의 관계 (보조, 충돌 없음)
- **harness-ralph** = Mode B **구조화 완료검증 루프**(수용기준=PRD, 반복 fix, circuit_breaker ≤5).
- **본 규율(closeout)** = mode 무관 **모든 완료주장**에 대한 가벼운 항상-on 5-step 게이트.
- 관계: closeout이 **상위 일반 게이트**, ralph가 **Mode B 전용 심화 루프**. closeout은 ralph를 호출하지도 대체하지도 않음 — 단발 주장엔 closeout, Mode B 구현완료엔 ralph.

## 경계
advisory. 호출 = `harness-dev-closeout`(명시). 실행 명령은 일반 도구로(게이트 하).
