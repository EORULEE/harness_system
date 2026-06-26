---
name: block-write-original-office
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: (\.(hwp|hwpx|docx)$|templates/(hwp|docx)/)
  - field: file_path
    operator: not_contains
    pattern: _output/forms/
---
⚠️ **경고(warn): HWP/DOCX 원본·template 직접 덮어쓰기 감지 — 복사본으로 작업하세요.**

> **이 규칙은 `warn` 단계입니다.** 작업을 막지 않고 경고만 합니다.
> **`block` 전환은 별도 사용자 승인이 필요합니다.** (승인 전 `action: block` 변경 금지.)

## 목적
**HWP/DOCX 원본 보호.** Writing Suite의 양식 적용 스킬(harness-hwp-template-style·
harness-docx-template-style·harness-form-export-review)은 **원본을 직접 수정하지 않고
복사본에만** 작업해야 합니다(`_writing-core/hwp-docx-format-rules.md`, AC8).

## 경고 대상 (원본 직접 덮어쓰기)
- 원본 `.hwp` / `.hwpx` / `.docx` 파일 직접 쓰기.
- `templates/hwp/**` · `templates/docx/**` 의 원본 template 직접 덮어쓰기.

## 허용 (경고 제외)
- **복사본 작업 경로 = `_output/forms/**`** — 특히 `_output/forms/hwp/**`·`_output/forms/docx/**`
  는 경고 대상에서 제외됩니다(`not_contains: _output/forms/`).
- 즉 **원본은 두고, `_output/forms/` 아래 복사본에 양식을 적용**하는 것이 정상 흐름입니다.

## 동작 (AND 결합)
1. file_path 가 office 원본/template 패턴에 매치되고,
2. file_path 가 `_output/forms/` 를 포함하지 **않을** 때만
→ 경고(warn). 둘 중 하나라도 아니면 경고하지 않습니다(복사본 경로는 조용히 통과).

## 비고
- 기존 hookify 7규칙과 **병행**(충돌 아님). 이 규칙은 8번째 신규 규칙입니다.
- block 전환 시: 사용자 승인 → `action: block` 으로 변경 → 정적 재검증 후 적용.
- 본 규칙은 **경고만** 하며 실제 파일을 수정·차단하지 않습니다.
