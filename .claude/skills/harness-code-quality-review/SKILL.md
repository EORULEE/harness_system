---
name: harness-code-quality-review
description: Use when reviewing changed code for simplicity, YAGNI, duplication, regression risk, and maintainability — frames findings by severity (Critical/Important/Minor). Codex (ChatGPT) cross-model adversarial review stays primary; this standardizes the framing. Read-only, no edits. Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# harness-code-quality-review (코드 품질 검토)

코드 품질을 **단순성·YAGNI·중복·회귀위험·유지보수성** 차원으로 검토하는 thin wrapper. 정본 = `_dev-discipline-core/code-quality-review-rules.md` · 출처 = `vendors/obra-superpowers/upstream-subagent-driven-development.md`+`upstream-requesting-code-review.md`(MIT).

## 차원
단순성 · YAGNI · duplication · regression risk · maintainability. 격리-컨텍스트(세션 히스토리 X, 산출물만) + **Critical/Important/Minor** severity 게이트(Critical 즉시·Important 진행 전·Minor 기록).

## codex 우선 (충돌 방지)
**코드 적대검토 primary = `/codex:adversarial-review`(ChatGPT gpt-5.5)** — 교차모델 비대칭([[feedback-codex-2pass-deploy]]). 본 skill은 codex 호출의 **차원·severity 프레이밍 표준화**(동일모델 Claude 리뷰는 보조).

## 경계
명시 호출 전용·advisory·읽기전용(권고만, 수정 0). 최종권위 stop-guard/hookify.
