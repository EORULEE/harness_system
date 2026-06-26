---
name: harness-ralph
description: "Mode B 구현 완료 검증 루프. harness-deep-interview 명세 계약의 테스트가능 수용기준을 PRD로 삼아, 기준별로 fresh evidence(test·build·lint·typecheck)로 검증→실패 시 fix→재검증을 반복한다. 반자동(사용자가 '랄프모드로/완료 검증해줘' 등 명시 요청 시 1줄 확인 후 호출; 확인 없는 완전 자동호출 금지). circuit_breaker ≤5회 종속, 미수렴 시 사용자 에스컬레이션. OMC가 아니라 v4.5 하네스 하위 도구. shell 자율실행 없음."
disable-model-invocation: false
---

# harness-ralph — Mode B 구현완료 검증 루프 (v4.6)

> **이 스킬은 OMC runtime이 아니다.** oh-my-claudecode Ralph의 *PRD 완료 검증 절차*에서 영감을 받아
> v4.5 하네스가 **재작성한 하네스 소유 도구**다. **OMC persistent-mode(Stop hook)·keyword trigger·
> PermissionRequest hook·autopilot/team/ultrawork는 일절 사용하지 않는다.** (v4.6 원칙 11·12)
>
> **권위**: v4.5 **stop-guard·hookify가 최종 권위**. 이 루프는 그 아래의 종속 도구다.
> **호출**: **반자동 (v6, 2026-06-10 사용자 결정)**. 사용자가 "랄프모드로/완료 검증해줘" 등 **명시 요청** 시 Claude가 "랄프로 완료 검증 시작할까요?" **1줄 확인 → 동의 시 호출**. ⚠️ **확인 없는 완전 자동호출·`ralph:` 접두 keyword trigger·Stop 지속루프는 여전히 금지**(반자동 강제 = 매 호출 전 사용자 게이트).
> **shell**: 이 스킬은 **검증 절차 문서**다. 자율 실행 runtime을 번들하지 않는다. 검증 명령은
> **Claude가 일반 Bash 도구로**(hookify·stop-guard·권한 게이트 하에서, 가시적으로) 실행한다.

## 목적
"구현 완료"라는 주장을 **명세 계약의 수용기준으로 실제 검증**한다. Ralph의 "끈질긴 검증" 정신만
가져오되, "안 멈추는 자율"은 **circuit_breaker 상한 + 반자동 확인 게이트 + stop-guard 최종권위**로 대체한다.

## 입력
- `harness-deep-interview`가 만든 **명세 계약**(`_output/contracts/contract-<slug>-*.md`)의
  **Acceptance Criteria = PRD**. (별도 `prd.json`으로 추출해도 됨.)
- generic 기준("구현 완료") 금지 — **구체·task별 검증가능 기준**만(예: "함수 X에 Z 입력 시 Y 반환").

## 검증 루프 (기준별, 증거 기반)
1. PRD의 각 수용기준(체크박스)에 대해:
   - 관련 검증 명령 실행(test·build·lint·typecheck 등) — **Claude가 Bash 도구로, 게이트 하에**.
   - **출력을 직접 읽어** 해당 기준 충족 여부 판정(추정 금지, fresh evidence).
   - 하나라도 실패 → 미완료. **fix → 재검증**.
2. 모든 기준 통과 시에만 story/계약을 `pass`로 표시.
3. (선택) **c-/x- debate 또는 verify 스킬**로 리뷰어 교차검증(별도 OMC reviewer 미사용).
4. cleanup 편집 후 **regression 재검증**.

## 경계 (불가침 — v4.5 권위)
- **상한**: `scripts/circuit_breaker.py`의 **max_iterations=5**. 5회에도 미수렴 → **사용자 에스컬레이션**(무한루프 금지).
- **게이트 우회 금지**: DL 본학습 검토게이트, git 커밋/푸시, Mode C 코인 hard-refuse, hookify block(예: `--no-verify`, train 로그)를 **넘지 못한다**.
- **앰비언트 금지**: 1회 명시 호출로 시작하는 **유한 루프**. Stop hook으로 세션을 끌고 가지 않는다.
- **권한**: 위험 명령은 사용자 권한·hookify 판정에 따른다. 자동 승인 안 함.

## 산출물 (경로 정의)
- **검증 로그**: `_output/ralph/ralph-<slug>-<날짜>.md` (라운드별 기준·증거·판정·fix)
- **결정 영구화**: `vault/decisions/` (검증 결과 중 보존 가치 있는 것 승격)
- ⚠️ `.omc/`에 두지 않는다.

## 🔗 로그 마커 규약 (stop-guard 경계검사 결합 — 필수)
검증 로그는 **`hooks/stop.mjs`의 `checkRalphBoundary()`가 파싱**한다. 아래 마커를 **정확히** 써야
상한 강제(circuit_breaker ≤5)가 동작한다. (마커 불일치 시 경계검사가 무효화됨.)

| 마커 | 형식(정확) | stop.mjs 정규식 | 용도 |
|---|---|---|---|
| **iteration 헤더** | `## Iteration <N>` (또는 `Round`/`반복` + 숫자, `#`~`####`) | `^#{1,4}\s*(?:Iteration\|Round\|반복)\s+(\d+)` | 현재 반복 횟수(maxIter) |
| **에스컬레이션** | 본문에 `ESCALATED` (또는 `에스컬레이션`) 포함 | `ESCALAT\|에스컬레이션` | 5회 초과 시 사용자에게 넘김 → 차단 해제 |
| **완료** | `모든 기준 통과` (또는 `COMPLETE`/`PASS_ALL`/`all criteria pass`) | `COMPLETE\|모든 기준 통과\|all\s+criteria\s+pass\|PASS_ALL` | 모든 수용기준 통과 → 차단 해제 |

**규칙**:
- 각 검증 반복은 **반드시 `## Iteration N` 헤더로 시작**(N=1,2,…).
- **6회차에 도달했는데 미수렴**이면 더 진행하지 말고 로그에 **`ESCALATED`** 한 줄 기록 + 사용자에게 판단 요청(무한루프 금지). → stop-guard 차단 해제.
- 모든 기준 통과 시 로그 말미에 **`모든 기준 통과`** 명시. → 완료, 차단 해제.
- 로그 파일명은 `_` 로 시작하지 않는다(테스트·임시 파일과 구분). 6h 이상 묵은 로그는 stale로 무시됨.

> 예시:
> ```
> # Ralph 검증 — <slug>
> ## Iteration 1
> - AC1: build … FAIL → fix
> ## Iteration 2
> - AC1: build OK · AC2: test … FAIL → fix
> …
> ## Iteration 6
> - AC4 미수렴 → ESCALATED (사용자 판단 요청)
> ```

## 적용 범위
- **Mode B(구현)의 완료 검증에만**. A1 조사·multi-model-research·c-/x- debate(조사용)·Mode C 실험루프를 **대체하지 않는다**(v4.6 원칙 5).
- primary loop authority는 하네스 1개. harness-ralph는 B가 빌려 쓰는 **종속 루프**, 완료·에스컬레이션 시 권한 반납.
