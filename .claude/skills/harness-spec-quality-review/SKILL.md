---
name: harness-spec-quality-review
description: Use when checking whether an implementation matches its contract/plan acceptance criteria — maps each criterion to the built output and flags extra-build (scope creep) and under-build (missing). Read-only review, no edits. Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# harness-spec-quality-review (명세 정합 검토)

구현이 **contract/plan 수용기준과 일치**하는지 검토하는 thin wrapper. 정본 = `_dev-discipline-core/spec-quality-review-rules.md` · 출처 = `vendors/obra-superpowers/upstream-brainstorming.md`+`upstream-subagent-driven-development.md`(MIT).

## 검토
1. 수용기준 1:1 대조(충족/미충족/부분) · 2. **under-build**(누락) · 3. **extra-build**(scope creep·YAGNI 후보) · 4. spec 품질(placeholder·모순·모호) · 5. 미문서화 가정.

## 출력
기준별 표(기준 | 상태 | 증거/위치 | extra/under) + 판정(일치/조건부/불일치). **직접 수정 0**.

## 하네스
입력 = `harness-deep-interview` 명세계약(`_output/contracts/`, 있으면)·plan. **harness-ralph**의 완료검증 루프 전/외 가벼운 검토(보조). code면 `harness-code-quality-review` 병행.

## 경계
명시 호출 전용·advisory·읽기전용. 최종권위 stop-guard/hookify.
