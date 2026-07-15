# dev-discipline cheatsheet (상세 규율 정본)

> ⚠️ **advisory · 침묵 적용**. 이 문서는 고위험 엔지니어링 작업에서 Claude가 **내부적으로만**
> 참고하는 체크리스트다. **전체를 출력하지 않는다** — 산출에 영향 주는 최소 기준만 ≤2줄 언급.
> **최종 안전권위는 stop-guard·hookify**(이 규율은 그 하위). 적용 여부 = `dev-discipline-trigger-policy.md`.
> 기존 메모리/규칙과 겹치면 **펼치지 말고 링크만**(DRY). 단순 질문·번역·prose에는 적용·언급 0.

---

## 1. Systematic Debugging (오류·traceback·blank render·selector 실패)
추측으로 고치지 않는다. 순서:
1. **재현(reproduce)**: 실패를 결정적으로 재현하는 최소 명령/입력을 먼저 확보. 재현 못 하면 "재현 불가"로 표기.
2. **격리(isolate)**: 에러 메시지·스택의 **원문 라인을 먼저 인용**한 뒤 해석(글로벌 §3). 범위를 한 파일/함수로 좁힌다.
3. **가설(hypothesize)**: 1개 가설 → 그 가설이 틀렸을 때 무엇이 보일지도 적는다.
4. **수정(fix)**: 가설을 검증하는 최소 변경. 무관한 리팩터 섞지 않는다.
5. **검증(verify)**: 같은 재현 명령으로 **fresh evidence** 재실행. "고쳐졌을 것" 금지.
- 렌더/캡처류(Lottie·browser): `--virtual-time-budget` 단독 빈 캔버스 레이스 → playwright **프레임 카운터 대기 후 캡처**(결정적). 참고 [[reference_lottie_pipeline]].
- 환경 주장 전 probe(`which`/`ls`/`grep`/Read), 자명하지 않으면 "확실치 않음"(글로벌 §1).

## 2. Verification Before Completion (완료 주장 게이트)
"완료/통과/정상작동/렌더됨/secret 없음/배포됨"을 **fresh evidence 없이 주장하지 않는다**(허위 준수 방지, 글로벌 §2·§4).
- 주장 1개 = 증거 1개. 증거 = 방금 실행한 test/build/ffprobe/픽셀샘플/grep/md5의 **원문 출력**.
- 추정·캐시된 기억·"보통 그럴 것"은 증거 아님. 못 한 검증은 "미검증/미실행"으로 정직 표기.
- 메타블록 주장(task_calls·Iteration·pass)은 audit log 실측치와 일치해야 함.
- 완료 주장 유형 예: "배포됐다"→md5 일치 출력 · "통과"→테스트 출력 · "secret 없다"→scan 결과 · "렌더된다"→캡처 프레임.

## 2b. Code-Behavior Claim Gate (코드가 "무엇을 한다"·값이 "무엇을 측정한다" 주장 — 분석)
§2(완료 주장)의 형제. 코드 동작·값 의미를 주장하기 전 **그 값을 생산하는 함수**를 serena(`find_symbol`)/Read 로 열어 결정적 라인(`file:line`)을 **원문 인용 후 해석**(글로벌 §3).
- **컨테이너 ≠ 측정**: crop·배열 shape·valid% 는 처리 컨테이너일 뿐, 산출이 쓰는 **마스크/부분집합/평균 대상**과 다르다("valid 100%"≠"전체가 대상").
- 전송 직전 `python3 scripts/code_claim_lint.py <draft|->` 로 자기 draft self-check(인용 없는 동작 주장 surface → 읽고 인용 or "확실치 않음" 강등). heuristic 보조기(flag 0 ≠ 검증완료).
- 정본 [[code-claim-evidence-rules]]·[[feedback_read_producing_function]]. (고위험은 Layer 3 cross-model codex exec 적대검토(CLI) 옵트인.)

## 3. Mode B Code-change TDD (코드/스크립트 변경)
**적용 조건**(전부 충족 시): ① 검증 가능한 동작 변경 ② 회귀 위험 있음 ③ DL **본학습이 아님**(DL은 §6 carve-out).
- read-before-edit: 편집 전 대상 파일을 읽고 **주변 코드 양식**(주석밀도·명명·관용)에 맞춘다.
- 가능하면 **검증을 먼저**: 실패하는 케이스/명령을 정하고 → 수정 → 그 케이스로 통과 확인(fresh).
- 작은 단위로. `git --no-verify`/`--no-gpg-sign` 금지(hookify `block-git-no-verify`). 데이터 dtype 변경 금지([[feedback_data_dtype_preserve]]).
- 수정 후 회귀 재검증. 정리(cleanup) 편집했으면 다시 검증.
- ⚠️ stop-guard·hookify·settings·hook 파일 **자체 수정은 권위 불가침** — 사용자 명시 승인 없이 손대지 않는다.

## 4. Skill TDD (새 skill/router/workflow/profile 작성)
- **계약 먼저**: 입력·출력·수용기준을 명세(필요 시 `harness-deep-interview`). 산출은 draft/diff 우선.
- 플래그 점검: `disable-model-invocation`·`allowed-tools`·`disableSkillShellExecution`를 의도대로. **auto-invoke(자동발화) 금지**가 기본.
- **오프라인 smoke** 결정적 테스트로 검증(예: `tests/smoke_*.sh`). 실제 모델 호출은 별도 승인.
- 기존 자산(스킬·엔진) md5 불변 확인. 라우터는 분류만, 모델 고정 금지(model-policy SoT 참조).

## 5. Receiving Code Review (codex/x-review 피드백 수신)
- 지적을 **맹목 적용하지 않는다**. 1건씩: 원문 근거 확인 → 실제 재현/검증 → 타당하면 반영, 아니면 반박 근거 기록.
- x-(적대) 검토는 비대칭 검증용 — 새 major 지적이면 2-pass divergence로 다룬다(글로벌 A1 2-pass).
- 리뷰어가 틀릴 수 있음: 코드/로그 원문으로 교차확인 후 판단. 수정했으면 회귀 재검증(§2).

---

## 부록 — 트리거별 추가 규율(요약 링크)
- HWP/DOCX 자동화: COM·렌더 육안검증 [[reference_hwp_editing]] · 한컴 interop 주의 [[feedback_hancom_interop_caution]].
- 멀티머신 배포: md5 일치·`.bak` 백업·idempotent · **server-a 배포동결** [[feedback_server-a_deploy_freeze]].
- DL 학습 전: smoke/checklist/log 저장·본학습 승인 [[feedback_dl_workflow]] (§6 = smoke-as-test).
- settings/hookify/stop-guard 작업: `.bak`·JSON 유효·규칙 테스트·권위 불가침.
- secret: 출력 전 `scripts/secret_masking.py`로 마스킹, residual 0 확인.
