---
name: harness-deep-interview
description: "실행 전 명세 게이트. 모호한 요청을 소크라테스식 질문으로 명료화하여 테스트가능한 수용기준(acceptance criteria)을 가진 명세 계약(contract)을 만든다. A1-설계/B-구현 작업 감지 시 **반자동**(내가 '딥인터뷰로 명세 잡을까요?' 1줄 확인 → 사용자 동의 시 호출). OMC가 아니라 v4.5 하네스 하위 도구. shell 실행 없음."
disable-model-invocation: false
---

# harness-deep-interview — 실행 전 명세 게이트 (v4.6)

> **이 스킬은 OMC runtime이 아니다.** oh-my-claudecode의 Deep Interview *방법론*에서 영감을 받아
> v4.5 하네스가 **처음부터 재작성한 하네스 소유 도구**다. OMC plugin/hook/MCP/setup/keyword-detector/
> persistent-mode는 일절 사용하지 않는다. (v4.6 원칙 8·11·12)
>
> **권위**: v4.5 **stop-guard·hookify가 최종 권위**다. 이 스킬은 그 아래의 종속 도구다.
> **호출(v5.6 반자동, 사용자 결정 2026-06-08)**: 설계/구현 작업 감지 시 내가 **"딥인터뷰로 명세 잡을까요?" 1줄 확인 → 동의 시 호출**. ⚠️ **확인 없는 완전 자동호출·keyword trigger·hook 발화는 여전히 금지**(반자동 강제 = 매 호출 전 사용자 게이트). user 명시 호출(`/harness-deep-interview`)도 그대로 가능.
> **shell**: 이 스킬은 **순수 질의·문서화**다. 셸 실행 스크립트를 번들하지 않는다(`disableSkillShellExecution`).

## 목적
모호한 요청을 코드 작성/실행 전에 명료화하여 **명세 계약(contract)**으로 고정한다.
이 계약의 **수용기준**은 이후 `harness-ralph`(Mode B 완료 검증 루프)의 체크리스트(PRD)가 된다.
이는 기존 **DL 검토 게이트(전처리+학습코드 승인)**를 모든 B/A1-설계 작업으로 일반화한 것이다.

## 절차 (셸 없이, 대화로 수행)

### Phase 0 — 임계값
- 모호도 임계 기본 **0.2**(20%). 더 엄격히 원하면 사용자가 지정.

### Phase 1 — 초기화
- 요청 파싱. **brownfield(기존 코드 위) vs greenfield(신규)** 판별.

### Round 0 — 토폴로지 열거
- 깊이 질문 전에 최상위 컴포넌트 구조를 먼저 고정.

### Phase 2 — 소크라테스 질문 루프 (4개 가중 명료도 차원)
| 차원 | 의미 | 가중(greenfield / brownfield) | 질문 예 |
|---|---|---|---|
| Goal | 1차 목표가 모호 없는가 | 0.40 / 0.35 | "정확히 무엇이 일어나야 하나?" |
| Constraints | 경계·비목표가 명시됐는가 | 0.30 / 0.25 | "경계·하지 말아야 할 것은?" |
| Success Criteria | 성공을 검증하는 테스트를 쓸 수 있는가 | 0.30 / 0.25 | "어떻게 작동을 확인하나?" |
| Context (brownfield) | 기존 시스템이 엔티티에 안전히 매핑되는가 | — / 0.15 | "기존과 어떻게 맞물리나?" |

- **모호도 = 1 − Σ(차원 점수 × 가중)**. 가장 약한 차원을 우선 질문. **가정(assumption) 노출** 중심(기능 나열 X).
- **온톨로지 추적**: 라운드마다 핵심 엔티티(명사) 안정도 = (stable+renamed)/total. 100% 연속 → 도메인 수렴.

### 챌린지 모드 (임계 라운드에서 관점 전환)
- Round 4+ **Contrarian**: "반대가 참이라면?"
- Round 6+ **Simplifier**: "그래도 의미 있는 가장 단순한 버전은?"
- Round 8+ **Ontologist**(모호도>0.3): "이건 본질적으로 무엇인가?"

### 종료 조건
- 자동: 모호도 ≤ 임계 / soft-warn R10 / hard-cap R20 / R3+ 사용자 조기종료(리스크 고지) / 사용자 중단(상태 저장).

### Phase 4 — 명세 계약 crystallize
산출물 = **명세 계약** (아래 §산출물). **테스트가능 수용기준은 체크박스**로.

### Phase 5 — 실행 브리지 (승인 게이트)
- 명세를 제시하고 **사용자 승인(human_proxy) 전 어떤 구현·변경·커밋도 금지**.
- 자동 실행모드 선택 금지(OMC autopilot/team/ultrawork 미도입). 승인되면 기존 하네스 흐름으로 진행.

## 산출물 (경로 정의)
- **계약**: `_output/contracts/contract-<slug>-<날짜>.md`
- **결정 영구화**: `vault/decisions/spec-<slug>.md` (검증 가치 있을 때 승격)
- ⚠️ `.omc/`에 두지 않는다(OMC 미사용). 위 두 경로만 사용.

계약 필수 항목: 메타(라운드수·최종 모호도·임계) · 명료도 표 · 토폴로지 · **Goal** · **Constraints/Non-Goals** ·
**Acceptance Criteria(테스트가능 체크박스)** · 노출·해소된 가정 표 · 온톨로지(엔티티 표) · Q&A 요약.

## 하네스 합성
- 수용기준은 **c-/x- debate**로 x-챌린지 가능(설계 약점 적대 검토).
- **multi-model-research·Mode C·A0**에는 개입하지 않는다.
- 산출 계약이 곧 `harness-ralph`의 입력(PRD). 두 스킬은 명세→검증으로 짝.
