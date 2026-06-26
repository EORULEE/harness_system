# adaptive-verification-policy — 요청별 자동 검증 강도 (r5 adaptive)

> r4 baseline 위 forward-only. 기존 validation_mode 5종·circuit_breaker·loop_ledger 재사용. 새 엔진 없음.
> 사용자가 c-/x-·2-pass·Codex·iteration을 지정하지 않아도 자동 결정.

## 1. 매 요청 자동 판정 인자
task_type · 관련 도메인 수 · 도메인 상호의존성 · 오류 영향 · 외부제출/정책/논문/배포 여부 · 되돌릴 수 있는지 · 결정적 검증기 존재 · 근거 완전성 · 모호성 · 비용·시간.

## 2. 위험 tier
- **LOW**: 상태조회·파일읽기·용어설명·짧은 변환·저위험 단발
- **MEDIUM**: 전문 단일도메인 분석·작은 코드 수정·내부 초안·데이터 품질 검토
- **HIGH**: 복합도메인 해석·다중파일 구현·모델 성능 결론·논문 revision·정책 분석·중요 실험 비교
- **CRITICAL**: 외부 제출 최종본·특허·정책 권고·배포/삭제/push/merge·Design publish·핵심 재현성 코드·고비용 실험 채택

## 3. 자동 라우팅 (intensity → review_plan)
| 조건 | validation_mode | review_topology | pairs | passes |
|---|---|---|---|---|
| LOW+단순 | one-shot | none | 0 | 1 |
| LOW/MED+결정적검증기 | deterministic-only | none | 0 | fix≤3, 동일실패2 HOLD |
| MED+전문 단일도메인 | executor-verifier | intra-pair | 1 | min2/max2 |
| HIGH+복합도메인 | executor-verifier | cross-domain | 2(최대3) | min2/max3 |
| HIGH+외부제출·중요주장 | + cross-model(Codex 1회)+Claude 재검증 | cross-domain | 2~3 | +human gate |
| CRITICAL | human-gated | cross-domain | 최대3 | Codex 1회·승인 필수·자동 배포/공개/실험 0 |

★ 모든 요청에서 6~8 영구 pair 전체를 호출하지 않는다 — 관련 0~3개만(pair_router).

## 4. 2-pass·adaptive iteration (PHASE 5)
- PASS1 constructive/independent: 실행자+관련 pair가 같은 evidence bundle 독립검토(타 pair 결론 미리 안 봄). claim·evidence·assumption·scope·test 기록.
- PASS2 adversarial/challenge: x-agent/타 도메인 pair가 누락·반례·범위초과·근거충돌·물리/통계 가정 검토 + 결정적 결과 대조. 수용/기각 이유 기록.
- PASS3 reconciliation(선택): HIGH/CRITICAL·verdict 불일치·source 충돌·미해결 가정·사용자 요청일 때만.
- SUCCESS: 결정적 test/metric/schema PASS · 주요 verdict 수렴 · critical unresolved 0 · source contradiction 해결/명시 · 수용기준 충족.
- EARLY STOP: 2-pass 후 verdict 일치 + 상위지적 일치 + 핵심가정 충돌 없음 + 결정적 PASS.
- HOLD: 동일실패 2회 · 동일논쟁 2round · source 부족 · domain conflict · 예산초과 · 범위밖 수정 · verifier 판정불가 · 승인 필요.

## 5. 상한 (circuit_breaker.py 재사용)
cross-domain ≤3 round · Codex ≤1 · Claude 재검증 ≤1 · 전역 ≤5(circuit_breaker). 동일 실패 2회 HOLD.
이미 PASS한 항목 재실행 금지 — 실패 delta만 재시도.

## 6. 결정적 검증 우선 (PHASE 6 인자)
환경 test·metric·schema 등 결정적 검증 가능하면 에이전트 의견보다 결정적 검증 우선(loop-verifier-policy verification_priority 1).
