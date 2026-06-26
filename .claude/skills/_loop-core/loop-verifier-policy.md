# loop-verifier-policy.md — 검증 모드·verifier 정책

> r3 후보(harness-2026-06-23-r3-loop-rc). r2 불변. `validation_mode` 5종의 정의와
> verifier 의 권한 경계, 검증 우선순위의 SoT.

## 1. validation_mode 정의 (loop-contract-schema.yaml enum 과 정합)

### one-shot
- 추가 반복·추가 agent 없음. 단발 응답.
- 대상: 설명·상태조회·파일읽기·짧은 문장수정·단순 사실확인.

### deterministic-only
- **환경 검증만**: compile·test·lint·schema·metric·render·security scan.
- 모델 교차검증 없음. 작은 코드 수정·실험·문서·배포의 1차 게이트.
- 통과 기준 = 실제 실행 결과(녹색). "아마 될 것" 금지.

### executor-verifier
- **실행자**(Write/Edit/Bash 권한)와 **읽기전용 verifier**(별도 컨텍스트)를 분리.
- ⚠️ **verifier 는 Write/Edit 권한이 없다**(코드 수정 금지). 발견만 보고.
- 구현 = read-only Explore/Plan 서브에이전트(Write/Edit/NotebookEdit 미보유) 또는 별도 Claude.
- 대상: 중요 코드·다중 파일·광범위 조사(독립 조사자 vs 검증자 분리).

### cross-model
- Claude 결과를 **Codex(ChatGPT)/외부 모델이 반박**(적대검토).
- ⚠️ **Codex 결과는 사실 정본이 아니다** — Claude 가 source 로 재검증한다.
- 대상: 보안·아키텍처·대규모 수정, 중요 주장·특허·Wiki 승격, 중요 배포.
- 경로 = `/codex:adversarial-review`·`/codex:review`(플러그인 app-server, gpt-5.5). 유료 → human-gated 동반.

### human-gated
- 배포·삭제·push/merge·외부 업로드·비용 발생 호출·Mode C 실행·Design sync·Wiki 승격에
  **사용자 승인 필수**. 승인 전 해당 행위 시작 금지.

## 2. verifier 권한 경계 (하드)
- verifier(읽기전용)·백그라운드 agent **내부에서는 AskUserQuestion 을 호출하지 않는다**.
  질문·승인은 **주 orchestrator(harness-loop-engineering)만** 담당.
- verifier 의 Write/Edit/Bash(mutating) **= 0**. 위반 시 그 verdict 무효.
- **강제 메커니즘(정직)**: verifier 는 **Write/Edit/NotebookEdit 도구가 없는 agent type 으로 스폰**한다
  (예: `Explore`·`Plan` — 도구 집합에 Write/Edit 미포함). 즉 정책 선언만이 아니라 **도구 수준 제약**으로
  강제된다. 주 orchestrator 가 verifier 에게 full-tool agent 를 쓰면 본 정책 위반(금지).

## 3. 검증 우선순위 (verdict 산정 순서)
1. **실제 실행·컴파일·테스트·metric·render** (1순위 — 가장 강한 증거)
2. **schema·lint·contract·security scan**
3. **독립 verifier 또는 Codex 적대검토**(읽기전용)
4. **사용자 승인**

> 상위 증거가 실패하면 하위로 보강하지 않는다(테스트 실패를 "Codex 가 괜찮다 함"으로 통과시키지 않음).

## 4. 모드 조합
- recipe 의 `validation_mode` 는 **list** 가능(예: `[deterministic-only, executor-verifier]`,
  `[cross-model, human-gated]`). 강한 모드가 약한 모드를 대체하지 않고 **누적**된다.

## 5. 금지
- 모든 작업에 무조건 agent 교차검증(과검증) **금지** — 강도는 §라우팅 표대로 작업 위험도에 비례.
- verifier 의 코드 수정 금지. 무한 반복 금지. stop-guard 약화 금지.
