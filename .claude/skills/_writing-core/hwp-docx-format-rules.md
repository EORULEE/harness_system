# hwp-docx-format-rules.md — HWP/DOCX 양식 규칙 (AC7·AC8)

> `harness-hwp-template-style`·`harness-docx-template-style`·`harness-form-export-review`가 준수.

## ⛔ 원본 보호 (제1원칙 — AC8)
- **원본 .hwp/.hwpx/.docx 직접수정 금지.** 항상 **복사본/draft**에서 작업.
- 입력경로 ≠ 출력경로 (in ≠ out). 출력은 `*_draft.*`·`*/work/*`·`*.out.*` 등 비원본.
- 적용은 **사용자 승인 후**. 승인 전엔 diff/미리보기만.
- ⚠️ 기계강제(예정, Phase C): `hookify.block-write-original-office.local.md`를
  Phase C에서 **처음엔 disabled 또는 warn**으로 생성 → smoke 통과 + **별도 승인 후 block 전환**.
  **원본 `.hwp/.hwpx/.docx` 직접 덮어쓰기만 차단**하고, **`_output/forms/**` 복사본 생성은 허용**.
  Phase A/B에서는 이 규칙을 만들지 않는다(문서약속만).

## 1. HWP 양식 (harness-hwp-template-style)
- 표 양식은 **기존 `hwp-table-style` 스킬을 재사용(위임)**한다(AC14, 무수정).
- 그 스킬의 **사용자 표-매핑 게이트**(SKILL.md "표 매핑은 사용자 확인")를 **보존**한다.
- 검증은 **렌더 이미지**(한컴→PDF→PNG, 눈으로 비교) — 숫자만 보고 판단 금지.
- 글꼴·글자색·셀배경 등 COM/바이너리 경계는 hwp-table-style 규칙 따름.

## 2. DOCX 양식 (harness-docx-template-style) — 폴백 2엔진
- **기본**: `python-docx`(설치 확인 1.2.0) — 레퍼런스 .docx 복사 후 텍스트/표/스타일 적용.
- **폴백(고충실)**: 한컴 COM(Windows) — `python-docx`로 표현 불가한 양식.
- 선택은 `_format-profiles/docx/<name>/format.yaml`의 `engine` 키.

## 3. 양식 export 검토 (harness-form-export-review)
- 산출 문서를 렌더(PDF/PNG)해 레퍼런스와 시각 대조 후 사용자 보고.
- 원본 무변경·복사본 산출 확인.

## 4. 금지
- 원본 경로 덮어쓰기. 사용자 승인 없는 양식 적용. 한컴 interop 무한 taskkill([[feedback_hancom_interop_caution]]).
