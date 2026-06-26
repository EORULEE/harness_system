# html-safety-rules.md — HTML 보호 규칙 (AC9)

> `harness-html-copy-polish`가 준수. HTML 문서를 다듬을 때 **보이는 텍스트만** 손대고
> 구조·속성·스크립트는 보호한다.

## ⛔ 보호 대상 (수정 금지)
- **tag** 구조(여닫음·중첩), `id`, `class`, `href`, `src`, `script`, `style`.
- 인라인 이벤트 핸들러·데이터 속성·주석 내 지시문.

## ✅ 수정 허용
- **visible text node**(태그 사이의 표시 텍스트)만 polish.
- 단 인용·수치는 불변([[citation-numeric-protection]]).

## 1. 작업 방식
- 원본 HTML **복사본**에서 작업(AC8). 원본 직접수정 금지.
- 파싱은 도구 기반(structure_protection role) — 텍스트노드만 추출·치환 후 재조립.
- 치환 전후 **DOM 구조 diff 0**(태그/속성 불변) 확인.

## 2. 금지
- 텍스트 변경을 빌미로 태그/속성 재배치 금지.
- `<script>`/`<style>` 내부 내용 수정 금지.
- 외부 링크(href/src) 변경 금지.

## 3. 검증
- polish 후: visible text만 바뀌고 tag/id/class/href/src/script/style **불변** 정적 확인.
