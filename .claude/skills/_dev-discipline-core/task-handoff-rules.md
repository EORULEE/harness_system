# 작업 핸드오프 규율 (task-handoff)

> 출처: `vendors/obra-superpowers/upstream-subagent-driven-development.md`(격리-컨텍스트 디스패치 패턴) (MIT). 하네스 advisory.
> ⚠️ **불채택 부분**: upstream의 *"Do not pause to check in between tasks"*(연속실행·no-checkpoint)·worktree 자동생성·parallel implementer 자동실행은 **가져오지 않는다**. 패턴(격리 디스패치 + 다단 검토)만 흡수.

## 흡수한 패턴
- **격리 컨텍스트 디스패치**: 서브에이전트/codex에 **세션 히스토리 누출 없이** 필요한 산출물 컨텍스트만(요청·plan·diff·SHA) 전달.
- **다단 검토 게이트**: 구현 → spec 정합 검토([[spec-quality-review-rules]]) → 품질/적대 검토([[code-quality-review-rules]]·codex) → 통과 후 진행. 거부 시 fix-재검토.
- **TodoWrite 원장**: 작업을 TaskCreate로 추적, 양 검토 통과 후에만 완료 표기.

## 하네스 규율 (upstream과 다른 점)
- **게이트마다 하네스 흐름에 복귀** — 연속 자동 진행 없음. 사용자/stop-guard 경계 존중.
- **worktree·branch·PR 자동화 0**: 필요 시 advisory로 *제안*만, 실행은 별도 승인 일반 흐름.
- **parallel 자동 실행 0**: 병렬은 하네스 워크플로 도구를 통해 사용자 지시 하에만.
- 최종 안전권위 = stop-guard/hookify. Mode C·코인 hard-refuse 등 안전선 불가침.

## 용도
closeout·review skill이 "어떻게 일을 넘기고 검토 받는가"의 공통 참조. 독립 skill 아님(core 규율).
