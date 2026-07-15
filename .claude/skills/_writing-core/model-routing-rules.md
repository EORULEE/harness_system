# model-routing-rules.md — 모델 라우팅·폴백 규칙

> ⚠️ **모델명 리터럴 금지 문서**(AC2). 본 문서는 `model-policy.yaml`의 **role 이름과
> `model_refs` 키만** 참조한다. 구체 모델명은 `model-policy.yaml` 한 곳에만 존재한다.

## 1. 라우팅 원칙
- 모든 Writing Suite skill은 모델명을 직접 쓰지 않고 **role**(`primary_writer`,
  `fallback_writer`, `adversarial_reviewer`, `orchestrator`, `structure_protection`)로
  요청한다.
- role → 엔진/모델 해석은 **`model-policy.yaml`**에서 단일하게 이뤄진다.
- skill이 모델을 바꾸고 싶으면 코드가 아니라 `model-policy.yaml`의 `model_refs`를 고친다.

## 2. 작성 경로 (writer)
1. **primary_writer** = `gemini-write` 스킬을 `gemini-writer` 서브에이전트로 위임 호출.
   - 위임 대상이 자체 폴백 체인을 내장한다(아래 §3 백엔드 체인 참조).
2. primary 실패 시 백엔드가 자동으로 **fallback_writer**로 넘어간다.
3. 두 writer 모두 불가하면 **graceful_terminal**(`model-policy.yaml`) 발동.

## 3. 백엔드 폴백 체인 (정적 대조 대상, AC17)
`model-policy.yaml`의 `backend_chain` 블록이 `gemini-write/write.py`의 실제 런타임
폴백과 **일치해야** 한다. smoke(Phase C)는 둘을 **정적 대조**한다(실제 호출 없음, AC20).
- 체인 단계: primary → (한도초과) flash 폴백 → (백오프) → (Gemini 완전실패) ChatGPT 폴백.
- ChatGPT 호출 경로: codex 플러그인 app-server 우선 → bare codex exec.
- ⚠️ **조용한 폴백 주의(2026-06-10)**: write.py 폴백은 *조용**해서 출력만으론 실제 사용 모델을 모름. **특정 모델이 실제로 쓰였는지 보장**해야 할 때(예: 사용자가 3.1-pro 명시)는 **검증 호출 `~/.claude/lib/gemini_call.py --model <m>`** 사용 — 응답 `modelVersion` 검증, 불일치 시 조용한 대체 없이 exit 2 + `[VERIFIED] model/tokens/tier` 실측. (cap 상향됨: gemini-3.1-pro-preview tier=standard 접근 가능, 2026-06-10 확인.) 참조 [[reference-gemini-key-usage]].

## 4. unavailable 판정 (누가)
- **런타임 판정**은 백엔드(write.py) 책임 — 429/503/예외로 감지(본 suite는 백엔드 미수정).
- **정적 판정**은 본 suite 책임 — 환경에서 자격/도구 존재만 확인:
  - Gemini: `~/.claude/gemini.env` 키 존재 여부.
  - ChatGPT(codex): codex companion 스크립트 발견 여부.
- 둘 다 정적으로 불가 → `graceful_terminal.action`(orchestrator 직접작성 or 사용자 에스컬레이션).

## 5. 적대 검토(adversarial_reviewer)
- 초안 완성 후 `adversarial_reviewer` role로 약점·과장·근거부재를 검토.
- 이 role이 불가한 환경(codex 차단)이면 **orchestrator(Claude)가 자기검토로 대체**하고
  "교차모델 적대검토 미수행(환경 제약)"을 메타에 1줄 명시한다(은폐 금지).

## 6. 금지
- skill 본문·기타 `*-rules.md`에 모델명 리터럴 기입 금지(AC2 grep 0건).
- 백엔드(`write.py`·`gemini-writer.md`) 수정 금지(Constraints) — 라우팅은 위임으로만.
