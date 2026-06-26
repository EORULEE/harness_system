# loop-routing-policy.md — 자연어 → 작업유형 → recipe 라우팅 정책

> r3 후보(harness-2026-06-23-r3-loop-rc). r2 불변. harness-loop-engineering 이 이 표로
> 라우팅한다. **사용자는 DEV·Ralph·Writing Suite·Mode C 등 내부 이름을 몰라도 된다** — 자연어만으로
> 기존의 적절한 작업·검증 경로를 자동 선택한다. **새 범용 실행기·두 번째 오케스트레이터를 만들지 않는다**
> — 현재 설치된 DEV Suite·Ralph·Writing Suite·Research·Experiment Tracking·Mode C·Knowledge
> Promotion·Claude Design·배포 workflow 를 재사용한다.

## 1. 원칙
- **분류는 결정적 코드가 아니라 Claude 판단**(advisory hook 은 넛지만). 모호하면 좁히는 질문 우선.
- **one-shot 우선**: 설명·상태조회·파일읽기·짧은 문장수정·단순 사실확인은 loop·추가 agent 없이 즉답.
- **수정루프는 명시적 실행 의도에만**: "이 함수 뭐야?"(질문)는 수정루프를 시작하지 않는다.
- 각 recipe 는 `validation_mode` 를 **필수**로 가진다(loop-verifier-policy.md).

## 2. 라우팅 표 (자연어 신호 → task_type → recipe → executor → 기본 validation_mode)

| 자연어 신호(예) | task_type | recipe | executor(재사용) | 기본 validation_mode |
|---|---|---|---|---|
| "설명해줘", "상태 어때", "이 파일 읽어", "이 오타 고쳐"(1문장) | `simple-question` | simple-question | claude-main | one-shot |
| "이 함수 무슨 역할이야?", "이 코드 왜 이래?" | `code-question` | code-question | claude-main | one-shot |
| "버그 고쳐줘", "이거 자동으로 고쳐줘", "왜 깨져?(수정의도)" | `code-bugfix` | code-bugfix | dev-suite(debug→tdd→review) | deterministic-only → executor-verifier |
| "기능 구현해줘", "추가해줘", "만들어줘"(신규) | `code-feature` | code-feature | dev-suite(+deep-interview?+Ralph?) | executor-verifier (중요시 cross-model + Ralph) |
| "조사해줘", "최신 동향", "비교 정리"(광범위) | `research` | research | research workflow(multi-model) | executor-verifier |
| "이거 사실이야?", "버전 맞아?"(단발) | `fact-check` | fact-check | claude-main | one-shot |
| "다듬어줘", "보고서 써줘", "polish" | `writing` | writing | writing-suite | deterministic-only + human-gated(중요주장) |
| "학습률 3개 비교", "A/B 실험" | `experiment` | experiment | experiment-tracking → Mode C | deterministic-only + human-gated |
| "이 HWP/DOCX/HTML 양식 맞춰줘" | `document-form` | document-form | form-export-review | deterministic-only + human-gated |
| "이 PPT 디자인 개선해줘" | `claude-design` | claude-design | claude-design bridge | deterministic-only + human-gated |
| "이거 Wiki 정본으로 올려", "지식 승격" | `knowledge-promotion` | knowledge-promotion | knowledge-promotion-gate | cross-model + human-gated |
| "이 서버에 배포해줘" | `deployment` | deployment | 배포 workflow | deterministic-only + human-gated (중요배포 +cross-model) |
| "오래 걸리는 학습/백업 돌려줘" | `long-compute` | long-compute | nohup/tmux + watcher | deterministic-only(완료/로그 감시만) |
| "그림/개념도/인포그래픽/일러스트 그려·만들어" | `visual-generation` | visual-generation | Claude SVG/NotebookLM/Nano Banana Pro/Lottie/Claude Design | deterministic-only + human-gated(업로드/유료/sync) · 정량 figure=생성모델 금지 |

## 3. 코드 작업 세분 규칙 (중요)
- **버그 수정**: `DEV:debug → DEV:tdd → 환경 테스트 → DEV:review`.
- **새 기능**: 모호하면 **deep-interview 확인**(1줄) → `DEV:tdd → 테스트 → DEV:review`.
- **다중 파일·보호 파일·핵심 아키텍처·명세계약 존재** → 위 경로 후 **Ralph 완료 검증**까지.
- **작은 단일 파일 수정** + 결정적 테스트 전부 PASS → **Ralph 생략 가능**(단 **생략 이유를 ledger 에 기록**).
- DEV·Ralph 라는 이름을 사용자가 직접 말하지 않아도 동작. **코드 질문**만 한 경우 수정루프 미시작.

## 4. 기본 검증 강도 (validation_mode 매핑 — loop-verifier-policy.md 와 정합)
| 상황 | 기본 강도 |
|---|---|
| 단순 질문 | one-shot |
| 작은 코드 수정 | deterministic-only |
| 중요 코드·다중 파일 | executor-verifier |
| 보안·아키텍처·대규모 수정 | cross-model + Ralph |
| 광범위 조사 | executor-verifier |
| 중요 주장·특허·Wiki 승격 | cross-model + human-gated |
| 실험 | deterministic-only + human-gated |
| 문서·Design | deterministic-only + human-gated |
| 배포 | deterministic-only + human-gated (중요배포 cross-model 추가) |

## 5. 억제(loop 미발화) — advisory hook 과 정합
- 상태 조회·개념 질문·파일 읽기·짧은 문장 수정 → **계약 생성조차 안 함**, 바로 처리.
- 기존 dev-intent / research-intent / system-question hook 과 **중복 안내 금지**(loop-intent-hook 은 그 신호가 이미
  잡히면 침묵). 사용자가 **실행을 요청한 경우에만** 실제 recipe 실행.
