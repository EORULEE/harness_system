---
name: harness-report-writer
description: "기술·과제·정책·기관 보고서 초안을 작성한다(draft only). executive summary/background/data/method/results/implications/limitations/future work 지원. 의사결정자용 요약과 기술 세부를 분리. HWP/DOCX export용 문단 구조는 고려하되 양식 적용은 하지 않는다. writer 정책은 model-policy.yaml role 참조. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<report 유형 + domain_profile + 자료>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-report-writer — 보고서 초안 (draft only)

기술보고서·과제보고서·정책보고서·기관보고서의 초안 작성.

## 지원 구조
executive summary · background · data · method · results · implications · limitations · future work.

## 핵심 원칙
- **의사결정자용 요약 ↔ 기술 세부 분리**: executive summary는 비전문가도 읽히게, 기술 세부는 별도 섹션.
- **양식 적용 안 함**: HWP/DOCX export를 염두에 둔 **문단/표 구조**는 고려하되, 실제 양식 적용은 본 스킬이 하지 않는다(format skill = Phase B2, 원본 복사본만 [[hwp-docx-format-rules]]).

## 작성 정책 (role 참조)
- 초안 = **primary_writer**, 검증 = **orchestrator**, 적대검토 = **adversarial_reviewer** (전부 `model-policy.yaml` 해석). 모델명 하드코딩 금지.

## 절차
1. contract(`_writing-core/writing-contract-schema.yaml` 형식, document_type=report) + domain_profile 참조.
2. 구조별 초안 구성 → claim-evidence table 동반([[claim-evidence-rules]]).
3. limitations·future work 보존(낙관 편향 금지).

## 출력 (draft only)
- 보고서 초안(섹션별) + 의사결정 요약 + claim-evidence table + [확인 필요] 목록.
- 실제 Write/Edit·양식 적용 금지 — 응답 초안.

## 규칙 (공통)
- 명시 호출 전용. 기존 파일 직접수정 금지. 모델명 하드코딩 금지. 새 claim 생성 금지.
- 수치·인용·metric·센서·데이터셋 임의 변경 금지. domain profile 없으면 초안 제안만. secret 출력 금지.
- 목적 = clarity·precision·technical integrity·reviewer readability.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
