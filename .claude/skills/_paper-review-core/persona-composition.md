# persona-composition.md — 역할×도메인×저널 조합 규칙 (문서 기반, 코드 0)

> 계약: `_output/contracts/contract-universal-personas-20260708.md`.
> **조합은 Claude가 이 규칙대로 3파일을 읽어 프롬프트를 구성한다** — 조합 스크립트(persona_resolve.py) 없음.
> 기존 journal-profiles 참조 방식과 동일한 "문서 읽어 반영" 패턴.

## 조합 공식

```
실행 페르소나 = 역할(personas.yaml/<persona-id>)
              + {domain}  ← domain-profiles/<선택>/persona_seed  (calibration only)
              + {journal} ← journal-profiles.yaml/<선택>         (scope·weights·language)
```

## 조합 절차 (스킬 실행 시)

1. **역할 로드**: 스킬 frontmatter의 `persona: <id>` → `personas.yaml`의 해당 페르소나(stance·goal·rigor·non_goals) 읽기.
2. **도메인 보정({domain})**: 사용자 지정 도메인 있으면 `domain-profiles/<도메인>/domain.yaml`의 `persona_seed`를 **주제 이해 보정으로만** 삽입.
   - ⚠️ **리뷰 페르소나(self·peer)의 precedence 규칙 (collusion 방지 메커니즘 — codex F3)**:
     1. **역할 독립성이 도메인 텍스트보다 우선**한다. persona_seed와 역할(독립 심사자)이 충돌하면 **항상 역할 승**.
     2. persona_seed는 **주제 배경 사실(background facts)로만 인용**한다 — "이 논문 주제는 {domain}, 그 분야 통상 관례·지표는 …". **"당신은 이 분야 전문가/내부자"라는 정체성 문장으로 쓰지 않는다**.
     3. persona_seed 안에 **identity(전문가 정체성)·loyalty(분야 옹호)·author-alignment(저자 편들기)·leniency(관대)** 지시가 있으면 **무시·제거(strip)**하고 background facts만 취한다.
     4. 도메인 지식은 지적의 **정확도**를 높이는 데만 쓰고, 지적의 **강도를 낮추는 데 쓰지 않는다**(정설이라 관대 금지 — "이 분야에선 흔한 관행"으로 결함을 봐주지 않는다).
   - **작성 페르소나(writer 등)**: persona_seed를 저자 정체성으로 써도 됨(기존 방식 — 리뷰와 달리 독립성 불요).
3. **저널 오버레이({journal})**: 사용자 지정 저널 있으면 `journal-profiles.yaml/<저널>`의 scope·weights·language로 severity·강조·언어 튜닝. (paper 문서유형에 한함)

