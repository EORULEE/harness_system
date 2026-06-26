# loop-budget-policy.md — Loop 기본 예산·HOLD 정책

> r3 후보(harness-2026-06-23-r3-loop-rc). r2 불변. 각 recipe 의 `budget` 기본값과
> HOLD(중단·에스컬레이션) 조건의 SoT. **무한 반복 금지.**

## 1. 작업유형별 기본 예산

| 작업유형 | 기본 예산 | HOLD 트리거 |
|---|---|---|
| **DEV (bugfix/feature)** | 최대 **3 iteration**, **30분** | 같은 실패 **2회**면 HOLD |
| **조사 (research)** | agent **3~5개**, synthesis **최대 2회** | 출처 미달·교차반박 미수렴 |
| **글쓰기 (writing)** | **최대 2회**(draft→audit→polish) | 미확인 claim 잔존·수치/인용 변경 필요 |
| **실험 (experiment)** | 계약값, 기본 **최대 3 실험** | metric/seed/budget/stop 누락 시 **실행 금지** |
| **문서·Design** | **최대 2회** | 실제 렌더 검증 불가 시 HOLD |
| **배포 (deployment)** | **한 번에 대상 1개** | 머신/환경/절대경로 미상 시 확인질문 |
| **Knowledge Promotion** | **Codex 1회 + Claude 재검증 1회** | source audit 실패·미승인 |
| **long-compute** | loop 아님(nohup/tmux 1회 기동) | watcher 가 완료/로그만 감시 |

## 2. 공통 상한 (circuit_breaker 정합)
- DEV·검증 루프 iteration **최대 5회**(글로벌 `circuit_breaker.py max_iterations=5` 정합). 기본 권장 3회.
- 5회(또는 recipe 별 상한)에도 미수렴 → **자동 재시도 대신 사용자 에스컬레이션**.
- 시간 상한 초과 → HOLD + 부분 결과·다음 행동 보고.

## 3. 예산 초과 시 동작 (HOLD)
1. 추가 반복 **중단**(자율 재시도 안 함).
2. `verdict.json` 에 `status: HOLD` + `reason` 기록(events.jsonl append).
3. 사용자에게 1줄 보고: 어디까지 됐는지 + 왜 멈췄는지 + 가능한 선택지.
4. **예산/iteration 상한 변경이 필요하면 AskUserQuestion 재호출**(loop-permission-policy.md §재질문 2).

## 4. 비용(유료 호출) 예산
- 유료 모델/API(Codex 적대검토·유료 Gemini 등)는 **계획 승인에 포함된 횟수만** 호출.
- 계획에 없던 추가 유료 호출이 필요하면 **AskUserQuestion 재호출**(재질문 3).
- 유료 Gemini 사용 시 글로벌 규칙대로 `📊 사용량` 표기(silent 과금 금지).

## 5. 정직 기록
- 예산 미달성·생략(예: Ralph 생략)은 **ledger 에 사유 기록**. 조용한 통과 금지.
- in-sample/미검증 결과는 그대로 "미검증" 태그.
