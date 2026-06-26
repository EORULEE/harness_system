# Dev Discipline 라우터 규율 (dev-router)

> 짧은 `DEV:` 명령을 적정 Dev Discipline skill로 라우팅. [[harness-writing-router]](`WR:`/`FMT:`) 패턴과 동형. advisory.

## alias → skill 매핑
| alias | 라우팅 대상 | 용도 |
|---|---|---|
| `DEV:debug` | `harness-systematic-debugging` | bug/test 실패/이상 동작 → 근본원인 우선 |
| `DEV:tdd` | `harness-tdd-implementation` | code 변경 → 실패테스트→최소구현→green (도메인 carve-out) |
| `DEV:skill` | `harness-skill-tdd` | 새 skill 작성 전 pressure scenario·baseline·smoke 설계 |
| `DEV:review` | `harness-spec-quality-review` + `harness-code-quality-review` | 명세 정합 → 품질(+codex 적대) |
| `DEV:closeout` | `harness-dev-closeout` | 완료주장 전 fresh evidence(5-step 게이트) |

## 해석 규칙
- 메시지에 `DEV:<x>` 포함 → 해당 skill **명시 호출**. 복합(`DEV:review`)은 spec→code 순차 제안.
- 라우터는 **해석·제안만**(Write 없음·우회 불가). 실제 코드/파일 변경은 별도 승인 일반 흐름.
- 모호하면 사용자에게 1줄 확인(반자동 정신). 자동 mandatory 강제 금지.

## 경계
advisory. 호출 = `harness-dev-router`(명시, dmi:true). 최종권위 stop-guard/hookify.
