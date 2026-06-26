# 명세 정합 검토 규율 (spec-quality-review)

> 출처: `vendors/obra-superpowers/upstream-brainstorming.md`(spec 자가검토) + `upstream-subagent-driven-development.md`(spec compliance reviewer) (MIT). 하네스 advisory.
> 목적: 구현이 **contract/plan 수용기준과 일치**하는지 검토하고 **extra-build / under-build를 표시**.

## 검토 항목
1. **수용기준 1:1 대조**: contract(`_output/contracts/`)·plan의 각 기준 → 구현 산출과 매핑. 충족/미충족/부분 표기.
2. **under-build**: 기준에 있으나 미구현 — 누락 목록.
3. **extra-build**: 기준에 없는데 구현됨(scope creep) — YAGNI 후보 표기.
4. **spec 품질**(brainstorming 차용): placeholder·모순·모호·scope 이슈 검출 → 인라인 지적.
5. **가정 명시**: 구현이 전제한 미문서화 가정.

## 출력
기준별 표(기준 | 상태 | 증거/위치 | extra/under) + 요약 판정(일치/조건부/불일치). **직접 수정 0** — 권고만.

## 하네스 정합
- **harness-deep-interview**가 만든 명세계약을 입력으로(있으면). 없으면 plan/요청을 기준으로.
- **harness-ralph**는 이 검토를 *완료검증 루프*로 강제하는 상위 — spec-quality-review는 ralph 전/외 가벼운 검토(보조).
- code면 [[code-quality-review-rules]]와 병행(스펙 정합 먼저 → 품질).

## 경계
advisory. 호출 = `harness-spec-quality-review`(명시). allowed-tools Read/Grep/Glob.
