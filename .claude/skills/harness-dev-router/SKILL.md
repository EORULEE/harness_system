---
name: harness-dev-router
description: Use when a message contains a short DEV: command (DEV:debug, DEV:tdd, DEV:skill, DEV:review, DEV:closeout) — interprets it and routes to the matching Dev Discipline skill. Auto-interpret (like harness-writing-router); interpret/suggest only, no Write, no bypass.
disable-model-invocation: false
allowed-tools: Read, Grep, Glob
---

# harness-dev-router (Dev Discipline 짧은 명령 라우터)

`DEV:` 짧은 명령을 적정 Dev Discipline skill로 라우팅하는 thin wrapper. 정본 = `_dev-discipline-core/dev-router-rules.md`. [[harness-writing-router]](`WR:`/`FMT:`)와 동형.

## alias
| alias | → skill |
|---|---|
| `DEV:debug` | harness-systematic-debugging |
| `DEV:tdd` | harness-tdd-implementation (code 한정) |
| `DEV:skill` | harness-skill-tdd |
| `DEV:review` | harness-spec-quality-review → harness-code-quality-review(+codex) |
| `DEV:closeout` | harness-dev-closeout |

## 해석
`DEV:<x>` 포함 → 해당 skill 명시 호출 제안. 복합은 순차. **해석·제안만**(Write 없음·우회 불가). 모호하면 1줄 확인(반자동). 자동 mandatory 강제 금지.

## 경계
명시 호출 전용·advisory. 최종권위 stop-guard/hookify.
