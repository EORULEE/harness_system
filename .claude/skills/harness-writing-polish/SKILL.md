---
name: harness-writing-polish
description: "최종 문장 polish. 과장 표현·vague attribution·generic conclusion·불필요한 AI식 표현을 완화한다. 의미·수치·인용·metric은 변경하지 않는다. 변경 전후 diff proposal 형태로만 출력(직접 수정 안 함). AI 탐지 회피 목적 금지. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<polish할 문서 file_path 또는 텍스트>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-writing-polish — 문장 polish (diff proposal only)

완성 문서의 **문체만** 다듬는다. 사실·수치·인용은 불변.

## ⛔ 목적 경계
- 목적 = **clarity·precision·technical integrity·reviewer readability**.
- **AI 탐지 회피(anti-detection) 목적 금지.** "사람처럼 보이게" 위장하려는 변형 금지.

## 완화 대상 (문체)
- 과장 표현(unfounded superlatives), vague attribution("일부 연구에 따르면" 출처 없음),
  generic conclusion(내용 없는 맺음), 불필요한 AI식 상투구(redundant hedging·boilerplate).

## ⛔ 불변식 (변경 금지)
- 의미·논지, 수치, 인용 키·저자·연도·DOI, metric·dataset·sensor 명칭, 표/그림 번호, 수식.
- [[citation-numeric-protection]]: polish 전후 인용·수치 **diff 0**.

## 참조 (_writing-core)
- 재작성이 필요하면 엔진은 **role**로만 지정(`_writing-core/model-policy.yaml`, 모델명 하드코딩 금지).
- 톤·독자 기준 = contract의 audience/purpose(`_writing-core/writing-contract-schema.yaml`).
- 도메인 용어 보존 기준 = 선택된 **domain profile**(`_domain-profiles/<name>/`, terminology 불변).

## 절차 (읽기 전용 + 제안)
1. 대상 문서 Read + contract(audience/document_type)·domain profile(terminology) 참조.
2. 문장 단위로 완화 후보 식별 → **변경 전/후 쌍** 작성.
3. 각 변경이 불변식·도메인 용어를 안 건드리는지 self-check.

## 출력 (diff proposal only — 직접 수정 안 함)
- **diff proposal** 표: `원문 → 제안 | 사유(어떤 문체 문제)`.
- 불변식 보존 확인 1줄(수치·인용·metric diff 0).
- 실제 Edit/Write 금지 — 사용자가 검토 후 적용.

## 규칙 (공통)
- 명시 호출 전용. 기존 파일 직접수정 금지. 새 claim 생성 금지. 모델명 하드코딩 금지(role 참조).
- secret 출력 금지. AI 탐지 회피 금지.
