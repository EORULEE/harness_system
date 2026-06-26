---
name: harness-dev-closeout
description: Use when about to claim work is complete/fixed/passing — runs the 5-step evidence gate (IDENTIFY, RUN fresh, READ output, VERIFY against claim, THEN claim). Lightweight always-on gate that complements (does not replace) harness-ralph's Mode B loop. Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash
---

# harness-dev-closeout (증거-우선 완료 게이트)

완료/수정/통과 **주장 직전** 5-step 증거 게이트를 적용하는 thin wrapper. 정본 = `_dev-discipline-core/evidence-before-completion-rules.md` · 출처 = `vendors/obra-superpowers/upstream-verification-before-completion.md`(MIT).

## 5-step
IDENTIFY(입증 명령) → RUN(fresh) → READ(출력·exit·실패수) → VERIFY(주장 대조) → THEN CLAIM(증거 첨부). **단계 생략 = 거짓**(글로벌 §2 허위준수).

## 유형별 증거
테스트=실패0 출력 · 빌드=exit0 · 버그=증상 재현→통과 · **그림=Read 시각검증**([[feedback-figure-read-verify]]) · **fleet 배포=md5 byte-identity**.

## ralph와 관계 (보조)
closeout = mode 무관 **모든 완료주장**의 가벼운 항상-on 게이트. **harness-ralph** = Mode B 구조화 완료검증 루프(circuit_breaker ≤5). closeout은 ralph를 대체·호출 안 함 — 단발 주장엔 closeout, Mode B 구현완료엔 ralph.

## 경계
명시 호출 전용·advisory. Bash는 **검증 명령 실행용**(fresh evidence). 최종권위 stop-guard/hookify.
