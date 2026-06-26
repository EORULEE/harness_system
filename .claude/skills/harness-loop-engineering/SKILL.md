---
name: harness-loop-engineering
description: "Loop Engineering Control Plane — 사용자가 DEV·Ralph·Writing Suite·Mode C 등 내부 이름을 몰라도 자연어 요청만으로 기존의 적절한 작업·검증 경로를 자동 선택한다. 새 범용 실행기·두 번째 오케스트레이터를 만들지 않고 현재 설치된 DEV Suite·Ralph·Writing Suite·Research·Experiment Tracking·Mode C·Knowledge Promotion·Claude Design·배포 workflow 를 재사용한다. 실행 전 계획 요약 + AskUserQuestion 승인 게이트. 상태 정본 = 대화가 아니라 디스크(contract/events/verdict)."
disable-model-invocation: false
argument-hint: "<자연어 작업 요청 — 예: '이 버그 고쳐줘', '학습률 3개 비교', '이 서버에 배포해줘'>"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Write
  - Edit
  - Task
  - AskUserQuestion
---

# harness-loop-engineering — Loop Engineering Control Plane (r3 후보)

> r3 후보(harness-2026-06-23-r3-loop-rc). r2 불변. 이 스킬은 **라우터/플래너**다 —
> 실제 작업은 **기존 설치된 workflow 를 재사용**해서 위임한다. **새 범용 실행기·두 번째
> 오케스트레이터를 만들지 않는다.** 정책 SoT = `.claude/skills/_loop-core/`.

## 0. 무엇을 하나
사용자의 자연어 요청 1건을 받아:
1. **작업 유형 분류**(loop-routing-policy.md) → recipe 선택.
2. **계획 요약**(8항목) → **AskUserQuestion 승인 게이트**(loop-permission-policy.md).
3. 승인 시 **기존 workflow 로 위임** 실행 + **검증**(loop-verifier-policy.md) + **예산 관리**(loop-budget-policy.md).
4. **상태를 디스크에 영속**(contract/events/verdict). 대화 컨텍스트를 loop 상태의 정본으로 쓰지 않는다.

## 1. 분류 → recipe (loop-routing-policy.md §2 표 사용)
- 단순 질문/상태조회/파일읽기/짧은 문장수정/단순 사실확인 → **one-shot, 게이트 없이 즉답**(계약 생성 안 함).
- "이 함수 뭐야?" 등 **코드 질문** → one-shot, **수정루프 미발화**.
- "고쳐줘/버그" → `code-bugfix`. "구현/추가/만들어" → `code-feature`.
- "조사" → `research`. "다듬어/보고서" → `writing`. "비교/실험" → `experiment`.
- "HWP/DOCX/HTML 양식" → `document-form`. "PPT 디자인" → `claude-design`.
- "Wiki 승격" → `knowledge-promotion`. "배포" → `deployment`. "장기 학습/백업" → `long-compute`.
- 모호하면 좁히는 질문(필요 시 deep-interview) 우선.

## 2. 계획 게이트 (loop-permission-policy.md §1 — 필수)
one-shot 이 아닌 모든 loop 는 **실행 전** 다음 8항목을 짧게 보여준다:
1. 판단한 작업 유형  2. 선택 recipe·executor  3. 진행 단계  4. 검증 방식·교차검증 여부
5. 최대 iteration·시간·비용  6. 수정 가능 파일 범위  7. 사용자 승인 필요 위험작업  8. 성공·HOLD 조건

그다음 **AskUserQuestion** 4선택지: `계획대로 실행` / `계획만 저장` / `계획 수정` / `취소`.
- **"계획대로 실행" 전에는** Write·Edit·Bash 실행·외부 모델 호출·실험·배포 **금지**(읽기전용 탐색은 허용).
  frontmatter 의 Bash/Write/Edit 권한은 **승인 후 실행 단계용** — 승인 전 사용은 stop-guard 가 잡는 규율 위반.
  "계획만 저장" 선택은 **계약 파일만** Write 인가(실행 미수행, loop-permission-policy §2).
