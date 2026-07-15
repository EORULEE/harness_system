# Superpowers 적응 정책 (Dev Discipline Suite, 2026-06-16)

> obra/superpowers(MIT, commit `284be590`)의 **개발 방법론 패턴만** 하네스 v6 방식으로 흡수한다.
> Superpowers **plugin/marketplace/runtime은 설치하지 않는다.** 이 문서가 흡수 범위·경계의 정본이다.

## 권위 계층 (불변)
1. **Claude Code 하네스 = primary orchestrator** (single primary authority).
2. **stop-guard + hookify = 최종 안전권위.** 본 Dev Discipline Suite는 그 **하위 advisory**.
3. **harness-ralph = Mode B 완료검증 루프**(circuit_breaker ≤5). 본 Suite의 closeout은 ralph를 **대체하지 않고 보조**.
4. **codex exec CLI 직접(ChatGPT gpt-5.6-sol) = 교차모델 적대검토 primary** (플러그인 제거 2026-07-13). code-quality-review는 codex 경로를 **대체하지 않고 프레이밍만** 제공.
5. **harness-deep-interview = 반자동 명세 게이트.** brainstorming은 흡수 스킬화하지 않음(중복) — spec-quality-review로 *검토 부분만* 차용.

## 흡수한 패턴 (upstream → core rule)
| upstream snapshot | core rule | harness skill |
|---|---|---|
| systematic-debugging | `systematic-debugging-rules.md` | harness-systematic-debugging |
| verification-before-completion | `evidence-before-completion-rules.md` | harness-dev-closeout |
| test-driven-development | `tdd-implementation-rules.md` | harness-tdd-implementation |
| writing-skills (Skill TDD) | `skill-tdd-rules.md` | harness-skill-tdd |
| brainstorming(spec review) + subagent-driven(spec reviewer) | `spec-quality-review-rules.md` | harness-spec-quality-review |
| subagent-driven(quality reviewer) + requesting-code-review | `code-quality-review-rules.md` | harness-code-quality-review |
| subagent-driven(격리 디스패치 패턴) | `task-handoff-rules.md` | (closeout/review가 참조) |
| — | `dev-router-rules.md` | harness-dev-router |

## 하네스에 맞게 바꾼 점 (adaptation)
- **auto-invoke 제거**: upstream은 "mandatory, triggers automatically". → 본 Suite 전 skill = **`disable-model-invocation: true`(명시 호출 전용)**. 자동 강제 워크플로 **전역 적용 금지**.
- **연속실행 제거**: subagent-driven의 *"Do not pause to check in between tasks"* = **불채택**. 본 Suite는 게이트마다 사용자/하네스 흐름에 복귀(no-checkpoint 루프 없음).
- **git/PR 자동화 제거**: worktree 자동생성·branch merge·PR 자동화·parallel implementer 자동실행 = **전부 불채택**(advisory 텍스트만, 실행 0).
- **도메인 carve-out**: TDD iron law는 **code/logic에만**. DL 학습=throwaway+승인게이트([[feedback-dl-workflow]]), 문서/글쓰기/HWP·DOCX 양식/그림 생성=**TDD 제외**(Writing Suite·그림 규율 우선).
- **codex 우선**: 코드 적대검토는 **codex(ChatGPT) 교차모델**이 primary(동일모델 Claude 서브에이전트 리뷰는 보조). 비대칭 검증 우월성 유지.
- **ralph 종속**: closeout(evidence-before-completion)은 ralph의 가벼운 상위 게이트 — Mode B 구조검증은 ralph, 단발 완료주장은 closeout.

## 충돌 방지
- 기존 파일(settings.local.json·hooks·stop-guard·hookify·research-intent-hook·Writing Suite/Router·deep-interview·ralph·기존 `_dev-discipline-core` 2파일) **직접 수정 0**.
- 전 skill **dmi:true + allowed-tools Read/Grep/Glob**(Write/Edit 없음) → 출력은 plan/checklist/diff/판정. 실제 코드·파일 변경은 일반 하네스 흐름에서 **별도 승인 후**.
- stop-guard/hookify **block 강화 0**(advisory만).

## 금지 (재확인)
Superpowers plugin/marketplace 설치 · OMC/OmO/LazyCodex · 자동 mandatory workflow 전역 · worktree 자동 · PR/merge 자동 · parallel implementer 자동 · secret 원문 출력.

관련: [[reference-dev-discipline-policy]] · 기존 `dev-discipline-cheatsheet.md`·`dev-discipline-trigger-policy.md`(무수정) · 라우터 [[harness-writing-router]] 패턴.
