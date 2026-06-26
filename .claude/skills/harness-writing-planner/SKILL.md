---
name: harness-writing-planner
description: "글쓰기 작업의 명세 계약(writing contract) 초안을 만든다. document_type(paper/report/patent/slides/html/hwp/docx)·domain_profiles·format_profile·model_policy_ref를 정해 writing-contract-schema.yaml 형식의 contract 초안을 응답으로 제시한다(파일 저장 안 함). 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<document_type 또는 글 요청>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-writing-planner — writing contract 초안 생성

글쓰기 작업을 시작하기 전, **무엇을·누구에게·어떤 양식으로** 쓸지 `writing-contract-schema.yaml`에 맞춰 **계약 초안**으로 고정한다.

## 절차 (읽기 전용)
1. `_writing-core/writing-contract-schema.yaml`을 Read → 필수 필드 확인.
2. 요청에서 추론:
   - **document_type**: `paper` · `report` · `patent` · `slides` · `html` · `hwp` · `docx` · `general` 중 선택(`_writing-core/document-type-matrix.md` 참조).
   - **domain_profiles**: `harness-domain-profile-manager` 결과(없으면 초안 제안 인용).
   - **format_profile**: 양식이 필요하면 `{family: hwp|docx|html|none, name}` 기록(`_format-profiles/` 참조). 불필요하면 `none`.
   - **model_policy_ref**: `.claude/skills/_writing-core/model-policy.yaml` (고정).
   - audience·purpose·acceptance_criteria.
3. `claim_evidence_audit: true` 기본 포함(전 workflow 연결, [[claim-evidence-rules]]).

## 출력 (draft only — 파일 저장 안 함)
- **writing contract 초안**(yaml/markdown 텍스트)을 **응답으로 제시**. 실제 Write는 별도 승인 후.
- 다음 단계 추천: document_type별 writer(`harness-paper-writer`/`harness-report-writer` 등).

## 규칙 (공통)
- 명시 호출 전용. 기존 파일 직접수정 금지. **실제 파일 저장 안 함** — contract는 응답 초안.
- 모델은 role로만 지정(`model_policy_ref`), 모델명 하드코딩 금지.
- domain profile 없으면 custom-template 기반 초안 제안만(자동 적용 금지).
- 수치·DOI·citation·저자·연도·metric·센서·데이터셋·표/그림·수식 임의 변경 금지. 새 claim 생성 금지. secret 출력 금지.
- 목적 = clarity·precision·technical integrity·reviewer readability.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
