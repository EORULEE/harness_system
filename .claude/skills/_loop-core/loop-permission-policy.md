# loop-permission-policy.md — 승인 게이트·재질문 정책

> r3 후보(harness-2026-06-23-r3-loop-rc). r2 불변. 실행 전 AskUserQuestion 승인 게이트와
> 실행 중 재질문 조건의 SoT. **주 orchestrator(harness-loop-engineering)만 질문·승인을 담당.**

## 1. 실행 전 계획 게이트 (필수)
Loop 가 필요한 자연어 요청을 감지하면 **바로 실행하지 말고**, 먼저 다음 **계획 요약**을 짧게 보여준다:

1. 판단한 작업 유형
2. 선택한 recipe 와 executor
3. 진행 단계
4. 검증 방식과 교차검증 여부
5. 최대 iteration·시간·비용
6. 수정 가능한 파일 범위
7. 사용자 승인이 필요한 위험 작업
8. 성공 조건과 HOLD 조건

그다음 **AskUserQuestion** 으로 4 선택지를 제시한다:

| 선택지 | 의미 |
|---|---|
| **계획대로 실행** | 제시한 범위·예산으로 Loop 실행 |
| **계획만 저장** | contract 와 계획만 만들고 실행하지 않음 |
| **계획 수정** | 범위·검증·예산을 다시 조정 |
| **취소** | 아무 작업도 수행하지 않음 |

## 2. 승인 전 금지 (하드)
사용자가 **"계획대로 실행"** 을 선택하기 전에는 **Write·Edit·Bash 실행·외부 모델 호출·실험·배포를
시작하지 않는다.** (읽기 전용 탐색으로 계획을 정밀화하는 것은 허용.)
- 사용자가 **일반 텍스트로 명확히 승인**했다고 말한 경우에도 승인으로 인정한다.
- 작은 저위험 작업도 사용자가 **"자동으로 처리해줘"** 라고 했으면 **계획 요약 후 한 번만** 승인받는다.
- **"계획만 저장" 예외**: 이 선택은 **계약/계획 파일**(`_claude/loops/<loop_id>/contract.yaml` + 계획)만 Write 하도록
  인가한다(실행 단계 미수행). 그 외 작업 산출 Write/Edit/Bash·외부모델·실험·배포는 여전히 금지.
- **강제 메커니즘(정직)**: 이 게이트는 **하드 PreToolUse 차단이 아니라** 모델 규율 + AskUserQuestion +
  **stop-guard 최종권위**로 강제된다(loop-intent-hook 은 advisory, hard block 0). 사용자 명세 "hard block 금지"에 따른
  설계 — 즉 도구를 물리적으로 막는 훅이 아니라, 규율 위반 시 stop-guard 가 잡는 구조다.

## 3. 게이트를 띄우지 않는 경우 (즉시 처리)
- **단순 질문·상태조회·파일 읽기·짧은 문장 수정** → AskUserQuestion 없이 바로 처리.
- 상태 조회·개념 질문은 **계약 생성조차 하지 않는다**.

## 4. iteration 마다 다시 묻지 않는다
승인 1회로 계획 범위 내 전체 loop 를 진행한다. **다음 5가지에만** 실행 중 다시 AskUserQuestion:

1. **허용 범위(editable_paths) 밖 파일 수정** 필요
2. **예산 또는 iteration 상한 변경** 필요
3. **유료 모델/API 호출** 필요(계획에 없던)
4. **실험·배포·삭제·push·merge·외부 업로드** 필요
5. **기존 계획과 다른 전략으로 전환** 필요

## 5. 질문 위치 (하드)
- **백그라운드 agent·verifier 내부에서는 AskUserQuestion 을 호출하지 않는다.**
- 질문과 승인은 **주 orchestrator 만** 담당. verifier 는 발견을 orchestrator 에 반환만.

## 6. human-gated 위험작업 목록 (승인 필수)
배포 · 삭제 · push/merge · 외부 업로드(Drive/Design publish 등) · 비용 발생 호출(유료 모델/API) ·
Mode C 실제 실행 · Design sync · Wiki 정본 승격 · r2 release 변경(금지).

## 7. 금지
- 사용자 승인 없는 삭제·배포·외부 업로드·push·merge.
- Mode C 자동 활성화. 유료 모델 자동 호출. r2 release 덮어쓰기. 다른 서버·프로젝트 자동 배포.
