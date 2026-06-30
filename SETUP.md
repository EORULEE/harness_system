# 처음 설치 — 전체 설정 가이드 (First Setup)

이 하네스를 받은 직후 **한 번만** 거치면 되는 설정. **코어는 설정 0으로 바로 작동**하고, 아래 선택 통합은 본인 계정/폴더로 추가합니다(없으면 Claude로 대체되거나 생략).

> Claude Code 첫 세션을 열면 이 순서를 **자동으로 안내·질문**합니다(온보딩). 직접 보려면 이 문서.

## 0. 요구사항
- **Claude Code**(호스트) · **python3 3.9+** · **node 18+**

## 1. 받기 & 설치 확인 (필수)
```bash
git clone harness-public-core-v1.bundle harness
cd harness
bash selftest.sh        # 요구사항·코어 smoke(11)·스킬(45)·훅·도구·계정/MCP 상태 한 번에
```

## 2. 코어 — 설정 0으로 바로 작동
응답규율(`CLAUDE.md`) · dev-discipline(systematic-debugging·verification·**code-claim 게이트**·TDD) · loop · deep-interview · ralph · system-truth-probe · adaptive-verification. **추가 설정 불필요.**

## 3. 선택 통합 — 본인 것으로 설정 (한 번)
### 3a. LLM Wiki — `WIKI.md`
```bash
export WIKI_ROOT=~/notes/wiki && mkdir -p "$WIKI_ROOT"   # 본인 노트 폴더
# 결정적 도구(lint/health/graph)는 계정 0으로 작동. ingest/query 는 Claude 가 수행.
```
### 3b. Gemini (글쓰기 백엔드) — `ACCOUNTS.md §2`
Google AI Studio 키 → `~/.claude/gemini.env` 에 `GEMINI_API_KEY=...` (없으면 글쓰기는 Claude로 작성).
### 3c. Codex + ChatGPT (코드 적대검토) — `ACCOUNTS.md §3`
Codex Claude Code 플러그인 설치 + ChatGPT 인증 (없으면 Claude 리뷰로 대체).
### 3d. 연구·코드 MCP — `ACCOUNTS.md §4`
**본인 계정/키로** `semantic-scholar`·`paper-search`·`github`·`serena` 추가(일부 키 필요; 생략 가능).
```bash
bash scripts/setup_mcp.sh      # 본인 키로 자동 등록(이미 있으면 skip). 키는 저장 안 함.
claude mcp list                # 각 서버 '✔ Connected' 확인
```

## 4. 마무리
```bash
touch .claude/.onboarded     # 설정/결정 끝나면 → 시작 안내 종료
```

## 작동 / 미작동 한눈에
| 기능 | 필요한 것 | 설정 안 하면 |
|---|---|---|
| 규율·dev-discipline·loop·deep-interview·ralph·adaptive | — | ✅ 그대로 작동 |
| LLM Wiki — lint·health·graph | `WIKI_ROOT`(폴더만) | ✅ 작동 |
| LLM Wiki — ingest·query | Claude | ✅ 작동(에이전트) |
| 글쓰기 — Gemini 백엔드 | Gemini 키 | Claude로 작성(대체) |
| 코드 적대검토 | Codex+ChatGPT | Claude 리뷰(대체) |
| 논문/코드 조사 | MCP 서버 | 생략 |

**요약**: clone → `bash selftest.sh` → (원하는 통합만 3 에서 설정) → `touch .claude/.onboarded`. 코어는 즉시, 나머지는 본인 계정으로.
