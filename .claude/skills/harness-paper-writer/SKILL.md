---
name: harness-paper-writer
description: "학술 논문 섹션 초안을 작성한다(draft only). title/abstract/introduction/related work/methods/results/discussion/conclusion 지원. writer·review 정책은 model-policy.yaml의 role을 참조(모델명 하드코딩 금지). claim-evidence table 출력, 과장표현 제한, limitations 보존. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<section 이름 + domain_profile + 글감>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-paper-writer — 논문 섹션 초안 (draft only)

학술 논문의 섹션 초안을 작성하기 위한 스킬. 실제 작성 엔진은 **role**로만 지정하고 정책은 `_writing-core/model-policy.yaml`이 해석한다.

## 지원 섹션
title · abstract · introduction · related work · methods · results · discussion · conclusion.

## 작성 정책 (모델명 하드코딩 금지 — role 참조)
- 초안 작성 = **primary_writer** role(`model-policy.yaml`에서 해석, 위임 경로 = `model-routing-rules.md`).
- 사실·정합 검증 = **orchestrator** role.
- 적대 검토 = **adversarial_reviewer** role(환경 불가 시 orchestrator 자기검토 + 메타 명시).
- ⚠️ 본 SKILL.md에 모델명·벤더명을 적지 않는다. 정책 변경은 `model-policy.yaml`에서.

## 절차 (읽기 전용 + 초안 산출)
1. `harness-writing-planner`의 contract(`_writing-core/writing-contract-schema.yaml` 형식, document_type=paper) + domain_profile 참조.
2. 섹션별 페르소나 시드(domain_profile `persona_seed`) → 초안 구성안.
3. 초안 + **claim-evidence table** 동반 출력([[claim-evidence-rules]]): 주장 | 근거유형 | 출처 | 상태.
4. `harness-claim-evidence-audit` 연결(전 workflow 의무).

## 문체 제약
- **significant·outperform·prove·state-of-the-art·novel** 등 과장·단정 표현은 **근거 있을 때만**. 근거 없으면 완화·삭제.
- **limitations 보존**: 한계·반례·불확실성을 지우지 않는다.
- 수치·인용·metric은 [[citation-numeric-protection]]대로 불변.

## 출력 (draft only)
- 섹션 초안 텍스트 + claim-evidence table + [확인 필요] 목록 + 메타(role·반복·적대검토 여부).
- 실제 Write/Edit 금지 — 응답 초안으로 제시.

## 규칙 (공통)
- 명시 호출 전용. 기존 파일 직접수정 금지. 모델명 하드코딩 금지. 새 factual claim 생성 금지.
- domain profile 없으면 초안 제안만(자동 적용 금지). secret 출력 금지. AI 탐지 회피 목적 금지.
- 목적 = clarity·precision·technical integrity·reviewer readability.
