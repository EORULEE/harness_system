# dev-discipline trigger policy (적용 판단 정본)

> Claude가 작업 유형을 보고 **모델 판단으로 조용히** 적용할지 결정하는 규칙.
> 결정적 코드·hook·skill auto-invoke 아님. 최종 안전권위 = stop-guard·hookify(이 규율은 advisory 하위).
> 상세 검증 기준 = `dev-discipline-cheatsheet.md`(해당 섹션만 on-demand 참고).

## 1. 자동 적용 trigger (감지 시 silent 적용)
1. 오류·실패·traceback·exception·blank render·selector 실패
2. 코드·스크립트·훅 **수정**
3. HWP/DOCX 자동화 문제
4. Lottie 렌더/JSON/player 문제
5. ChatGPT Images browser assist 문제
6. settings 병합·hookify 규칙·stop-guard 관련 작업
7. 멀티머신 배포
8. 딥러닝 학습 전 smoke/checklist/log 검증
9. **완료 주장**: "완료됐다/통과했다/정상 작동한다/렌더링된다/secret 없다/배포됐다"
10. codex/x-review 피드백 수신
11. 새 skill·router·workflow·profile 작성
12. ⭐**시스템·코드·파일·도구·스킬·훅·설정의 동작/내용/컬럼/필드/경로 설명·주장** → **소스 Read/grep 선(先)실측 강제**(기억·훅텍스트 단정 금지, 불확실=확인 후). 정본 [[feedback-source-verify-before-claim]]·글로벌 §1 probe.
    - **코드-동작/값-의미 주장**("이 코드가 X 한다 / 이 값이 Y 를 측정·계산·반환한다")은 **생산 함수 serena-first**(`find_symbol`)**+`file:line` 원문 인용+전송직전 `code_claim_lint.py` self-check**. **컨테이너(crop·shape·valid%) ≠ 측정(마스크·부분집합)**. 정본 [[code-claim-evidence-rules]]·[[feedback_read_producing_function]].

## 2. 자동 미적용 non-trigger (적용·언급 0)
1. 단순 질문  2. 개념 설명  3. 짧은 번역  4. 일반 조사 요약
5. 논문/보고서 문장 polish  6. reviewer response 문체 정리
7. 가벼운 브레인스토밍  8. "간단히 답해줘"  9. "체크리스트 없이 바로 문장만"

## 3. silent application 원칙
- 관련 작업이면 **내부적으로만** 참고. 사용자가 묻지 않으면 **전체 체크리스트 출력 금지**.
- 고위험 작업에서만 **산출에 영향 주는 최소 검증 기준을 ≤2줄**로 짧게.
- **관련 없는 작업에서 dev-discipline 체크리스트를 펼치거나 언급하지 않는다.**
- cheatsheet는 해당 섹션만 on-demand Read(상주 주입 0). 기존 1줄 규칙과 겹치면 펼치지 않는다.

## 4. simple writing bypass 원칙
- 글쓰기 작업(작성·polish·번역·reviewer 문체·요약)은 **Writing Suite/Router를 우선** 사용.
- prose 작업에 TDD·systematic-debugging을 **강제하지 않는다**.
- non-trigger 5·6(논문 polish·reviewer 문체)은 dev-discipline 미적용 — writing/polish 경로로만.

## 5. completion claim evidence gate
- trigger 9(완료 주장) 감지 시 **verification-before-completion**(cheatsheet §2) 적용.
- 주장 1개 = fresh evidence(방금 실행한 test/build/scan/md5/캡처 원문) 1개. 없으면 "미검증" 정직 표기.

## 6. code-change TDD 적용 조건
- trigger 2(코드 수정) 중 **① 검증가능 동작변경 ② 회귀위험 ③ DL 본학습 아님** 전부 충족 시 cheatsheet §3 적용.
- 사소·결정적 기계 편집(오타·문구)에는 강제하지 않음.

## 7. DL training smoke-as-test 조건
- trigger 8(DL) = **smoke 실행을 테스트로 간주**: 1-step/1-epoch smoke + checklist(lr·불균형·메트릭·붕괴) + 로그 저장.
- **본학습은 사용자 승인 전 금지**(승인 전 smoke만) — [[feedback_dl_workflow]]·hookify `dl-train-gate`(warn) 정합.

## 8. codex/x-review 수신 규율
- trigger 10 감지 시 cheatsheet §5 적용: 지적 1건씩 원문근거 확인→재현/검증→타당시 반영(맹목 적용 금지).
- 새 major 지적이면 글로벌 A1 2-pass divergence로 처리.
- ⚠️ '리뷰' 어휘 충돌 주의: **학술 reviewer response 문체 정리(non-trigger 6) ≠ codex/x-review 코드 피드백 수신(trigger 10)**. 전자는 writing/polish 경로(dev-discipline 미적용), 후자만 receiving-code-review 적용.

## 9. user override 문구 (명시 우선)
| 사용자 발화 | 동작 |
|------------|------|
| "간단히 답해줘" | dev-discipline 생략 |
| "문장만 다듬어줘" | writing/polish만 수행(dev-discipline 미적용) |
| "dev-discipline 기준으로 검토해줘" | **명시적 전체 적용**(체크리스트 펼침 허용) |
| "완료 주장 가능한지 확인해줘" | verification-before-completion(§2·§5) 적용 |

## 10. Dev Discipline Suite 자동 적용 매핑 (2026-06-16 — "알아서 처리")
> 사용자 결정(2026-06-16): **명시 호출(`DEV:`)에 의존하지 않고, 내가 trigger 감지 시 아래 Superpowers-derived 규율을 silent 자동 적용**. skill은 dmi:true 유지(Skill-도구 자동발화 아님)·stop-guard/hookify 최종권위 불변·advisory. 즉 *규율을 내가 알아서 따르되, 런타임 auto-trigger는 도입하지 않음*.

| trigger | 자동 적용 규율(정본) | 비고 |
|---|---|---|
| 1 (오류·실패·blank render·selector·HWP/Lottie/serve_html 문제) | `systematic-debugging-rules.md`(4-phase, fix 전 근본원인) | 증상 fix 금지 |
| 2 (코드·스크립트 수정) + §6 조건 | `tdd-implementation-rules.md` | **code 한정**·DL/문서/HWP/그림 carve-out |
| 9 (완료 주장) + §5 | `evidence-before-completion-rules.md`(5-step) | ralph 보조·그림=Read·배포=md5 |
| 10 (codex/x-review 수신) | `code-quality-review-rules.md`·`spec-quality-review-rules.md` | codex(ChatGPT) primary |
| 11 (새 skill·router·profile 작성) | `skill-tdd-rules.md`(RED 미확인=HOLD) | |
| 12 (코드-동작/값-의미 주장) | `code-claim-evidence-rules.md`(serena-first·`file:line` 인용·`code_claim_lint.py` self-check) | 컨테이너(crop/shape)≠측정(마스크). 정본 [[feedback_read_producing_function]] |

- **DEV: 명시 입력** 시 = `harness-dev-router`(dmi:false, 자동 해석)가 적정 skill 제안. 단 위 자동 적용은 **DEV: 타이핑 없이도** 작동(trigger 기반).
- 강도: silent §3 원칙 그대로(≤2줄, 전체 출력 금지). non-trigger(§2)·override(§9)·writing bypass(§4)는 불변.
- 정본 정책 = `superpowers-adaptation-policy.md`. cheatsheet(기존)와 신규 rules는 **상보**(겹치면 펼치지 않음).
