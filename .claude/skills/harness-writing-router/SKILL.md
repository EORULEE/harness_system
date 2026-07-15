---
name: harness-writing-router
description: Short-command router for the domain-adaptive Writing Suite. Interprets brief writing requests and routes them to planner, writer, audit, polish, patent, slide, HTML, HWP, or DOCX skills.
disable-model-invocation: false
argument-hint: "<short writing request and optional source text/files>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-writing-router — 짧은 글쓰기 명령 라우터 (입구일 뿐, 안전장치 우회 없음)

매번 긴 writing contract를 쓰지 않아도, **짧은 요청**("리뷰어 답변 다듬어줘", "보고서 요약 써줘",
"PPT outline 만들어줘")을 분류해 적절한 Writing Suite skill 체인으로 연결한다.
규칙 정본 = `_writing-core/writing-router-rules.md` · 사용자 가이드 = `docs/writing-short-commands-v6.md`.

## ⚠️ 경계 (위반 금지)
- **라우터는 입구일 뿐**, 기존 안전장치를 **우회하지 않는다**. 대상 skill의 SKILL.md 규칙(원본 보호·draft only·면책 등)을 그대로 따른다.
- **라우터는 직접 파일을 수정하지 않는다**(allowed-tools = Read/Grep/Glob). 필요하면 대상 skill의 SKILL.md를 Read해 그 규칙대로 다음 단계를 **안내**한다.
- 기존 12개 writing skill은 **명시 호출 전용** 상태 유지. 라우터만 짧은 요청을 자동 해석한다(`disable-model-invocation: false`).
- 사용자가 충분한 근거자료를 안 주면 **새 사실을 만들지 않는다**(최대 3개만 질문).

## 역할
1. 짧은 요청을 **문서 유형으로 분류**(아래 분류 규칙).
2. 필요한 **skill 체인 선택**.
3. 정보 충분 → 바로 다음 단계 진행(draft-only면 즉시). 부족 → **최대 3개 질문**.
4. 매번 긴 contract 요구 안 함 — 필요 시 **내부 mini-contract**만 구성.
5. **중요 문서·특허·HWP/DOCX 양식·외부 제출물 → 사용자 확인**.
6. claim-evidence 검증 필요 작업엔 **audit 자동 제안** · 최종 제출 전엔 **form-export-review 권장**.

## 분류 규칙 (요청 키워드 → skill 체인)
| 신호(키워드) | skill 체인 |
|---|---|
| 리뷰어 답변·리뷰어 대응·reviewer response·response letter·revision response | `harness-reviewer-response` (→ 문체 다듬기 시 `harness-writing-polish`) |
| 셀프리뷰·모의심사·투고 전 검토·self review·pre-submission review | `harness-paper-self-review` |
| 심사서·피어리뷰·논문 심사·peer review·review report | `harness-paper-peer-review` |
| 논문·paper·manuscript·abstract·introduction·discussion·conclusion | `harness-writing-planner` 또는 `harness-paper-writer` |
| 보고서·report·성과요약·executive summary | `harness-writing-planner` 또는 `harness-report-writer` |
| 특허·발명신고서·claim·청구항 | `harness-writing-planner` → `harness-patent-assist` |
| 발표·PPT·슬라이드·speaker notes·outline | `harness-slide-writer` |
| 다듬어줘·rewrite·polish·문체·학술적으로 | `harness-writing-polish` |
| 근거 검토·claim 검증·과장 확인·수치 확인 | `harness-claim-evidence-audit` |
| HTML 문구·visible text | `harness-html-copy-polish` |
| DOCX 양식·워드 양식·template docx | `harness-docx-template-style` |
| HWP 양식·한글 양식·표 양식 | `harness-hwp-template-style` |
| 최종 제출 전 확인·export review | `harness-form-export-review` |

## 짧은 명령 alias
`WR:reviewer`(리뷰어 답변 rewrite) · `WR:paper`(논문) · `WR:report`(보고서) · `WR:patent`(특허/발명신고서) ·
`WR:slide`(발표 outline) · `WR:polish`(문장 다듬기) · `WR:audit`(claim-evidence 검증) ·
`FMT:docx`(DOCX 양식) · `FMT:hwp`(HWP 양식) · `FMT:review`(최종 export review).

## 예시 처리
1. `WR:reviewer …` — reviewer comment·수정내용·draft가 있으면 **audit → polish**. **수정 내용이 없으면 "무엇을 수정했는지"만 질문**.
2. `WR:report …` — 근거자료 충분하면 report summary draft(수치·한계 보존) + **audit table 포함**. 근거 없으면 "근거자료 제공" 요청.
3. `WR:paper …` — 논문 문체로 rewrite, **새 citation 생성 금지**, claim-evidence table 포함.
4. `WR:polish …` — 의미·수치·인용 변경 금지, **diff proposal** 출력.
5. `FMT:docx …` — 원본 수정 금지, **style audit + 적용 계획만**.

## 부족한 정보 질문 규칙
- **최대 3개**까지만. 근거 없으면 새 사실 생성 금지.
- 리뷰어 답변에 수정 내용 없음 → "무엇을 수정했는지"만.
- 보고서/논문에 수치·근거 없음 → "근거자료 제공" 요청.
- 특허 → 법률 판단 안 함, **변리사 검토 필요 명시**.
- HWP/DOCX → 원본 수정 없이 **계획만**.

## live 모델 호출 정책
- live 호출은 승인된 상태로 간주하되, 아래는 **한 번 더 확인**: ① 민감자료 ② 특허/발명신고서 ③ 외부 제출물 최종본 ④ ChatGPT/codex adversarial review ⑤ HWP/DOCX 실제 적용 ⑥ API 비용 발생 작업.
- 일반 draft/polish는 `_writing-core/model-policy.yaml`을 따른다. primary writer quota 실패 시 **fallback 정책 보고**.
- 사용자가 **"외부 모델 사용 금지"**라고 하면 **Claude-only/offline**으로 진행(외부 호출 안 함).

## 출력 형식
1. 분류 결과 · 2. 선택한 skill 체인 · 3. (부족 시) 최대 3개 질문 · 4. (가능 시) draft/audit/polish 결과 ·
5. 수치·인용·claim 보호 여부 · 6. 다음 추천 단계.

## 규칙 (공통)
- 직접 파일 수정 금지(Read/Grep/Glob만). 원본 HWP/DOCX 직접수정 금지 → 복사본/draft. 모델명 하드코딩 금지(role·model-policy.yaml 참조).
- secret 원문 출력 금지. AI 탐지 회피 목적 금지. 새 factual claim 생성 금지. 안전장치 우회 금지.