3-b. **🆕 문서유형({doc_type}, 2026-07-10 리뷰 일반화)**: 리뷰 스킬은 `doc_type`(paper/report/generic/…)을 받아
   `doc-type-profiles/<doc_type>/profile.yaml`(5필드: purpose·audience·evaluation_axes·structure_conventions·success_criteria)을 로드한다.
   - **rubric = 공통 코어(원문근거·논리·명료·공정) + 프로필 evaluation_axes 오버레이**(review-rubric.md).
   - 심사 관점 = 특성 프로필의 목적·독자·성공요건에서 파생(논문 축을 타 유형에 강제 금지).
   - **doc_type 해소 순서**: ① 사용자 명시(`--doc-type`) 우선 → ② 미지정 시 **문서에서 추론**(논문 지표[초록·IMRaD·저널 투고]→paper · 보고서 지표[Executive Summary·발주처·권고]→report · 발표 지표[PPTX/슬라이드 구조·학회명 표지·발표순서/Q&A]→slide · 제안 지표[연구개발계획서/제안서 서식 표두·평가항목 장 구성·공고/RFP 언급·KPI 표]→proposal · **특허 지표**[등록/공개특허공보·청구범위/청구항·[0001] 문단번호·IPC/CPC 분류·특허권자/출원인·"United States Patent"/"What is claimed"·발명의 설명]→patent · **기술문서 계열**[아래 세부 신호]→algorithm-doc/api-reference/user-manual/protocol-spec · 불명→generic) → ③ 추론 불가/모호 → **generic**(안전: 논문 축 강제 회피, codex #10).
   - **🆕 기술문서 계열 추론(2026-07-14, ATBD 등 varied 기술문서 — 유형을 못 물어도 자동 적응)**: 다음 지배 신호로 세분한다. 정합 안 되면 이 계열의 안전 fallback = `algorithm-doc`(이론·방법 중심) 또는 `generic`.
     - **algorithm-doc**: "ATBD"·"Algorithm Theoretical Basis"·"이론 근거"·처리 단계별 수식+명령 시퀀스·검증 계보/재현성 장 → 알고리즘 이론서. (실측: SAR-L2A ATBD)
     - **api-reference**: 함수/명령 시그니처 표·파라미터·반환·`--help` 재현·CLI Reference → API 레퍼런스.
     - **user-manual**: 설치·전제조건·단계별 사용법·오류 대처·실행 예 중심 → 사용자 매뉴얼/설치가이드.
     - **protocol-spec**: 메시지/이벤트 계약(필드·타입)·상태전이·종료코드·타임아웃 → 프로토콜 명세.
     - **product-spec**: 파일 포맷·NoData·명명 규칙·XML/QC 기계판독 계약 → 제품 명세서.
     - profile.yaml **보유**(2026-07-14): algorithm-doc·product-spec·user-manual·protocol-spec·patent. **미보유**: api-reference → **algorithm-doc 또는 generic 으로 폴백**하고 리뷰 서두에 "정밀 프로파일 미보유 — 근접 유형으로 평가" 명시. (user-manual=설치가이드/CLI레퍼런스도 이 프로필.) 새 유형 profile.yaml 신설 시 즉시 정밀화(스킬 무수정).
   - ⚠️ **미지정을 무조건 paper 로 두지 않는다** — 보고서를 논문 rubric 으로 오평가 방지. **paper 무회귀** = 논문 문서는 명시/추론으로 paper 경로(8차원+journal-profiles) 그대로.
   - **프로필 누락/오류** → generic fallback. **journal-profiles 오버레이는 paper 전용** — `doc_type≠paper` 이면 위 3단계({journal})를 **건너뛴다**(비-paper 에 저널 개념 미적용).
   - 🆕 **역할 페르소나 stance도 doc_type 로 전환(2026-07-14, 축만이 아니라 검토자 관점도 유형 적합화)**: 리뷰 스킬의 기본 stance(self-review/peer-review = **저널 수석 편집위원**)는 **doc_type=paper 전용**. `doc_type≠paper` 이면 그 유형에 맞는 검토자 관점으로 stance 를 바꾼다(축만 바꾸고 '저널 편집위원' 목소리를 유지하면 범주 오류).
     - ✅ **paper 무회귀(불변 보장)**: `doc_type=paper`(명시/추론) 경로는 **이 변경 이전과 100% 동일** — self-review/peer-review 의 저널 수석 편집위원 stance + 8차원 + journal-profiles 오버레이 그대로. 본 규칙은 `doc_type≠paper` 분기만 **추가**(paper 분기 미변경). 회귀 검증 = paper fixture 산출이 이전과 동일해야 함(smoke_paper_final_check 13/13 + doc_type=paper 시 stance='저널 수석 편집위원' 유지 확인).
     - **doc_type=patent → `personas.yaml/patent-review` stance 사용**(발명자·기술책임자 = "우리 기술이 제대로 담겼나", 저널 편집위원·법적 심사자 아님). 법적 축은 '변리사 확인 요망' 플래그만. 정본 규칙 = memory `feedback_patent_inventor_role`.
     - **doc_type ∈ {algorithm-doc, product-spec, user-manual, protocol-spec} → `personas.yaml/techdoc-review` stance 사용**(기술 검증자 = 재현·감사·구현 관점, 저널 편집위원 아님). ⚠️ **주 검토자·severity = 로드된 프로필 `audience`가 결정**(예: algorithm-doc=검증/QA 엔지니어·재현, user-manual=설치·실행 사용자·작업 재현 — 같은 techdoc-review stance라도 audience가 주 렌즈를 확정). **api-reference**는 프로필 미보유 → techdoc-review stance + algorithm-doc/generic 축 폴백이되 "시그니처·반환·에러·버전 계약 정밀평가 안 됨" 서두 명시(전용 프로필 신설 = 실제 API-ref 문서 도착 시, 과적합 방지).
     - report·proposal·slide 등 나머지 비-paper = 해당 프로필 `purpose·audience`에서 검토자 관점을 도출(저널 편집위원 stance 를 그대로 쓰지 말 것 — 예: proposal=평가위원). self-review/peer-review 의 rigor(엄격·건설·독립성)·non_goals(collusion 금지)는 유지하되 '저널·투고' 프레이밍만 유형 적합화. (report/proposal 전용 persona 신설은 실사용 시.)
   - ⚠️ **추론 휴리스틱 한계(codex #10)**: IMRaD 형식 기술보고서·Executive Summary 있는 논문 등은 키워드 추론이 오분류할 수 있다 → **명시(`--doc-type`) 우선**, 모호하면 generic(안전). 추론은 best-effort 이며 정본은 사용자 명시.
   - **신호 충돌 tie-break(운영 규칙)**: 서로 다른 유형의 신호가 **복수 매칭**되면(예: IMRaD 논문에 KPI 표·발주처 보고서에 간트) 단일 신호로 단정하지 않는다 — ① **지배 문서 신호 우선**(제출처·서식 표두·저널명·학회명 등 문서의 '목적지'를 말하는 신호 > 내용 구조 신호[IMRaD·KPI·간트]) ② 지배 신호도 상충하거나 없으면 **사용자에게 확인**(상호작용형) 또는 **generic**(배치형) — 다수결·추측 금지.
4. **프롬프트 구성**: 역할 stance/goal/rigor를 기본으로, {domain}·{journal}을 위 규칙대로 채워 최종 심사/작성 관점 확정.

## Fallback (미지정 시 — 범용성 보증)

| 슬롯 | 미지정 시 |
|---|---|
| {domain} | 일반 학술(도메인 보정 없이 역할만) |
| {journal} | `journal-profiles.yaml/default`(language: follow_manuscript, weights 균등) |

→ 도메인·저널을 몰라도 역할 페르소나만으로 동작. 지정하면 자동 특화.

## 범용성 규칙 (새 분야/저널 = 추가만, 무코드)

- **새 도메인**: `domain-profiles/<new>/domain.yaml`에 persona_seed 작성 → 즉시 조합 가능(personas.yaml·스킬 무수정).
- **새 저널**: `journal-profiles.yaml`에 프로필 항목 추가 → 즉시 조합 가능.
- personas.yaml·스킬 코드에 특정 도메인/저널 리터럴 0 — 슬롯만.

## 제외 (기계적 스킬 — persona 미참조)

`claim-evidence-audit`·`multi-model-research`·`writing-planner`는 **이 조합을 적용하지 않는다**(personas.yaml `excluded_mechanical`). 이들은 중립 검증·분해·계획이라 페르소나가 편향을 넣는다. 스킬 frontmatter에 `persona:` 없음(smoke 검증).

## Golden 조합 예시 (drift 감지용 — codex F4)

> 조합이 세션마다 흔들리지 않도록 정본 예시를 고정한다. smoke가 이 블록 존재를 검증.

**예시 A — peer-review × {domain}=수문학 × {journal}=(가상)HydroJ**:
```
[역할] 공정하되 엄격한 독립 심사자(타인 논문). scope·기여·재현성을 상위지 severity로.
[도메인 background only] 이 논문 주제는 수문학이며, 통상 공간검증·불확실성 보고가 요구된다.
   ⚠️ 나는 수문학 내부자가 아니라 독립 평가자다. "이 분야 관행"으로 결함을 봐주지 않는다.
[저널 overlay] HydroJ profile의 scope(catchment-scale)·weights·language 적용.
```

**예시 B — self-review × {domain}=미지정 × {journal}=미지정(fallback)**:
```
[역할] 상위 SCIE 수석 편집위원, 내 논문을 최악의 심사자로 시뮬레이션.
[도메인] 미지정 → 일반 학술(보정 없음).
[저널] 미지정 → default(follow_manuscript, weights 균등).
```

**예시 C — doc_type=patent × {domain}=영상융합(2026-07-14, doc_type→stance 전환)**:
```
[역할] paper 의 저널 편집위원 stance 가 아니라 patent-review stance —
   발명자·기술책임자로서 "변리사 명세서에 우리 기술이 정확·완전·차별점 살아있게 담겼나".
[도메인 background only] 이 발명 분야는 영상융합(SAR/다중분광), 기술 정확성 판단에 사용.
[관할] KIPO/USPTO + 발명 유형(저널 N/A). 다관할 대응출원이면 번역 기술의미 보존 검토.
[법적축] §101/§112/청구항 형식·자명성 = '변리사 확인 요망' 플래그만(판정 안 함).
```

**예시 D — doc_type=algorithm-doc × {domain}=SAR(2026-07-14, 코드문서 계열)**:
```
[역할] 저널 편집위원 아니라 techdoc-review stance —
   검증/QA 엔지니어로서 "이 ATBD만으로 재현·감사·이관이 되는가".
[도메인 background only] SAR RTC 분야, 이론↔구현 정합 판단에 사용.
[준거표준] CEOS·NASA ATBD 템플릿 제공 시 그 기준. 저널 N/A.
[대조 본질] 문서 ↔ 실제 구현/사양/데이터. 구현 미제공이면 내적정합만+not_assessed 병기.
```

## self ≠ peer 독립성

같은 "심사자" 계열이나:
- **self-review**: 내 논문 → harsh(최악의 심사자 시뮬레이션, 방어 금지)
- **peer-review**: 타인 논문 → fair·**independent**(공정·건설적이되 독립 평가, 저자 동조 금지)
→ 서로 다른 persona id. 도메인 보정 시 둘 다 "독립 평가" 유지가 핵심.
