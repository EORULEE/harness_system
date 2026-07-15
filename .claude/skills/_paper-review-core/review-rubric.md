# review-rubric.md — 리뷰 평가 기준 (공통 코어 + 문서유형 오버레이)

> paper-review 3스킬(self-review·peer-review·reviewer-response)의 기준틀.
> 저널별 가중·관행은 `journal-profiles.yaml` 오버레이(paper). 계약 = `contract-paper-review-skills-20260706.md` · 일반화 `contract-review-doctype-generalization-20260710.md`.
> **철칙: 근거 없는 지적 금지** — 모든 finding은 근거를 동반한다. 근거 형태는 `evidence.type` 로 확장(아래 "증거 규칙"): excerpt(원문 발췌)·omission(expected_location)·cross_reference·visual·external_rule(normative_basis). 무근거 지적(어느 필드도 없음)은 불가.
> **균형·공정 원칙(SCIE_Writing 병합, 2026-07-06)**: Strengths(강점)도 반드시 기술 — 막연한 비판 금지, 각 지적에 수정 제안 포함, 건설적 어조.

## 🆕 문서유형 일반화 (2026-07-10) — rubric = 공통 코어 + 특성 오버레이
> **rubric 은 문서유형 특성 프로필에서 파생된다**(심장 = `doc-type-profiles/<type>/profile.yaml`). 논문 기준을
> 타 유형에 이식하지 않는다.

**① 공통 코어 (어떤 문서든 — 항상 적용):**
- **원문 근거**: 모든 finding = 원문 위치 인용(위 철칙).
- **논리 정합**: 주장→근거 흐름 일관·내부 모순 없음.
- **명료성**: 서술 명료·용어 일관·과장/무근거 일반화 검출.
- **균형·공정**: Strengths + 각 지적에 수정 제안 + 건설적 어조.

**② 문서유형 오버레이 (`doc-type-profiles/<type>/profile.yaml` 의 `evaluation_axes`):**
- 리뷰 시작 시 `doc_type` 의 특성 프로필을 로드 → `purpose·audience·evaluation_axes·structure_conventions·success_criteria` 를 심사 관점으로 삼는다. **doc_type 해소 순서(명시→추론→generic)는 `persona-composition.md` 3-b** (미지정을 무조건 paper 로 두지 않음).
- **`doc_type=paper`(명시/추론 시, 무회귀)** = 아래 **8차원**이 곧 paper 의 evaluation_axes. journal-profiles 가중 오버레이(paper 전용). **논문 문서 리뷰 동작·산출 불변.**
- `doc_type=report`·`generic`·기타 → 각 `doc-type-profiles/<type>/profile.yaml` 의 `evaluation_axes`(축 목록은 **프로필이 유일 정본** — 본 rubric 에 유형별 축을 나열하지 않는다).
- **새 문서유형 = `doc-type-profiles/<new>/profile.yaml` 추가만**(본 rubric·스킬 무수정). 하드코딩 0.

## 증거 규칙 (finding evidence — 유형 무관 공통, T1 2026-07-10)
> 위 "철칙"을 `evidence.type` 기반으로 일반화 — 존재하는 오류 외에 **누락·불일치·시각·외부규범**도 표현. 각 finding 은 evidence.type + 유형별 필수필드를 갖는다.
- **excerpt**(원문 발췌): `document_locators` + `excerpts`(원문 ≤2줄). [기존 기본형]
- **omission**(누락): `expected_location`(있어야 할 위치) + `searched_scope`(찾은 범위). **원문 인용 면제**(없는 것은 인용 불가) — 대신 두 필드 필수.
- **cross_reference**(교차 불일치): `document_locators` ≥2 + 각 위치의 불일치 값 명시(예: 초록 91% ↔ 표3 89%).
- **visual**(시각 결함): `document_locator`(그림/차트/슬라이드 번호) + 관찰 서술(그림 자체 오류·범례·좌표·reading order).
- **external_rule**(외부 규범 위반): `normative_basis`(출처 = RFP 항목·법규 조항·프로필 규칙) + `version`/기준일. context overlay 있으면 참조, **없어도 문자열로 독립 동작**.

