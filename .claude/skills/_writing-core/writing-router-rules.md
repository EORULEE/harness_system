# writing-router-rules.md — 짧은 글쓰기 명령 라우팅 규칙 (정본)

> `harness-writing-router`가 따르는 분류·체인·질문·live 정책의 단일 출처.
> 라우터는 **입구**일 뿐 — 대상 skill의 SKILL.md 규칙(원본 보호·draft only·면책)을 우회하지 않는다.

## 1. 분류 → skill 체인 (정본 표)
| # | 신호(키워드/alias) | document_type | skill 체인 | 비고 |
|---|---|---|---|---|
| 1 | 리뷰어 답변·reviewer response·response letter·revision response / `WR:reviewer` | response | claim-evidence-audit → writing-polish | 수정내용 없으면 질문 |
| 2 | 논문·paper·manuscript·abstract·introduction·discussion·conclusion / `WR:paper` | paper | writing-planner 또는 paper-writer | 새 citation 금지 |
| 3 | 보고서·report·성과요약·executive summary / `WR:report` | report | writing-planner 또는 report-writer | audit table 포함 |
| 4 | 특허·발명신고서·claim·청구항 / `WR:patent` | patent | writing-planner → patent-assist | 법률자문 아님·변리사 검토 |
| 5 | 발표·PPT·슬라이드·speaker notes·outline / `WR:slide` | slides | slide-writer | .pptx 비생성 |
| 6 | 다듬어줘·rewrite·polish·문체·학술적으로 / `WR:polish` | (any) | writing-polish | diff proposal·의미 불변 |
| 7 | 근거 검토·claim 검증·과장 확인·수치 확인 / `WR:audit` | (any) | claim-evidence-audit | 권고만 |
| 8 | HTML 문구·visible text | html | html-copy-polish | tag/속성 보호 |
| 9 | DOCX 양식·워드 양식·template docx / `FMT:docx` | docx | docx-template-style | 원본 복사본·계획만 |
| 10 | HWP 양식·한글 양식·표 양식 / `FMT:hwp` | hwp | hwp-template-style | 원본 복사본·계획만 |
| 11 | 최종 제출 전 확인·export review / `FMT:review` | (any) | form-export-review | PASS/FAIL 점검 |

- 신호가 **복수 매치**면: 가장 구체적인 것 우선(예: "특허 청구항 보고서" → patent). 모호하면 §3 질문.
- 매치 없음 → "어떤 유형(논문/보고서/특허/발표/HTML/HWP/DOCX/다듬기/검증)인지" 1개 질문.

## 2. mini-contract (긴 contract 대체)
라우터는 매번 full writing-contract를 요구하지 않는다. 내부적으로 최소 필드만 구성:
```
document_type: <분류 결과>
source: <사용자 제공 텍스트/파일 — 없으면 질문>
audience/purpose: <짧게 추론, 불명확하면 질문>
model_policy_ref: _writing-core/model-policy.yaml
claim_evidence_audit: <report/paper/response면 true>
```
full contract가 필요한 큰 작업(다중 섹션 논문 전체 등)만 `harness-writing-planner`로 승격.

## 3. 부족 정보 질문 규칙 (최대 3개)
- 근거자료 없으면 **새 사실 생성 금지**.
- 리뷰어 답변: 실제 수정 내용 없음 → "무엇을 수정했는지"만.
- 보고서/논문: 수치·근거 없음 → "근거자료 제공" 요청.
- 특허: 법률 판단 안 함 → "변리사 검토 필요" 명시.
- HWP/DOCX: 원본 수정 없이 "계획만".
- 질문은 **딱 부족한 것만**, 3개 초과 금지.

## 4. 자동 제안 (안전장치 보강, 우회 아님)
- report/paper/response/patent 작업 → **claim-evidence-audit 자동 제안**.
- 외부 제출·최종본 → **form-export-review 또는 final consistency check 권장**.

## 5. 확인 게이트 (바로 진행 금지 → 사용자 확인)
| 상황 | 동작 |
|---|---|
| draft/polish/audit(공개·비민감) | 바로 진행 가능 |
| 민감자료·외부 제출물 최종본 | 진행 전 확인 |
| 특허/발명신고서 | 확인 + 변리사 검토 명시 |
| HWP/DOCX 실제 양식 적용 | 확인(계획만 기본, 적용은 복사본+승인) |
| ChatGPT/codex adversarial review | 사용 전 확인 |
| API 비용 발생 작업 | 확인 |

## 6. live 모델 호출 정책
- 일반 draft/polish = `model-policy.yaml` 따름. primary writer quota 실패 시 **fallback 정책 보고**(어느 엔진 썼는지).
- 위 §5의 ①~⑥은 호출 전 확인.
- 사용자가 **"외부 모델 사용 금지"** → **Claude-only/offline**(외부 호출 0, 라우터·Claude가 직접 draft/diff).

## 7. 금지
- 라우터의 직접 파일 수정·원본 HWP/DOCX 수정. 안전장치 우회. 모델명 하드코딩. secret 출력. AI 탐지 회피. 새 claim 생성.
