---
name: harness-wiki-lint
description: "vault/wiki 콘텐츠 품질검사(의미). orphan·broken link·모순·stale·누락 entity·data gap 탐지. 결정적 부분(broken/orphan)은 Grep, 의미 판정(모순·gap)은 2-pass(c-/x-). health(구조) 통과 후 주기적 실행. 에이전트 모드. 명시 호출 전용."
disable-model-invocation: true
allowed-tools: [Read, Grep, Glob, Write, Task, mcp__zotero__zotero_search_items]
---

# harness-wiki-lint — 위키 품질검사 (에이전트 모드)

> 정본 [[_wiki-core/wiki-rules.md]]. health(구조·결정적) 통과 후 실행(빈 파일 lint는 토큰 낭비).
> **LLM 단계는 이 세션(Claude)** — litellm 금지.

## 검사 (결정적 + 의미)
- **결정적(Grep/Glob)**:
  - broken link — `[[X]]`가 존재하지 않는 페이지 가리킴
  - orphan — 인바운드 `[[링크]]` 없는 페이지
  - 무출처 주장 — `[src:]`/source 링크 없는 사실 문장(패턴 검출)
- **의미 판정(2-pass c-/x-)**:
  - 모순 — 페이지 간 충돌 주장 (→ contradictions.md 병기 제안)
  - stale — 새 소스 이후 갱신 안 된 페이지
  - 누락 entity — 3+ 페이지서 언급되나 자체 페이지 없는 엔티티
  - data gap — 위키가 답 못하는 질문(→ 새 소스 제안)
- **인용 재검증**(선택): citekey를 `mcp__zotero__zotero_search_items`로 재대조(실재성).

## 절차
1. health 먼저 통과 확인
2. 결정적 검사(Grep) → broken/orphan/무출처 목록
3. 의미 검사 2-pass(Task c-/x-) → 모순·stale·gap
4. lint 리포트 출력 + 사용자에게 `vault/wiki/lint-report.md` 저장 질문
5. 수정(모순 병기·페이지 생성)은 **사람 확인 후** ingest/편집으로 — lint는 탐지·제안만.

## 금지
모순 무단 삭제 · 가짜 citekey · litellm/외부 API.
