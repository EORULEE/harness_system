---
name: harness-paper-peer-review
persona: peer-review   # 역할 페르소나 정본 = _paper-review-core/personas.yaml (조합 = persona-composition.md)
# ⚠️ persona stance 는 doc_type=paper 전용(저널 편집위원). doc_type≠paper 면 persona-composition.md 3-b 의 doc_type→stance 규칙으로 전환(patent→patent-review 등). 축·journal 오버레이도 doc_type 조건부.
description: "타인 논문 PDF를 저널 심사자(reviewer) 관점으로 심사해 심사서(review report) 초안 작성. PDF는 PyMuPDF dpi200 렌더→비전 분석(기존 표준). rubric 8차원+저널 프로필, 모든 지적 = 근거 필수(evidence.type: 원문인용/누락위치/외부규범). draft-only — 제출은 사람. codex 적대검토 필수(미가용=HOLD). '심사서 초안/피어리뷰 해줘' 명시 요청 시."
disable-model-invocation: true
allowed-tools: [Read, Grep, Glob, Bash, Write, Task, mcp__zotero__zotero_search_items, mcp__zotero__zotero_item_metadata]
---

# harness-paper-peer-review — 저널 심사서 초안 (draft-only)

> 정본: 계약 `_output/contracts/contract-paper-review-skills-20260706.md` · rubric `_paper-review-core/review-rubric.md` · 프로필 `_paper-review-core/journal-profiles.yaml`.
> **draft-only**: 심사서 초안만 산출(`_output/reviews/<slug>/peer-review.md`) — **제출·판정 확정은 심사자 본인**.
> 모델은 model-policy role 참조만 — 모델명 하드코딩 금지.
> **페르소나 (정본 = `_paper-review-core/personas.yaml`의 `peer-review`, 조합 = `persona-composition.md`)**: 해당 저널의 **공정하되 엄격한 독립 심사자**(self-review와 달리 타인 논문·독립 평가). scope 적합성·기여도·재현성을 저널 기준으로 건설적이되 상위지 severity로 판정. **{domain}·{journal} 조합**: {domain}은 persona_seed=**주제 보정only**(⚠️ 저자와 사각지대·정설 공유해 관대해지는 collusion 금지, 독립 평가자 유지), {journal}은 journal-profiles로 심사 관점. 페르소나 수정은 personas.yaml에서.
> ⚠️ **기밀 경계(도구 스코프)**: 심사 대상 원고 = 비공개 자료. **원고 본문·결과·수치·그림은 어떤 외부 채널(MCP/업로드/공유)로도 전송 금지.** 참고문헌 실재 확인도 **기본 = 로컬만**(DOI 형식 점검·wiki 대조 — codex 지적: 미공개 원고의 참고문헌 조합 자체가 novelty를 노출 가능). **Zotero 등 외부 조회는 사용자 명시 동의 시에만**, 그때도 개별 서지 단위(조합 일괄 전송 금지). Task 서브에이전트에도 동일 경계 전파. 산출물은 로컬 `_output/reviews/`만.

## 입력
심사 대상 **PDF**(권장) 또는 **DOCX/HWP/HWPX** + 저널명(권장). 심사 의뢰 안내문(선택 — 저널 요구 관점 반영).
> 포맷별 추출: **PDF = PyMuPDF 비전**(아래 2단계) · **DOCX·HWP·HWPX = kordoc(MCP) 추출**(수식 LaTeX·병합셀 보존; 정본 `_writing-core/document-extraction.md`).


## 🆕 문서유형(doc_type) — 리뷰 일반화 (2026-07-10)
- 이 스킬은 `doc_type`(paper/report/generic/…) 을 받는다(명시>추론>generic; 미지정을 무조건 paper 로 두지 않음, paper 무회귀는 명시/추론). `doc-type-profiles/<doc_type>/profile.yaml` 로드 → rubric = 공통 코어 + 특성 evaluation_axes 오버레이(`review-rubric.md`·`persona-composition.md` 3-b). 논문 축을 타 유형에 강제하지 않는다. 새 유형=프로필 추가만. 계약 `contract-review-doctype-generalization-20260710`.

## 절차
1. **프로필 로드**: journal-profiles.yaml에서 **사용자 지정 저널 프로필**(없으면 default) — 언어·가중·verdict 어휘. ⚠️ 저널명 하드코딩 금지 — 프로필 항목만 있으면 어떤 저널도 동작(범용).
2. **PDF 분석 (기존 표준)**: **PyMuPDF 렌더 dpi≈200 → 비전 정독**(`reference_pdf_analysis_standard`). 전 페이지 — 표·그림·수식 포함. 페이지별 구조 맵.
3. **8차원 심사**: rubric 8차원 **전부** 판정(커버리지 100%, not_assessed 남용 금지). 모든 comment = **근거 필수**(evidence.type: excerpt=위치(p./§/Fig./Table)+원문 인용 ≤2줄 기본 / omission·cross_reference·external_rule 은 "증거 규칙" 대체 필드) — **근거 없는 지적 금지**.
4. **검증 배선(재사용)**: 수치 정합(초록↔본문↔표, claim-evidence-audit 패턴) · 참고문헌 spot-check(**Zotero MCP**·DOI — 미확인="미확인", **날조 단정 금지**) · wiki 대조(누락 선행연구·기존 수치와 상충).
5. **심사서 초안**: `_paper-review-core/report-templates/peer-review.md` 서식 — Summary·Recommendation(권고)·major/minor 번호 목록(저자가 항목별 응답 가능한 단위).
6. **codex 적대검토 (필수)**: codex_probe 가용 확인 → 심사서 초안의 무근거·과장·불공정 지적 검토 → 반영 → codex_review_log record(해시바인딩). **미가용 = HOLD**(`peer-review.DRAFT-HOLD.md` + "미완성" 명시).
7. 출력: 심사서 경로 + 권고(accept/minor/major/reject — **최종 결정은 사람**).

## 금지
제출/발송 · accept-reject 자동 확정 · 근거 없는 지적(evidence.type 필드 부재) · 원고 유출(외부 전송·업로드) · 모델명 리터럴 · 자동발화 · codex 스킵 후 완성 주장.
