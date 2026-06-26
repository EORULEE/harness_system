# TDD 구현 규율 (code 변경 한정)

> 출처: `vendors/obra-superpowers/upstream-test-driven-development.md` (MIT). 하네스 advisory + **도메인 carve-out**.
> 철칙(code): **실패 테스트 없이 프로덕션 코드 금지** ("NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST").

## RED → GREEN → REFACTOR
- **RED**: 원하는 동작을 보이는 **최소 실패 테스트 1개** 작성. **올바른 이유로 실패**하는지 확인(기능 부재 — 오타·syntax 아님).
- **GREEN**: 통과시킬 **최소 코드만**. 그 테스트 통과 + 기존 테스트 전부 green 확인. 과설계 금지.
- **REFACTOR**: 중복 제거·이름 개선·헬퍼 추출(green 유지). 새 동작 추가 금지.
- **REPEAT**: 다음 실패 테스트로.
- 코드가 테스트보다 먼저 있으면 **삭제**(reference 보관 금지).

## ⚠️ 도메인 carve-out (하네스 — 적용 안 함)
- **DL 학습·데이터 탐색**: throwaway 프로토타입 허용, **TDD 미적용**. 학습 실행 전 사용자 승인·smoke만([[feedback-dl-workflow]]). 프로덕션화 단계서만 검증 강화. dtype 불변(글로벌 §10).
- **문서·글쓰기·논문/보고서**: 미적용 → **Writing Suite/Router** 우선.
- **HWP·DOCX 양식·그림(Lottie/figure) 생성**: 미적용 → 그림 규율(글로벌 §7·[[feedback-figure-read-verify]]) + `harness-lottie-export-review` 게이트.
- 즉 **code/logic 구현에만** 적용.

## Mode B·ralph와의 관계
- Mode B 구현 시: **수용기준을 검증하는 테스트/체크를 먼저**(= ralph evidence) → 최소 구현 → green → ralph 완료검증.
- "3+ fix 실패 → 아키텍처 의심" = [[systematic-debugging-rules]] Phase4 + circuit_breaker 에스컬레이션.

## 경계
advisory. 호출 = `harness-tdd-implementation`(명시). 코드 실제 변경은 별도 승인 후 일반 흐름.