- 일반 텍스트로 명확히 승인해도 승인 인정. "자동으로 처리해줘"여도 **계획 요약 후 1회 승인**.
- **iteration 마다 다시 묻지 않는다.** 재질문은 5가지(범위밖 파일·예산변경·유료호출·실험/배포/삭제/push/merge/업로드·전략전환)에만.
- **백그라운드 agent·verifier 내부에서는 AskUserQuestion 금지** — 질문·승인은 이 orchestrator 만.

## 3. 계약 작성 + 검증 (승인 후)
1. `loop_id` 생성: `<task_type>-YYYYMMDD-HHMMSS-<4hex>`.
2. 계약을 스키마(`_loop-core/loop-contract-schema.yaml`)대로 채워 `_claude/loops/<loop_id>/contract.yaml` 에 Write.
3. 검증: `python3 scripts/loop_contract_validator.py validate _claude/loops/<loop_id>/contract.yaml` (exit 0 필요).
4. 시작 이벤트 기록: `python3 scripts/loop_ledger.py <loop_id> append --event start --data '{...}'`.

## 4. 실행(위임) — recipe steps 대로
각 step 의 `uses` 가 가리키는 **기존 스킬/workflow 를 호출**한다(재구현 금지). 예:
- code-bugfix → harness-systematic-debugging → harness-tdd-implementation → 환경 테스트 → harness-code-quality-review
- code-feature → (모호 시 harness-deep-interview) → harness-tdd-implementation → 테스트 → harness-code-quality-review → (중요 시 harness-ralph)
- research → research-agent + multi_research.py(chatgpt) + 교차반박 + notes-app/kb
- writing → writer → harness-claim-evidence-audit → harness-writing-polish (≤2)
- experiment → experiment_contract_validator.py → (승인 시) Mode C
- document-form → 사본 → template-style → harness-form-export-review
- claude-design → 3장 파일럿 → render 검증
- knowledge-promotion → claim-evidence-audit → /codex:adversarial-review → 재검증 → (승인) 승격
- deployment → delta → backup → canary → smoke → live
- long-compute → nohup/tmux + watcher

## 5. 검증 (loop-verifier-policy.md)
- recipe 의 `validation_mode` 를 적용. 검증 우선순위: 실행/테스트/metric/render > schema/lint/contract/scan > 독립 verifier/Codex > 사용자 승인.
- **executor-verifier**: read-only 서브에이전트로 검증(Explore/Plan — Write/Edit 미보유). **verifier 코드 수정 0.**
- **cross-model**: `/codex:adversarial-review`(gpt-5.5). **Codex 결과 ≠ 정본** — Claude 가 source 로 재검증. 유료 → human-gated 동반.

## 6. 예산·HOLD (loop-budget-policy.md)
- 작업유형별 기본 예산(DEV 3iter/30분, 조사 3~5 agent·synth 2, 글쓰기 2, 실험 3, 문서·Design 2, 배포 대상 1, 승격 Codex1+재검증1).
- 같은 실패 2회·budget 초과 → **HOLD**(자율 재시도 금지) + verdict.json 기록 + 1줄 보고. 상한 5회 미수렴 → 에스컬레이션.

## 7. 상태 종료
- `verdict.json` 작성(status: **PASS|HOLD|CANCELLED|FAIL**, success/hold 조건 충족 여부, 생략 사유 등).
- `loop_ledger.py <loop_id> finalize --verdict <PASS|HOLD|CANCELLED|FAIL>` 로 마감 이벤트 + verdict 기록.
- 산출물은 `_output/loops/<loop_id>/`.

## 8. 금지 (하드)
- OMC/OmO 설치, Superpowers full runtime, 외부 Ralph 중복 설치.
- 모든 작업에 무조건 agent 교차검증(과검증). verifier 의 Write/Edit. 무한 반복.
- Mode C 자동 활성화. 유료 모델 자동 호출. 사용자 승인 없는 삭제·배포·외부 업로드·push·merge.
- stop-guard 약화. r2 release 덮어쓰기. 다른 서버·프로젝트 자동 배포.

## 9. 최종 권위
stop-guard·hookify 가 최종 권위(이 control plane 은 그 하위). primary loop authority = 하네스 1개.
