# 코드 품질 검토 규율 (code-quality-review)

> 출처: `vendors/obra-superpowers/upstream-subagent-driven-development.md`(quality reviewer) + `upstream-requesting-code-review.md` (MIT). 하네스 advisory.
> 목적: 단순성·YAGNI·중복·회귀위험·유지보수성 검토. **codex(ChatGPT) 교차모델 적대검토가 primary**, 본 규율은 그 **프레이밍·보조**.

## 검토 차원
1. **단순성**: 더 단순한 구현이 있나? 불필요한 추상화·간접참조?
2. **YAGNI**: 지금 안 쓰는 기능·일반화? (extra-build = [[spec-quality-review-rules]]와 연계)
3. **중복(duplication)**: 기존 코드/헬퍼 재사용 가능? 복붙?
4. **회귀 위험(regression risk)**: 인접 기능·엣지케이스 영향? 테스트 커버?
5. **유지보수성**: 이름·구조·매직넘버·주석 밀도(주변 코드 일치).

## 격리-컨텍스트 + severity 게이트 (requesting-code-review 차용)
- 리뷰어에게 **세션 히스토리 아님, 산출물 컨텍스트만**(SHA 범위·plan·diff) 전달.
- findings = **Critical / Important / Minor** 분류.
  - Critical = 즉시 fix · Important = 진행 전 fix · Minor = 기록 후 나중. 기술 근거 있으면 pushback 허용.

## codex 우선 (충돌 방지)
- **코드 적대검토 primary = `/codex:adversarial-review`(ChatGPT gpt-5.5)** — 교차모델 비대칭([[reference-codex-chatgpt-blocked]]·[[feedback-codex-2pass-deploy]]).
- 본 규율은 codex 호출의 **차원·severity 프레이밍을 표준화**. 동일모델(Claude) 서브에이전트 리뷰는 codex 보조로만(상관오류 주의).

## 경계
advisory. 호출 = `harness-code-quality-review`(명시). 직접 수정 0(권고만).
