---
name: harness-form-export-review
description: "HWP/DOCX/HTML 최종 제출 전 점검 skill. heading hierarchy·table/figure numbering·captions·references·citation·numeric values·page breaks·fonts·secret scan·render/openability를 확인해 PASS/FAIL table을 출력한다. 직접 수정하지 않음. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<점검할 .hwp/.docx/.html file_path>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-form-export-review — 제출 전 양식/무결성 점검 (audit only)

최종 산출 문서를 제출·export 전에 점검해 **PASS/FAIL 표**를 낸다. **직접 수정하지 않는다.**

## 점검 항목 (PASS/FAIL)
| 항목 | 확인 |
|---|---|
| heading hierarchy | 제목 레벨 일관·건너뜀 없음 |
| table/figure numbering | 표/그림 번호 연속·중복 없음 |
| captions | 캡션 번호·본문 참조 일치 |
| references | 참고문헌 형식·본문 인용 매칭 |
| citation | 인용 키 실재·누락 없음([[citation-numeric-protection]]) |
| numeric values | 본문 수치 ↔ 표/그림 일치(변경 금지, 대조만) |
| page breaks | 페이지 나눔·빈 페이지 |
| fonts | 폰트 일관(양식 profile 대비) |
| secret scan | API key·token 원문 0 |
| render/openability | 파일 열림·렌더 가능(계획상 확인, 실제 실행은 사용자 승인) |

## 절차 (읽기 전용)
1. 대상 문서 Read(또는 구조 파싱 계획) → 위 항목별 점검.
2. format_profile 대비 폰트·스타일 일치 확인.
3. 각 항목 PASS/FAIL + 근거.

## 출력 (PASS/FAIL table only)
- 항목별 **PASS/FAIL 표** + 실패 항목 사유.
- **직접 수정 안 함** — 실패 항목은 수정 권고(해당 format/polish 스킬로 라우팅 제안).
- 실제 렌더/변환은 실행하지 않음(사용자 승인 후).

## 규칙 (공통 B2)
- 명시 호출 전용. 원본 직접수정 금지. format profile 참조. domain profile은 내용 용어 보호에만.
- 수치·인용·표 값·그림/캡션 번호·DOI 변경 금지(점검만). secret 출력 금지. 모델명 하드코딩 금지.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
