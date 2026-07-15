#!/usr/bin/env bash
# vgate-node.sh <mjs-basename> — node >=18 해석(nvm 폴백) 후 exec.
# codex 배포리뷰 F1: server-a /usr/bin/node=v12(EOL, node: prefix 미지원)가 걸리면
# hook 이 조용히 죽어 "hard 라고 믿지만 미작동" 상태가 됨 → 버전 검증 + nvm 폴백.
# F2: 해석 실패는 침묵하지 않고 vgate-errors.log 기록(fail-open 이되 관측 가능).
D="$(cd "$(dirname "$0")" && pwd)"
PROJ="${CLAUDE_PROJECT_DIR:-$(dirname "$D")}"
LOG="$PROJ/.claude/runtime/vgate/vgate-errors.log"
pick=""
NB="$(command -v node 2>/dev/null)"
if [ -n "$NB" ]; then
  V="$("$NB" -p 'parseInt(process.versions.node)' 2>/dev/null)"
  [ "${V:-0}" -ge 18 ] 2>/dev/null && pick="$NB"
fi
if [ -z "$pick" ]; then
  for c in "$HOME"/.nvm/versions/node/v*/bin/node; do
    [ -x "$c" ] || continue
    V="$("$c" -p 'parseInt(process.versions.node)' 2>/dev/null)"
    [ "${V:-0}" -ge 18 ] 2>/dev/null && pick="$c"
  done
fi
if [ -z "$pick" ]; then
  mkdir -p "$(dirname "$LOG")" 2>/dev/null
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) NO_NODE18 $1" >> "$LOG" 2>/dev/null
  exit 0
fi
exec "$pick" "$D/$1"
