---
name: harness-domain-profile-manager
description: "Writing Suite의 도메인 프로파일을 찾고 선택한다(reference only). _domain-profiles/ 의 프로파일을 스캔해 요청 도메인에 맞는 것을 고르고, 없으면 custom-template 기반 초안을 제안한다. 여러 프로파일 조합 지원. runtime/hook 아님 — 단순 참조 레이어. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<domain_profile name 또는 도메인 키워드>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-domain-profile-manager — 도메인 프로파일 선택 (reference only)

Writing Suite가 쓸 **도메인 프로파일**을 찾고 선택한다. 프로파일은 글쓰기 페르소나·용어·인용 규범의 **참조 데이터**일 뿐, 실행 코드도 hook도 아니다.

## ⚠️ 충돌 회피 (중요)
- 본 스킬은 `scripts/domain_detector.py`·`scripts/domain_templates.py`(**프로젝트 부트스트랩용** 도메인 탐지)와 **별개**다. 그것들을 호출·수정·대체하지 않는다.
- 본 스킬 = **Writing Suite 전용 프로파일 선택 reference 레이어**. 런타임 분류기 아님.

## 입력
- 도메인 이름(예: `remote-sensing`) 또는 도메인 키워드.

## 절차 (읽기 전용)
1. `.claude/skills/_domain-profiles/` 하위 디렉터리를 **Glob/Grep으로 스캔** → 존재하는 프로파일 목록.
2. 각 `domain.yaml`을 Read → `name`·`description` 확인(로딩 규약 = `_writing-core/profile-resolution-rules.md`).
3. 요청 도메인과 매칭:
   - **있으면**: 해당 프로파일(들) 선택. **여러 프로파일 조합** 가능(예: `remote-sensing` + `hydrology`) → 우선순위·병합 방식을 제안.
   - **없으면**: `_domain-profiles/custom-template/domain.yaml`을 본보기로 **새 프로파일 초안을 응답으로 제안**(필수 키 채운 yaml 텍스트). **자동 생성/적용하지 않는다** — 사용자가 검토 후 직접 추가.
4. 선택 결과를 **plan 형태로 출력**: 선택된 profile name(들) · 누락 시 초안 · 적용 대상 document_type.
   - 선택된 domain_profiles는 contract의 `domain_profiles` 필드로 전달된다(`_writing-core/writing-contract-schema.yaml`).

## 출력 (draft/plan only)
- 선택된 domain_profiles 목록(또는 "없음 → 초안 제안").
- custom-template 기반 신규 프로파일 **초안 텍스트**(필요 시).
- 다음 단계: `harness-writing-planner`에 전달할 domain_profiles.

## 🆕 `--from-agents` 모드 — 기존 도메인 에이전트에서 프로파일 증류 (하이브리드)

> 계약: `_output/contracts/contract-domain-agent-distillation-20260709.md`.
> 목적: **페어(c-/x-)를 가진 프로젝트**에서 기존 c-도메인 에이전트의 지식(가정·용어)을 도메인 프로파일
> 초안으로 재사용한다. 빈 `custom-template` 대신 **이미 있는 에이전트 지식을 시드**로 쓴다. 범용 —
> 특정 프로젝트/도메인 하드코딩 없이 example-project-b·fusion 등 어디서나. (this-project 등 페어 없는 프로젝트는 graceful skip.)

**하이브리드 2단계:**
1. **결정적 추출** (스크립트) — `python3 <distill> --project <프로젝트 루트>`
   - `<distill>` 해석: 글로벌 설치 `~/.claude/lib/distill_domain_from_agents.py` 우선, 없으면 repo `scripts/distill_domain_from_agents.py`(this-project dev). 순수 stdlib·cwd 무관.
   - `<root>/.claude/agents/c-*.md` 스캔(x-*, *.bak 제외).
   - **선별 = `## 도메인 기본 가정` 섹션 필수**(강한 도메인 신호). 용어(terminology)만 있는 에이전트·순수
     프로세스(c-dev·c-qa·c-lead 등)는 **자동 제외**(이름 하드코딩 아님). 용어는 가정 보유 시 부가 추출.
   - 선별 에이전트의 가정·용어를 **프로젝트당 1개** raw `domain.yaml` 로 병합해 stdout 출력.
   - ⚠️ 스크립트는 `_domain-profiles/` 에 **절대 쓰지 않는다**(draft-only, 구조적 차단). `--out` 도 그 하위면 거부.
2. **산문 polish** (Claude, 이 스킬) — 스크립트가 낸 raw `persona_seed`(배경 사실 시드)를 자연어 산문으로 다듬되
   **collusion-strip 규칙 유지**(`_paper-review-core/persona-composition.md`):
   - 도메인 가정 = **배경 사실**로만("이 분야 통상 관례/가정"). **"당신은 이 분야 전문가/내부자" 정체성 문장 금지.**
   - identity/loyalty/leniency 지시 strip. 정설이라 관대 금지(리뷰 페르소나 독립성 보존).

**출력·승인**: polish된 `domain.yaml` 초안을 **plan/텍스트로 제시**. 이 reference 스킬은 **직접 Write 하지
않는다**(아래 '## 규칙 (공통)'의 "실제 Write/Edit 금지" 유지 — 기존 custom-template 초안 제안과 동일 규율).
파일화(`_domain-profiles/<name>/domain.yaml` 생성)는 **사용자 승인 후 별도 명시 단계**에서 수행한다(사용자
또는 승인된 후속 작업). 스크립트 역시 `_domain-profiles/` 미기록(draft-only).

**한계**(codex 적대검토 반영): ① **형식 의존** — 하네스 c-에이전트 관례(한/영 헤딩·표준 불릿)를 따르는
에이전트만 파싱. 미준수 에이전트는 제외되며 **제외 목록을 stderr 로 보고**(커버리지 확인). ② 도메인 값은
에이전트 내용에서만 파생(코드 도메인분기 0), smoke grep 은 회귀 가드이지 전면 증명 아님. ③ **[해소됨]**
'도메인 기본 가정' 필수화로 terminology-only 오선별 차단(codex #10, smoke T11 가드). ④ 산출 초안은 프로젝트
식별자·에이전트 파일명을 포함(traceability 목적, secret 아님 — 전송 secret 스캔은 gate 가 담당).

**검증**: `tests/smoke_domain_distill.sh`(T1~T9: 선별·범용성·리터럴가드·draft-only·collusion-strip·결정성·graceful·경계·순수추가).

## 규칙 (공통)
- 명시 호출 전용. **기존 파일 직접수정 금지**. 실제 Write/Edit 금지 — 출력은 draft/plan.
- 프로파일 부재 시 **자동 적용 금지**(초안 제안만, 사용자 승인).
- 모델 정책은 `_writing-core/model-policy.yaml` 참조(모델명 하드코딩 금지, role만).
- 수치·DOI·citation·저자·연도·metric·센서·데이터셋·표/그림 번호·수식 임의 변경 금지. 새 factual claim 생성 금지. secret 원문 출력 금지.
- 목적 = clarity·precision·technical integrity·reviewer readability.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
