# 계정 설정 (선택적 통합) — 본인 계정으로 추가하는 법

이 하네스의 **코어**(응답 규율 · dev-discipline · code-claim 게이트 · loop · deep-interview · ralph · system-truth-probe · LLM Wiki 결정적 도구)는 **Claude Code만으로 바로 작동**합니다. 추가 계정이 필요 없습니다.

아래는 **선택적 통합** — **본인 계정/키로** 설정합니다. 없어도 코어는 동작하며 해당 기능은 Claude로 대체(fallback)됩니다. **이 패키지엔 어떤 키도 들어있지 않습니다.** 키는 전부 *당신* 것을 넣으세요.

> 한 번에 추가: `bash scripts/setup_mcp.sh` (MCP 서버를 본인 키로 자동 등록 — 아래 §4).

## 1. Claude Code (필수 · 이미 보유)
이 하네스의 호스트. 별도 설정 없음.

## 2. Gemini API 키 — Writing Suite 백엔드 (선택)
- 용도: 글쓰기(paper/report/slide-writer)를 Gemini 백엔드로. 없으면 Claude로 작성.
- **본인 키 발급**: <https://aistudio.google.com/apikey> (Google 계정 로그인 → "Create API key").
- **설정**:
  ```bash
  mkdir -p ~/.claude
  echo 'GEMINI_API_KEY=<당신의-키>' >> ~/.claude/gemini.env
  ```
- ⚠️ Gemini 위임 글쓰기 스킬(gemini-write)은 개인 도구라 이 패키지에 미포함 — 원하면 별도 구성.

## 3. Codex + ChatGPT — 코드 적대검토 (선택)
- 용도: 코드 리뷰를 교차모델(ChatGPT)로 적대검토. 없으면 Claude 리뷰로 대체.
- **본인 계정으로 설정**:
  1. Claude Code에서 Codex 플러그인 설치: `/plugin` → `codex` 검색·설치.
  2. **본인 ChatGPT 계정**으로 인증(플러그인 안내에 따라 로그인).
  3. (모델 차단 회피) `~/.codex/config.toml` 에 `model = "gpt-5.5"` 권장.

## 4. 연구·코드 MCP 서버 (선택) — 본인 계정으로 추가
용도: 논문 조사(semantic-scholar · paper-search) · 코드(github) · 코드 심볼 탐색(serena).

### 가장 쉬운 방법 — 도우미 스크립트
```bash
bash scripts/setup_mcp.sh          # uv 설치 확인 → 각 서버를 claude mcp add 로 등록(이미 있으면 skip)
```
스크립트는 **키를 패키지에 저장하지 않습니다**. 키가 필요한 서버는 본인 환경변수(예: `S2_API_KEY`)를 읽거나 안내만 합니다.

### 수동으로 하나씩 (본인이 직접)
> CLI 버전에 따라 플래그가 다를 수 있으니 `claude mcp add --help` 로 확인하세요. 아래는 stdio/HTTP 표준형.

```bash
# 논문 조사 — Semantic Scholar (S2). 키 없이도 동작(있으면 rate-limit↑).
#   본인 키(선택): https://www.semanticscholar.org/product/api → 발급 후 export S2_API_KEY=<당신-키>
claude mcp add semantic-scholar -- uvx s2-mcp-server

# 논문 조사 — 다중 DB(arXiv·PubMed·OpenAlex·Crossref 등). 키 불필요.
claude mcp add paper-search -- uvx --from paper-search-mcp python -m paper_search_mcp.server

# 코드 심볼 탐색 — serena (uv 필요). 키 불필요.
#   serena 설치: uv tool install --from git+https://github.com/oraios/serena serena
claude mcp add serena -- serena start-mcp-server --context claude-code

# GitHub — 본인 GitHub 계정 인증 필요(HTTP transport).
#   추가 후 Claude Code 안내에 따라 본인 GitHub 로 인증/토큰 연결.
claude mcp add --transport http github https://api.githubcopilot.com/mcp/
```
- `uvx`/`uv` 가 없으면 먼저 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh` (또는 setup_mcp.sh 가 안내).
- 등록 확인: `claude mcp list` (각 서버 옆 `✔ Connected` 확인).
- ⚠️ 개인 도구 MCP(zotero·claude_design 등)는 본인 라이브러리·계정에 묶여 이 패키지에 미포함. 필요하면 같은 방식으로 본인 것을 추가하세요.

## 설정/결정을 마치면
선택 통합 설정을 마쳤거나 코어만 쓸 거면, 시작 안내가 더 안 뜨도록 마커를 만드세요:
```bash
touch .claude/.onboarded
```
