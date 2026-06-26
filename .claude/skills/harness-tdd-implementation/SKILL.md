---
name: harness-tdd-implementation
description: Use when implementing a code/logic feature or bugfix — enforces failing test first, then minimal implementation to green, then refactor. Does NOT apply to DL training, document/writing, or HWP/DOCX/figure generation (domain carve-outs). Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# harness-tdd-implementation (code 한정 TDD)

code/logic 변경에 **실패 테스트 → 최소 구현 → green → refactor**를 적용하는 thin wrapper. 정본 = `_dev-discipline-core/tdd-implementation-rules.md` · 출처 = `vendors/obra-superpowers/upstream-test-driven-development.md`(MIT).

## RED→GREEN→REFACTOR
- RED: 최소 실패 테스트 1개(올바른 이유로 실패 확인).
- GREEN: 통과 최소 코드만(기존 green 유지).
- REFACTOR: 중복·이름·헬퍼(green 유지, 새 동작 X).

## ⚠️ 적용 안 함 (carve-out)
- **DL 학습·데이터 탐색** → throwaway+승인게이트([[feedback-dl-workflow]]), dtype 불변.
- **문서·글쓰기·논문/보고서** → Writing Suite/Router.
- **HWP·DOCX 양식·그림(Lottie/figure)** → 그림 규율 + `harness-lottie-export-review`.

## Mode B·ralph
수용기준 검증 체크 먼저(= ralph evidence) → 구현 → ralph 완료검증. closeout([[evidence-before-completion-rules]])과 결속.

## 경계
명시 호출 전용·advisory·plan/체크리스트 출력(Write 없음). 실제 코드 변경은 별도 승인. 최종권위 stop-guard/hookify.