**문서유형별 locator**: paper/report=페이지·섹션·표·그림 / slide=슬라이드번호·개체 제목·speaker notes / patent=청구항·문단[00NN]·도면번호 / proposal=공고항목·평가항목·제안서 섹션 / web·HTML=heading·anchor·DOM selector.

## 축별 평가 상태 (axis_state — 유형 무관 공통, T1 2026-07-10)
각 evaluation_axis 판정에 상태 라벨을 붙인다:
- **pass**: 축 요건 충족.
- **issue**: 결함 존재(critical/major/minor finding 동반).
- **not_applicable**: 이 문서 유형·맥락에 축이 해당 안 됨(예: 순수 상태·기록형 보고서에서 권고 성격 축).
- **not_assessed_missing_input**: 평가에 필요한 입력이 없어 **판정 불가**(예: 선행기술 없이 신규성, 과업지시서 없이 요건 추적성, 발표조건 없이 전달력).

⚠️ **not_assessed_missing_input ≠ 낮은 점수** — 문서 결함이 아니라 리뷰 입력 부족. 낮은 점수로 처리하면 둘을 혼동한다.
- **정합(비-paper)**: 핵심 축이 not_assessed_missing_input → verdict = **not_assessable**(맨 끝 비-paper 판정 1순위) 도출.
- **정합(paper)**: paper 8차원도 not_assessed_missing_input 사용 가능(예: Data Availability 부재 → ethics_reproducibility=not_assessed). **not_assessed 도 "판정 기재"로 카운트** → 8차원 커버리지 100% 무회귀 유지.
- ⚠️ **not_assessed 남용 금지(커버리지 회피 방지)**: not_assessed_missing_input 은 **어느 입력이 없어 판정 불가인지 명시 필수**(무근거 not_assessed 불가). 문서가 완비된 경우(특히 full paper)엔 해당 축을 pass/issue 로 실판정해야 하며, 다수 축을 근거 없이 not_assessed 로 두는 것은 **커버리지 회피**로 간주한다.

## 오버레이 우선순위 (병합·적용 — T1 2026-07-10)
> ⚠️ **doc_type 해소(어느 유형인가) ≠ rubric 병합(어느 기준이 우선인가)** — 둘을 구분한다.
**(A) doc_type 해소** = `persona-composition.md` 3-b(정본): **명시(`--doc-type`) > 문서 추론 > generic fallback**(미지정≠paper).
**(B) 유형 확정 후 rubric 병합 4층**: effective rubric = 공통 코어 + 문서유형 프로필(evaluation_axes) + context/authority overlay + 명시 요구사항. 적용 우선(**높은 것이 낮은 것을 덮음**):
1. 명시된 외부 평가기준·요구사항(RFP·과업지시서·저널 Guide for Authors)
2. context/authority overlay(명시된 맥락 — authority·저널)
3. 문서유형 기본 프로필(`doc-type-profiles/<type>`)
4. 공통 코어(원문근거·논리·명료·공정 — **항상 적용**, 최하위 기본)
> **context/authority overlay = 문서유형과 직교**(paper→journal · patent→관할/절차 · proposal→RFP · slide→발표맥락). 스키마·패턴 = `context-profiles/README.md`. `journal-profiles.yaml` 이 paper 의 첫 인스턴스(하위호환 무변경). **실 비-paper overlay 파일은 T2**(실문서 도착 시 생성).

---
# (이하 ~ "판정 어휘" 섹션까지 = doc_type=paper 전용: 8차원 evaluation_axes + paper 점수·판정. 비-paper 유형은 이 paper 섹션들을 적용하지 말고 맨 끝 "비-paper 판정" 섹션을 쓴다)

## 8차원 (doc_type=paper 리뷰 산출물은 8차원 전부에 판정 기재 — 커버리지 100% 의무. 여기 "리포트"=리뷰 보고서(산출물)이지 doc_type=report 문서가 아니다)

### 1. novelty (신규성·기여)
- 기여 주장이 명시적인가? 기존 연구 대비 델타가 실재하는가?
- 과장 신호: "최초/novel" 남용, 기여-결과 불일치. 관련연구 커버리지(누락 핵심문헌 — wiki·Zotero 대조).

