# document-type-matrix.md — 문서유형 × 역할 × format 매트릭스

> 어떤 문서유형이 어떤 writer role·format-family·전용 skill에 매핑되는지의 단일 표.
> 모델명 리터럴 금지(role만).

| document_type | 주 writer role | format family | 담당 skill(Phase B) | 상태 |
|---|---|---|---|---|
| paper (논문) | primary_writer | hwp/docx | harness-paper-writer | 활성 |
| report (보고서) | primary_writer | hwp/docx/html | harness-report-writer | 활성 |
| patent (기술특허) | primary_writer | docx/hwp | harness-patent-assist | 활성(면책 필수) |
| slides (발표자료) | primary_writer | (텍스트/개요) | harness-slide-writer | 활성(.pptx 선택) |
| html | primary_writer | html | harness-html-copy-polish | 활성(visible text만) |
| hwp (양식) | structure_protection | hwp | harness-hwp-template-style | 활성(hwp-table-style 재사용) |
| docx (양식) | structure_protection | docx | harness-docx-template-style | 활성(python-docx+한컴COM) |
| general | primary_writer | none | harness-writing-planner→폴리시 | 활성 |

## 공통 파이프라인 (모든 유형)
1. `harness-writing-planner` — 요청 분석·domain/format profile 선택·writing-contract 구성.
2. `harness-domain-profile-manager` — domain-profile 로드(추가는 프로파일만, AC3).
3. **writer role 호출**(primary_writer = gemini-writer 위임).
4. `harness-claim-evidence-audit` — 주장-근거 감사(**전 workflow 연결**, AC10).
5. `harness-writing-polish` — 문체 다듬기(사실 불변).
6. (양식 필요 시) format skill — **복사본에만** 적용(AC8), 사용자 승인 후.
7. orchestrator(Claude) 최종 검증 → 전달.

## 비범위(MVP)
- slides: 산출 = 슬라이드 텍스트·개요(markdown). .pptx 바이너리 생성은 **선택·후속**(AC24).
- patent: **법률자문 아님**(AC21). 변리사 최종검토 전제.
