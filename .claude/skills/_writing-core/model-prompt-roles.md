# model-prompt-roles.md — 역할별 프롬프트 규범

> 모델명 리터럴 금지(AC2). role 이름만 사용.

각 role이 받는 프롬프트의 **규범**을 정의한다. 실제 모델 해석은 `model-policy.yaml`.

## orchestrator (Claude)
- 입력: 사용자 요청 + 선택된 domain-profile + format-profile + writing-contract.
- 책임: 작업 분해 → writer 호출 → 결과 사실·정합 검증 → format skill 배선 → 최종 전달.
- 규범: 추측 금지·실측 우선. writer 산출을 **그대로 통과시키지 않는다**(반드시 검증).

## primary_writer (Gemini, gemini-writer 위임)
- 입력: orchestrator가 구성한 **정교한 페르소나(system instruction)** + 글 요청.
- 규범: 페르소나에 충실, 두괄식·능동·간결, **근거 없는 단정·수치 날조 금지**.
- 출력: 초안 + (위임 에이전트가) 페르소나 요약·반복횟수·사용엔진 메타.

## fallback_writer (ChatGPT via codex)
- 발동: primary_writer 완전 실패 시에만.
- 규범: primary와 동일 페르소나·금지사항 승계. 사용 시 메타에 "폴백 사용" 명시.

## adversarial_reviewer (ChatGPT via codex)
- 입력: 완성 초안 + 요청·근거.
- 규범: **약점을 찾도록** 지시 — 과장·근거부재·논리비약·요청불일치·사실오류.
  통과시키려 하지 말 것. 환경 불가 시 orchestrator 자기검토로 대체 + 메타 명시.

## structure_protection (deterministic tool)
- LLM이 아님. python-docx·pyhwpx·hwp5proc·HTML 파서 등 **도구**가 구조를 검증.
- 규범: 문장 품질이 아니라 **태그/스타일/표/셀 구조 무결성**만 본다.

## 공통 금지
- 없는 인용·기관·실적·수치 날조 금지 → "[확인 필요]" 표기.
- secret 원문 출력 금지. 모델명 리터럴은 본 문서·skill에 금지(model-policy.yaml만).
