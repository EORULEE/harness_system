---
name: harness-docx-template-style
description: "DOCX 양식 적용 '계획' skill. template docx 분석으로 style profile·heading mapping·paragraph/table/caption style·references/bibliography rules를 정의하고 계획/체크리스트만 산출한다. field/TOC/citation/numbering 보호. 원본 직접수정 금지·복사본 작업. 실제 적용은 안 함. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<format_profile name 또는 대상 .docx file_path>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-docx-template-style — DOCX 양식 적용 계획 (plan only)

DOCX 양식을 레퍼런스 template대로 맞추는 **계획·체크리스트**를 만든다. **실제 적용은 하지 않는다.**

## 양식 엔진 (format-profile에서 선택)
- 기본 **python-docx**(설치확인 1.2.0) — 레퍼런스 복사본에 스타일 적용 계획.
- 고충실 필요 시 **한컴 COM** 폴백(format.yaml `engine: hancom-com`).

## ⛔ 원본 보호
- 원본 `.docx` **직접수정 금지** → **레퍼런스 복사본**(`_output/forms/**` 등)에만(`_writing-core/hwp-docx-format-rules.md`). 적용은 사용자 승인 후.

## 정의 항목 (계획에 포함)
1. **style profile**: template `.docx` 분석(스타일 목록·기본 폰트·여백).
2. **heading mapping**: 문서 제목 레벨 ↔ template Heading 스타일.
3. **paragraph style** · **table style** · **caption style**(그림/표 캡션 번호 규칙).
4. **references/bibliography rules**: 인용·참고문헌 스타일(실재 출처만, [[citation-numeric-protection]]).

## ⛔ 보호 (변경 금지)
- **field, TOC, citation, numbering**(자동 필드·목차·인용 필드·번호) 보존.
- 표 값·그림/캡션 번호·DOI 불변.

## 검증 계획 (실행은 안 함)
- **openability check**(파일 열림) · **style check**(스타일 적용 일치) · **field check**(필드·TOC 무손상).

## 출력 (plan/checklist only)
- 양식 적용 **계획**(복사본 경로·엔진·heading/table/caption 매핑·references 규칙).
- **체크리스트**: [ ] 복사본 [ ] field/TOC/numbering 보존 [ ] openability/style/field check [ ] 원본 무변경.
- 실제 적용·렌더·변환 안 함.

## 규칙 (공통 B2)
- 명시 호출 전용. 기존 파일·원본 직접수정 금지. 실제 양식 적용 금지(계획만).
- format profile 참조. domain profile은 내용 용어 보호에만(양식 로직과 분리).
- 수치·인용·표 값·그림/캡션 번호·DOI 변경 금지. secret 출력 금지. 모델명 하드코딩 금지.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
