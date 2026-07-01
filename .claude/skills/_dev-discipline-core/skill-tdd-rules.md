# Skill TDD 규율 (skill 작성 전 테스트-우선)

> 출처: `vendors/obra-superpowers/upstream-writing-skills.md` (MIT). 하네스 advisory.
> 철칙: **실패 테스트 없이 skill 금지** ("NO SKILL WITHOUT A FAILING TEST FIRST"). 신규·편집 모두.

## RED → GREEN → REFACTOR (skill 작성)
- **RED**: skill **없이** 압박 시나리오(3+ 압박 결합)를 서브에이전트로 돌려 **baseline 실패행동을 기록**. 무엇을 자연히 잘못하는지 먼저 관찰.
- **GREEN**: 그 baseline 실패를 겨냥한 **최소 skill** 작성 → skill 있는 상태로 테스트 → 준수 확인.
- **REFACTOR**: 테스트에서 나온 **새 rationalization(빠져나갈 변명)을 명시 counter** 추가 → bulletproof까지 재테스트.

## frontmatter 규칙 (upstream 준수)
- `name`: 영문·숫자·하이픈만.
- `description`: **"Use when …"로 시작**(트리거 조건만, 워크플로 요약 금지), 3인칭, ≤1024자.
- 하네스 추가: **`disable-model-invocation: true`**(명시 호출 전용 — 본 Suite 기본), `allowed-tools` 최소.

## skill 유형별 테스트
- **discipline**: 압박 시나리오(3+ 결합) · **technique**: 적용+엣지케이스 · **pattern**: 인식+반례 · **reference**: 검색+적용.

## HOLD 규칙
**skill 없이 실패를 먼저 확인하지 않았으면 skill 생성 HOLD** — RED를 건너뛴 skill은 미검증으로 간주, 배포 보류.

## 하네스 정합
- 본 Suite·Writing Suite·LEEER skill 작성 시 이 규율을 권장(advisory). [[reference-harness-install-procedure]]의 vendored 스킬 절차와 정합.
- static smoke = `tests/superpowers-patterns/smoke.sh`(frontmatter·dmi·secret).
## 경계
advisory. 호출 = `harness-skill-tdd`(명시). 최종권위 stop-guard/hookify.