### 2. methodology (방법론 타당성)
- 방법이 재현 가능하게 기술됐는가(데이터·전처리·하이퍼파라미터·환경)?
- 비교 실험 설계 공정성(baseline 선정·동일 조건). 도메인 함정: spatial CV 없는 random split(공간자기상관 누수), train/test 오염, 검증낙관편향.

### 3. stats_results (통계·결과 건전성)
- 정량지표 ≥3종 비교(단일지표 결론 금지 — 조사규율과 동형). seed/반복 보고, 유의성.
- 수치 정합: 초록↔본문↔표 수치 일치(C5형 결함), % vs 절대값, 표-그림-본문 교차일치.
- IoU/F1/OA는 태스크·데이터 특이적 — 타 연구와 직접 비교 시 조건 명시 요구(C1형).

### 4. figures_tables (그림·표 품질)
- 축·단위·범례·좌표계·해상도. 캡션 자기완결성. 컬러맵 접근성.
- 원 데이터 출처 캡션(재수록 시 원 서지). 그림-본문 참조 정합(미참조 그림, 부재 그림 참조).

### 5. references (참고문헌)
- 실재성(날조/오기 — Zotero·DOI 대조 가능한 것만 확인, 못 하면 "미확인" 표기).
- 최신성·자기인용 비율·핵심 선행연구 누락. 서지 형식 = 저널 프로필.

### 6. writing_clarity (서술·명료성)
- 논리 흐름(주장→근거), 용어 일관성, 초록의 자기완결성, 문법(언어별).
- 과장 표현·무근거 일반화("보통 ~") 검출.

### 7. domain_interpretation (도메인·물리적 해석) — Editor프롬프트+zip Domain Specialist 승격(2026-07-06)
- 결과 해석이 **피상적이지 않고 메커니즘을 깊이** 다루는가(Physical Interpretation).
- 전문용어 정확성 · 연구지역/데이터 선택의 도메인 타당성 · 결과의 도메인 맥락 의미 · 실질 응용성.

### 8. ethics_reproducibility (윤리·재현성) — SCIE_Writing 병합(2026-07-06)
- Data Availability 명시 · 코드/소프트웨어 공개 여부 · 데이터 라이선스/사용 허가.
- 재현에 충분한 정보(환경·seed·버전) · 이해충돌(COI) 선언 · 연구윤리 기준.

## 실행 체크리스트 (차원별 — SCIE_Writing 흡수, finding 탐색 시 순회)
- **methodology**: □아키텍처/방법 정확 기술 □수식 수학적 정확성 □하이퍼파라미터 명시 □학습전략(lr·optimizer·epoch) □재현 정보 완비 □기존 방법과 차이 명확 □구조 선택 근거
- **stats_results**: □지표 정의 명확 □실험설계 통계 타당 □비교실험 공정 □유의성 검증 □Train/Val/Test 분할 적절(spatial CV 포함) □불확실성/오차범위 □과대해석 없음
- **novelty/references**: □핵심 선행연구 누락 없음 □최근 5년 문헌 비율 □독창성 주장의 구체 근거 □기존 연구 비교 공정 □Research Gap 논리 □인용 문맥 적합 □서지 정확
- **domain**: □물리적/환경적 해석이 **피상적이지 않고 메커니즘을 깊이** 다루는가 □해석 정확 □전문용어 올바름 □연구지역 타당 □도메인 맥락 의미 □실질 응용성
- **ethics_reproducibility**: □Data Availability □코드 공개 언급 □재현 정보 □라이선스/허가 □COI □연구윤리

