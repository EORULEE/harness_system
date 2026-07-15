---
name: harness-reviewer-response
persona: reviewer-response   # 역할 페르소나 정본 = _paper-review-core/personas.yaml (조합 = persona-composition.md)
description: "받은 심사평(텍스트/PDF)+내 원고를 분석해 point-by-point 응답문(response letter) 초안 + 수정범위(revision-scope) 제안. 코멘트 전건 응답(누락 0), 반박은 근거(원고 위치·문헌) 필수. draft-only — 원고 수정은 별도 작업. codex 적대검토 필수(미가용=HOLD). '리뷰어 대응/응답문 초안' 명시 요청 시."
disable-model-invocation: true
allowed-tools: [Read, Grep, Glob, Bash, Write, Task, mcp__zotero__zotero_search_items, mcp__zotero__zotero_item_metadata]
---

# harness-reviewer-response — 심사평 응답문 초안 (draft-only)

> 정본: 계약 `_output/contracts/contract-paper-review-skills-20260706.md` · rubric `_paper-review-core/review-rubric.md` · 프로필 `_paper-review-core/journal-profiles.yaml`.
> **draft-only**: 응답문 초안 + 수정범위 **제안**만(`_output/reviews/<slug>/response-letter.md`) — **원고 실수정·제출은 별도 작업**.
> 모델은 model-policy role 참조만 — 모델명 하드코딩 금지.

## 입력
> 📄 원고·심사평이 **DOCX·HWP·HWPX면 kordoc(MCP) 추출**(수식 LaTeX·병합셀 보존) / **PDF는 PyMuPDF 비전**. 정본 `_writing-core/document-extraction.md`.
① 심사평(**이메일 텍스트 붙여넣기 / PDF** — PDF면 PyMuPDF dpi200 비전) ② **내 원고**(md/tex/docx 소스 또는 PDF) ③ 저널명(언어 결정).


## 🆕 문서유형(doc_type) — 리뷰 일반화 (2026-07-10)
- 이 스킬은 `doc_type`(paper/report/generic/…) 을 받는다(명시>추론>generic; 미지정을 무조건 paper 로 두지 않음, paper 무회귀는 명시/추론). `doc-type-profiles/<doc_type>/profile.yaml` 로드 → rubric = 공통 코어 + 특성 evaluation_axes 오버레이(`review-rubric.md`·`persona-composition.md` 3-b). 논문 축을 타 유형에 강제하지 않는다. 새 유형=프로필 추가만. 계약 `contract-review-doctype-generalization-20260710`.

## 절차
1. **프로필 로드**: 언어(EXJ=ko·RS/GD=en)·관행.
2. **심사평 분해**: reviewer × comment 단위 표 — **누락 0 의무**(분해표 건수 = 응답 건수, 기계 대조 가능).
3. **원고 대조**: 각 코멘트의 관련 원고 위치 특정(§/p./L. — 소스 Read).
4. **응답 초안**: `_paper-review-core/report-templates/response-letter.md` 서식 — 코멘트 원문 인용 → 응답(동의/부분동의/정중한 반박) → 반영 위치.
   - **반박은 근거 필수**: 원고 위치 인용 + 필요 시 문헌(**Zotero 실재 확인** — 날조 금지, 미확인 문헌으로 반박 금지).
   - wiki(447p) 대조로 반박 근거 보강(기존 조사·모순장부 활용).
5. **수정범위 제안**: 우선순위·대상 위치·작업량 추정 표(저자 결정용 — 실수정 아님).
6. **codex 적대검토 (필수)**: codex_probe → 응답의 무근거 주장·회피성 답변·공격적 어조 지적 → 반영 → codex_review_log record(해시바인딩). **미가용 = HOLD**(`response-letter.DRAFT-HOLD.md` + "미완성" 명시).
7. 출력: 응답문 경로 + 전건 응답 확인(분해 N = 응답 N) + 수정범위 요약.

## 금지
원고 자동 수정 · 코멘트 무응답/선택적 누락 · 근거 없는 반박 · 문헌 날조 · 모델명 리터럴 · 자동발화 · codex 스킵 후 완성 주장.
