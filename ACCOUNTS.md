# 계정 설정 (선택적 통합)

이 하네스의 **코어**(응답 규율 · dev-discipline · code-claim 게이트 · loop · deep-interview · ralph · system-truth-probe)는 **Claude Code만으로 바로 작동**합니다. 추가 계정이 필요 없습니다.

아래는 **선택적 통합** — 본인 계정/키로 설정. 없어도 코어는 동작하며, 해당 기능은 Claude로 대체(fallback)됩니다. **이 패키지엔 어떤 키도 들어있지 않습니다.**

## 1. Claude Code (필수 · 이미 보유)
이 하네스의 호스트. 별도 설정 없음.

## 2. Gemini API 키 — Writing Suite 백엔드 (선택)
- 용도: 글쓰기(paper/report/slide-writer)를 Gemini 백엔드로. 없으면 Claude로 작성.
- 설정: Google AI Studio에서 Gemini API 키 발급 → `~/.claude/gemini.env` 에 `GEMINI_API_KEY=<your-key>`.
- ⚠️ Gemini 위임 글쓰기 스킬(gemini-write)은 개인 도구라 이 패키지에 미포함 — 원하면 별도로 구성.

## 3. Codex + ChatGPT — 코드 적대검토 (선택)
- 용도: 코드 리뷰를 교차모델(ChatGPT)로 적대검토. 없으면 Claude 리뷰로 대체.
- 설정: Codex Claude Code 플러그인 설치 + ChatGPT 계정 인증.

## 4. 연구·코드 MCP 서버 (선택)
- 용도: 논문 조사(semantic-scholar · paper-search) · 코드(github) · 심볼(serena).
- 설정: Claude Code MCP로 각 서버 추가(일부는 API 키 필요).

## 설정/결정을 마치면
선택 통합 설정을 마쳤거나 코어만 쓸 거면, 시작 안내가 더 안 뜨도록 마커를 만드세요:
```bash
touch .claude/.onboarded
```
