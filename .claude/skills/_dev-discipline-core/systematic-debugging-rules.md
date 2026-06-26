# 체계적 디버깅 규율 (systematic-debugging)

> 출처: `vendors/obra-superpowers/upstream-systematic-debugging.md` (MIT). 하네스 advisory로 재서술.
> 철칙: **근본원인 조사 전에 fix 금지** ("NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST"). 증상 fix = 실패.

## 4단계 (순서 고정)
### Phase 1 — 근본원인 조사 (fix 시도 전)
1. **에러 메시지 정독**: stack trace·라인번호·에러코드에서 정확한 단서 추출.
2. **일관 재현**: 정확한 트리거 절차 확정. 재현 불가면 데이터 더 수집(추측 금지).
3. **최근 변경 확인**: commit·의존성·config·환경 diff.
4. **경계별 증거 수집(다중 컴포넌트)**: 각 경계 in/out 로깅으로 실패 컴포넌트 격리.
5. **데이터 흐름 역추적**: 증상→나쁜 값의 발생지점까지 거슬러.

### Phase 2 — 패턴 분석
정상 동작 코드 찾기 → 완독(skim 금지) → 정상↔고장 **모든 차이 나열** → 의존성·가정 파악.

### Phase 3 — 가설·검증
**단일 가설 명시**: "X가 근본원인, 근거 Y" → 최소 변경으로 검증 → 한 번에 한 변수 → 실패 시 새 가설(fix 쌓지 말 것).

### Phase 4 — 구현
실패 테스트/스크립트 먼저 → 근본원인만 단일 fix → 다른 것 안 깨지는지 확인 → **3+ fix 실패 시 중단, 아키텍처 의심**(circuit_breaker 에스컬레이션과 정합).

## 하네스 도메인 적용
- **Lottie 렌더 빈 캔버스**(항목100): P1 headless 재현+seek-draw 의심 → P2 정상 프레임 비교 → P3 virtual-time 레이스 단일가설 → P4 playwright 프레임대기 fix + **재Read 시각검증**([[feedback-figure-read-verify]]).
- **HWP 한컴 hang**([[feedback-hancom-interop-caution]]): 증상(taskkill 반복) 아닌 **근본(COM 서버 오염)** 차단. 1건씩·timeout 180s+.
- **serve_html cold-path timeout**: 재현 → <vpn> ping warm으로 격리 → 경로 vs 콘텐츠 切り分け.
- **DOCX/browser**: 동일 4-phase. "추측·fix 묶기·테스트 생략·미검증 가정" = red flag(재시작).

## 경계
advisory(차단 아님). 최종권위 = stop-guard/hookify. 호출 = `harness-systematic-debugging`(명시).
