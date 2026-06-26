---
name: harness-wiki-query
description: "vault/wiki에서 질문에 대한 답을 종합. 관련 페이지 식별→읽기→[[wikilink]] 인라인 인용으로 답 합성→선택 저장(syntheses/). 합성은 2-pass(c-/x-), 인용은 실재 페이지만(broken 0). 에이전트 모드. 명시 호출 전용."
disable-model-invocation: true
allowed-tools: [Read, Grep, Glob, Write, Task]
---

# harness-wiki-query — 위키 종합 질의 (에이전트 모드)

> 정본 [[_wiki-core/wiki-rules.md]]. **LLM 단계는 이 세션(Claude)** — litellm 금지.

## 입력
`query: <질문>`

## 절차
1. `vault/wiki/index.md` 읽어 관련 페이지 식별 (Grep로 키워드 교차)
2. 해당 페이지들 Read
3. **2-pass 합성**:
   - c-: 페이지 근거로 답 구성, 각 주장에 `[[PageName]]` 인라인 인용
   - x-: 위키에 없는 내용을 지어내지 않았는지·과일반화·인용 정확성 적대검토(Task)
4. **인용은 실재 페이지만** — `[[link]]`가 실제 vault/wiki 파일을 가리키는지 확인(broken 0). 위키에 근거 없으면 "위키에 출처 없음"이라 답하고 ingest 제안.
5. 사용자에게 답을 `vault/wiki/syntheses/<slug>.md`로 저장할지 질문(저장 시 page-schema synthesis 타입).

## 금지
위키 밖 내용 날조 · broken link · litellm/외부 API.