## 위협모델링 체크 (2026-07-06 ChatGPT Pro 비교분석 흡수 — "쓰이지 않은 것이 결론을 무너뜨리는가")
- □ **supervised 인코딩 fold-wise**: FR·target encoding류 피처가 라벨을 쓰면, bin 경계·인코딩 값이 **각 fold의 학습 표본만으로** 재계산됐는가(전체 데이터 1회 계산 = target leakage — 검증 라벨이 입력에 유입)
- □ **pseudo-replication**: 폴리곤/사상에서 파생된 고밀도 표본의 **유효 n**(독립 관측 수)이 검정력·CI에 과대 반영되지 않았는가 — 폴리곤/이벤트 단위 분할·block bootstrap 요구
- □ **pseudo-absence 민감도**: 비발생 표본 정의(경계 buffer 제외·known-safe 대비) 민감도 분석이 있는가
- □ **명칭-구현 충실도**: 모델명이 원 알고리즘과 다른 proxy/단순화 구현이면 명칭 자체를 조정했는가("X-inspired"·"X-like")
- □ **산출물 정체성**: 불확실성/신뢰도/앙상블 지도가 **어느 모델의** 산출인지 단일하게 명시됐는가

## 점수 척도 (1-10, 차원별+종합 — **doc_type=paper 전용**, SCIE_Writing 병합)
| 점수 | 의미 |
|---|---|
| 9-10 | 출판 즉시 가능 (Accept) |
| 7-8 | 경미한 수정 후 게재 (Minor Revision) |
| 5-6 | 상당한 수정 필요 (Major Revision) |
| 3-4 | 근본적 재작성 필요 |
| 1-2 | 게재 불가 (Reject) |

## 정량 판정 기준 (**doc_type=paper 전용** 권고 도출 규칙 — 최종 결정은 사람)
- **Accept**: Critical 0 · Major 0 (Minor만)
- **Minor Revision**: Critical 0 · Major 1~2 (구조 변경 불필요)
- **Major Revision**: Critical ≥1 또는 Major ≥3 (구조 변경 필요)
- **Reject**: 수정으로 해결 불가한 근본 결함

## finding 분류 (3-tier — **유형 무관 공통**, 영향 기반. SCIE_Writing 정합)
- **critical**: 핵심 주장/결론에 영향하는 근본 결함(수식 오류·실험설계 결함·결과해석 오류·수치 모순).
- **major**: 품질을 상당히 저하(방법 설명 부족·비교실험 부재·핵심문헌 누락·재현 불가).
- **minor**: 가독성·완성도(오타·캡션 불완전·형식 불일치) — 결론엔 무영향.
- 각 finding 필수 필드: `[차원·axis_state] [critical|major|minor] [evidence.type + 유형별 필드(document_locators+발췌 / expected_location+searched_scope / normative_basis 중 해당)] [지적] [수정 제안]` — **제안 포함 의무**(막연한 비판 금지). evidence 필드 상세 = 위 "증거 규칙".

## 판정 어휘 (peer-review 권고용 — **doc_type=paper 전용**)
accept / minor revision / major revision / reject — 위 정량 기준으로 도출하되 **최종 판정은 사람**(스킬은 근거와 권고만).

## 비-paper 판정 (report·generic·기타 doc_type — accept/reject 어휘 금지)
> paper 의 "출판 즉시 가능/게재 불가" 척도를 비-paper 문서에 적용하지 않는다.
> 위 **finding 분류(critical/major/minor)는 유형 무관 공통**(영향 기반)으로 그대로 사용하되, 최종 판정 어휘는 아래 중립 어휘를 쓴다.
- **판정 어휘(중립)**: `ready`(사용 준비됨) / `ready_with_minor_edits`(경미 수정 후) / `substantive_revision_required`(실질 재작업 필요) / `not_fit_for_intended_use`(의도된 용도 부적합) / `not_assessable`(입력 부족 — 평가 불가).
- 도출(**위에서부터 먼저 적용 — 첫 매칭 채택**, 조건 중복 시 상위 우선):
  1. **not_assessable** — 핵심 축이 입력 부족(과업지시서·RFP·발표조건 등 부재)으로 **품질 평가 자체가 불가**할 때(판정 유보; 문서 결함과 구분).
  2. **not_fit_for_intended_use** — 문서의 핵심 사용 목적을 무효화하는 결함(수정 전 의도 용도 불가).
  3. **substantive_revision_required** — Critical ≥1 또는 Major ≥3.
  4. **ready_with_minor_edits** — Major 1~2 (구조 변경 불필요; paper 의 Minor Revision 과 대응).
  5. **ready** — Critical 0·Major 0 (Minor 만 있거나 무결함; paper 의 Accept 와 대응).
  **최종 판정은 사람.**
