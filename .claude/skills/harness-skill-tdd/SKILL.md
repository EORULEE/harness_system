---
name: harness-skill-tdd
description: Use when authoring or editing a harness/Writing skill — designs the pressure scenario, baseline-failure observation, and smoke test BEFORE writing the skill (RED), then minimal skill (GREEN), then counter-rationalization (REFACTOR). Holds skill creation if the without-skill failure was never observed. Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# harness-skill-tdd (Skill TDD 게이트)

새 skill을 만들기 전 **테스트-우선 규율**을 적용하는 thin wrapper. 정본 규율 = `_dev-discipline-core/skill-tdd-rules.md` · 출처 = `_dev-discipline-core/vendors/obra-superpowers/upstream-writing-skills.md`(MIT).

## 할 일
1. **RED 설계**: skill 없이 돌릴 **압박 시나리오(3+ 결합)** + 예상 baseline 실패행동 명시.
2. **GREEN 설계**: 그 실패를 겨냥할 **최소 skill** 윤곽 + frontmatter(`description: Use when…`·dmi:true·≤1024자·3인칭).
3. **REFACTOR 설계**: 나올 법한 rationalization과 counter.
4. **smoke 설계**: `tests/.../smoke.sh`(frontmatter·dmi·secret·기존 무변경).

## HOLD
skill 없이 **실패를 먼저 확인하지 않았으면 skill 생성 HOLD**(RED 미수행 = 미검증).

## 경계
명시 호출 전용·advisory·출력은 plan/checklist(Write 없음). 실제 skill 파일 작성·배포는 **별도 승인** 후. 최종권위 = stop-guard/hookify. Superpowers plugin 설치·자동 강제 금지.
