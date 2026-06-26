---
name: harness-hwp-template-style
description: "HWP/HWPX 양식 적용 '계획' skill (orchestration layer). 기존 hwp-table-style + hwp_workflow/hwp_convert 계열을 재사용해 양식 적용 계획·체크리스트만 산출한다. 원본 직접수정 금지·복사본 작업·표 매핑 사용자 확인·render PNG 검증 필수. 실제 적용은 안 함. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<format_profile name 또는 대상 .hwp file_path>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-hwp-template-style — HWP 양식 적용 계획 (plan only, orchestration)

HWP/HWPX 양식을 레퍼런스대로 맞추는 **계획·체크리스트**를 만든다. **실제 양식 적용은 하지 않는다.**

## ⚠️ 재사용 (수정 금지)
- 표 양식: 기존 **`hwp-table-style`** 스킬(`apply_booktabs.py`·`inspect_tables.py`·`render_check.py`) **위임**(무수정).
- 변환/편집: `scripts/hwp_convert.py`·`scripts/hwp_workflow.py`·`scripts/hwp_edit_pyhwpx.py` **재사용 대상으로 참조만**(무수정).
- 본 스킬 = 이들을 묶는 **orchestration 계획 레이어**. 직접 실행·수정하지 않는다.

## ⛔ 원본 보호 (제1원칙)
- 원본 `.hwp/.hwpx` **직접수정 금지** → **복사본**(`_output/forms/**` 등 비원본)에서만(`_writing-core/hwp-docx-format-rules.md`).
- 입력경로 ≠ 출력경로. 실제 적용은 **사용자 승인 후**.

## 절차 (읽기 전용 — 계획만)
1. `format_profile`(`_format-profiles/hwp/<name>/format.yaml`) Read → engine·reference_template 확인.
2. 대상/레퍼런스 표 구조 파악(inspect_tables 위임 계획).
3. **표 매핑은 사용자 확인 필수** — 머리행/데이터행·매핑을 AskUserQuestion로 확정(자동 매핑 금지).
4. **render PNG 검증 계획**: 한컴→PDF→PNG 렌더 후 눈으로 레퍼런스 대조(숫자만 보고 판단 금지).
5. **한컴 taskkill 반복 금지**(`[[feedback_hancom_interop_caution]]` — drvfs 다운 위험).

## 출력 (plan/checklist only)
- 양식 적용 **계획**(복사본 경로·위임 스크립트·표 매핑 질문 목록).
- **체크리스트**: [ ] 복사본 작업 [ ] 표 매핑 사용자 확인 [ ] render PNG 대조 [ ] 원본 무변경.
- 실제 적용·실행·렌더 안 함. 사용자 승인 후 별도 단계.

## 규칙 (공통 B2)
- 명시 호출 전용. 기존 파일·원본 직접수정 금지. 실제 양식 적용 금지(계획만).
- format profile 참조. domain profile은 **내용 용어 보호에만**(양식 로직과 분리).
- 수치·인용·표 값·그림/캡션 번호·DOI 변경 금지. secret 출력 금지. 모델명 하드코딩 금지.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
