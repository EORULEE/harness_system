# verification-gate v1.1 — 근거 없는 단정 차단 게이트

어시스턴트가 **측정 없이 단정**하는 3유형을 Stop 훅에서 기계 검사합니다:
"불가/blocked" 선언 · 확정 원인 주장 · 파일/도구 부재 단정. 파괴적 명령(rm -rf 등)은 실행 전 확인(ask).

## 모드 (기본 = report: 기록만, 차단 없음)
```
mkdir -p .claude/runtime/vgate
echo report > .claude/runtime/vgate/mode.txt   # 관찰만 (기본·안전)
echo hard   > .claude/runtime/vgate/mode.txt   # 차단+재생성 강제 (충분히 관찰 후 전환 권장)
```
## 구성요소
- `scripts/vgate_orchestrator.py` — Stop 게이트 본체 (mode-aware)
- `scripts/measure.py` — 실측 helper (mount/identity/import)
- `scripts/decision_receipt.py` — "불가" 선언은 시도 기록 필수 (untried 자동 계산)
- `scripts/vgate_audit.py` — 오차단/미탐 감사 + 오판 확정 시 사용자 정정 프로토콜
- `hooks/vgate-node.sh` — node≥18 해석 런처

## 검증
`python3 tests/smoke_vgate_v11.py` → 59/59 PASS 기대.

한계(정직): 완곡한 표현 우회는 못 잡음 · 부재 검사는 "같은 턴에 조사했는가"까지(대상 일치는 미검증) ·
모든 인프라 오류는 fail-open(가용성 우선) · hard 차단의 오차단(FP)은 감사 루프로 조정하는 순환 설계.
