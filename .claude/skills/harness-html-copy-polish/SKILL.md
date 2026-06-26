---
name: harness-html-copy-polish
description: "HTML의 visible text만 polish하는 diff proposal skill. tag·id·class·style·script·href·src·data-* 와 table numeric·DOI·citation·code/pre/script/style 내부는 변경 금지. diff proposal만 출력(직접수정 안 함). html-report-workflow·serve_html 구조 무변경. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<대상 .html file_path>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-html-copy-polish — HTML visible text polish (diff proposal only)

HTML의 **보이는 텍스트만** 다듬는 제안을 만든다. 구조·속성·스크립트는 보호한다. 규칙 정본 = `_writing-core/html-safety-rules.md`.

## ⛔ 보호 (수정 금지)
- **tag** 구조 · `id` · `class` · `style` · `script` · `href` · `src` · `data-*`.
- **table numeric values · DOI · citation** 불변.
- **`code`/`pre`/`script`/`style` 내부** 텍스트 불변(코드·스타일 보호).

## ✅ 수정 제안 허용
- 일반 **visible text node**(보호 영역 밖)만. 인용·수치는 불변([[citation-numeric-protection]]).

## ⚠️ 무변경 대상 (구조)
- 기존 **`html-report-workflow`** 스킬과 **`serve_html.sh`/`serve_html.ps1`** 호스팅 구조를 **변경·수정하지 않는다**(이 스킬은 텍스트 polish 제안만).

## 절차 (읽기 전용 + 제안)
1. 대상 `.html` Read → DOM 파싱 계획(visible text node만 식별).
2. 보호 영역(tag/속성/code/pre/script/style/table 수치) 제외.
3. visible text 완화 후보 → **변경 전/후 쌍** 작성.
4. 변경 전후 **DOM 구조·속성 diff 0** 보장 확인(태그/속성 불변).

## 출력 (diff proposal only)
- **diff proposal** 표: `원문 텍스트 → 제안 | 사유`.
- 보호 불변식 확인 1줄(tag/id/class/href/src/script/style/data-*·수치·DOI diff 0).
- **원본 직접수정 금지** — 사용자가 검토 후 복사본에 적용.

## 규칙 (공통 B2)
- 명시 호출 전용. 원본 HTML 직접수정 금지. format profile(family=html) 참조.
- domain profile은 내용 용어 보호에만. secret 출력 금지. 모델명 하드코딩 금지. AI 탐지 회피 금지.
