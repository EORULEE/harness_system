---
name: harness-claim-evidence-audit
description: "문서에서 주장(claim)을 추출하고 각 claim에 근거를 연결한다. 수치·인용·metric·dataset·sensor term 일치 여부를 확인하고 risk level(high/medium/low)을 부여한다. 직접 수정하지 않고 수정 권고만 출력한다(audit only). 모든 writing workflow에 연결되는 공통 감사. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<감사할 문서 file_path 또는 텍스트>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-claim-evidence-audit — 주장-근거 감사 (audit only)

문서의 사실 주장과 근거를 대조해 위험을 표시한다. 규칙 정본 = `_writing-core/claim-evidence-rules.md`. **모든 writing workflow가 산출 직후 본 감사를 호출**한다(AC10).

## 참조 (_writing-core)
- 감사 연결은 contract의 `claim_evidence_audit: true`로 활성(`_writing-core/writing-contract-schema.yaml`).
- metric·dataset·sensor·인용 규범의 도메인 기준 = 선택된 **domain profile**(`_domain-profiles/<name>/` terminology·citation_norms).
- 모델 정책은 role로만 참조(`_writing-core/model-policy.yaml`).

## 절차 (읽기 전용)
> 📄 대상 문서가 **DOCX·HWP·HWPX면 kordoc(MCP) 추출**을 claim·수치·인용 정합의 기준 텍스트로(수식·병합표 보존 — 수치 대조 정확도↑). PDF=PyMuPDF 비전. 정본 `_writing-core/document-extraction.md`.
1. 대상 문서 Read + contract·domain profile(용어/인용 규범) 참조 → **claim 추출**(사실 주장·수치·인용·metric·dataset·sensor term).
2. 각 claim에 **근거 연결**: 근거유형 태깅 — `사용자제공` / `조사출처(DOI/URL)` / `계산` / `미확인`.
3. **일치 검증**: 본문 수치 ↔ 표/그림, 인용 키 ↔ 실재 출처, metric·dataset·sensor 명칭 일관성.
4. **risk level 부여**:
   - **high**: 근거 없는 사실 단정·수치 불일치·미검증 인용·과장 단정.
   - **medium**: 근거 약함·출처 모호·용어 불일치.
   - **low**: 근거 명확·일치.

## 출력 (권고 only — 직접 수정 안 함)
- claim-evidence 표: `claim | 근거유형 | 출처 | 일치여부 | risk`.
- high/medium 항목 **수정 권고**(어떻게 보완할지). **직접 Edit 금지**.
- [확인 필요]/[출처 미확보] 카운트. 0 아니면 사용자 게이트.

## 규칙 (공통)
- 명시 호출 전용. **직접 수정 금지 — 권고만**. 기존 파일 직접수정 금지.
- 수치·DOI·citation·저자·연도·metric·센서·데이터셋·표/그림·수식 임의 변경 금지(감사만). 새 claim 생성 금지.
- 모델 정책은 `model-policy.yaml` role 참조. secret 출력 금지.
- 목적 = technical integrity·precision·reviewer readability.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
