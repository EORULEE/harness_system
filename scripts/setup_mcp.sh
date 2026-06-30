#!/usr/bin/env bash
# setup_mcp.sh — 연구·코드 MCP 서버를 *본인 계정/키*로 Claude Code 에 등록한다.
# 이 스크립트는 키를 저장하지 않는다. 키가 필요한 서버는 본인 환경변수를 읽거나 안내만 한다.
# 멱등: 이미 등록된 서버는 건너뛴다(claude mcp list 기준).
set -uo pipefail

echo "═══════════ MCP 서버 설정 (본인 계정/키) ═══════════"

# --- 전제 도구 확인 ---
if ! command -v claude >/dev/null 2>&1; then
  echo "✗ 'claude' CLI 가 없습니다. Claude Code 를 먼저 설치하세요."; exit 1
fi
if ! command -v uvx >/dev/null 2>&1; then
  echo "⚠ 'uv/uvx' 가 없습니다(semantic-scholar·paper-search·serena 에 필요)."
  echo "  설치: curl -LsSf https://astral.sh/uv/install.sh | sh   (설치 후 셸 재시작)"
  echo "  지금은 uv 불필요 서버만 진행하거나, 설치 후 다시 실행하세요."
fi

# 이미 등록된 서버 목록(멱등 처리용)
EXISTING="$(claude mcp list 2>/dev/null || true)"
already() { printf '%s\n' "$EXISTING" | grep -q "^$1[: ]"; }

add() {  # add <name> <transport: stdio|http> <cmd-or-url...>
  local name="$1" kind="$2"; shift 2
  if already "$name"; then echo "  • $name — 이미 등록됨(skip)"; return; fi
  if [ "$kind" = http ]; then
    if claude mcp add --transport http "$name" "$1" 2>/dev/null; then
      echo "  ✓ $name 등록(HTTP) — 인증은 Claude Code 안내에 따라 본인 계정으로"
    else echo "  ✗ $name 등록 실패 — 'claude mcp add --help' 로 플래그 확인"; fi
  else
    if claude mcp add "$name" -- "$@" 2>/dev/null; then
      echo "  ✓ $name 등록"
    else echo "  ✗ $name 등록 실패 — 'claude mcp add --help' 로 플래그 확인"; fi
  fi
}

echo ""
echo "[1] 논문 조사"
# Semantic Scholar — 키 없이 동작, S2_API_KEY 있으면 rate-limit 상향(본인 키)
if [ -n "${S2_API_KEY:-}" ]; then echo "  (S2_API_KEY 감지 — 본인 키 사용)"; else
  echo "  (S2_API_KEY 없음 — 무료 등급으로 동작. 키 발급: https://www.semanticscholar.org/product/api)"; fi
command -v uvx >/dev/null 2>&1 && add semantic-scholar stdio uvx s2-mcp-server || echo "  • semantic-scholar — uv 필요(skip)"
command -v uvx >/dev/null 2>&1 && add paper-search stdio uvx --from paper-search-mcp python -m paper_search_mcp.server || echo "  • paper-search — uv 필요(skip)"

echo ""
echo "[2] 코드 심볼 탐색 — serena"
if command -v serena >/dev/null 2>&1; then
  add serena stdio serena start-mcp-server --context claude-code
else
  echo "  • serena 미설치 — 먼저: uv tool install --from git+https://github.com/oraios/serena serena"
fi

echo ""
echo "[3] GitHub (본인 GitHub 계정 인증 필요)"
add github http https://api.githubcopilot.com/mcp/

echo ""
echo "═══════════ 확인 ═══════════"
echo "  claude mcp list   ← 각 서버 옆 '✔ Connected' 확인"
echo "  키가 필요한 서버(GitHub 등)는 Claude Code 안내에 따라 *본인 계정*으로 인증하세요."
echo "  이 패키지에 키는 저장되지 않습니다."
