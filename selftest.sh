#!/usr/bin/env bash
# selftest.sh — 받자마자 전부 점검: 요구사항·코어 smoke·스킬·훅·도구·계정/MCP 상태.
# 코어는 계정 0으로 작동(아래 smoke). 선택 통합은 본인 계정 필요(ACCOUNTS.md).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
echo "═══════════ harness 공개 코어 자가점검 (selftest) ═══════════"

echo ""
echo "[A] 요구사항"
command -v python3 >/dev/null && echo "  ✓ python3 $(python3 --version 2>&1|awk '{print $2}')" || echo "  ✗ python3 없음(필수)"
command -v node >/dev/null && echo "  ✓ node $(node -v)" || echo "  ⚠ node 없음(훅 비활성; 코어 smoke 는 동작)"

echo ""
echo "[B] 코어 smoke (로직 검증 — 계정 불필요)"
P=0; F=0
for s in tests/smoke_*.sh; do
  if bash "$s" >/dev/null 2>&1; then echo "  ✓ $(basename "$s" .sh)"; P=$((P+1)); else echo "  ✗ $(basename "$s" .sh)"; F=$((F+1)); fi
done
echo "  → smoke $P/$((P+F)) PASS"

echo ""
echo "[C] 스킬 인벤토리 (구조 검증)"
ns=$(ls -d .claude/skills/*/ 2>/dev/null | wc -l)
valid=0; for d in .claude/skills/*/; do [ -f "$d/SKILL.md" ] || [ -f "$d/$(basename "$d").md" ] || ls "$d"*.md >/dev/null 2>&1 && valid=$((valid+1)); done
echo "  스킬 $ns 개 · md 보유 $valid"
echo "  (dev-discipline·code-claim·loop·deep-interview·ralph·system-truth-probe·writing·adaptive 등)"

echo ""
echo "[D] 훅 (문법·배선)"
ok=0; bad=0; for h in hooks/*.mjs; do node --check "$h" 2>/dev/null && ok=$((ok+1)) || bad=$((bad+1)); done
wired=$(python3 -c "import json;d=json.load(open('.claude/settings.json'));print(sum(len(g.get('hooks',[])) for v in d['hooks'].values() for g in v))" 2>/dev/null)
echo "  훅 node --check $ok OK / $bad FAIL · settings 배선 $wired 개"

echo ""
echo "[E] 도구 (code-claim lint)"
# lint 이 무근거 코드-동작 주장을 flag(surface)하면 정상. 출력으로 판정(exit code 아님).
_lo=$(printf 'compute_x 는 crop 전체 평균을 계산한다.\n' | python3 scripts/code_claim_lint.py - 2>&1)
echo "$_lo" | grep -q "인용 없는\|건 —" && echo "  ✓ code_claim_lint 동작(무근거 주장 탐지)" || echo "  ✗ lint"

echo ""
echo "[F] 선택 통합 — 계정/MCP 상태 (없어도 코어 작동, 설정=ACCOUNTS.md)"
echo "  Gemini 키:  $([ -f "$HOME/.claude/gemini.env" ] && echo '설정됨' || echo '미설정 → ACCOUNTS.md §2 (글쓰기는 Claude 대체)')"
echo "  Codex:      $(command -v codex >/dev/null 2>&1 && echo '설치됨' || echo '미설치 → ACCOUNTS.md §3 (적대검토는 Claude 대체)')"
echo "  연구 MCP:   미번들 — 본인 계정으로 추가: bash scripts/setup_mcp.sh → ACCOUNTS.md §4 (semantic-scholar·paper-search·github·serena)"

echo ""
echo "═══════════ 요약 ═══════════"
if [ "$F" -eq 0 ] && [ "$bad" -eq 0 ]; then
  echo "✅ 코어 정상 — smoke $P/$((P+F)) · 훅 $ok OK · 스킬 $ns. 바로 사용 가능."
else
  echo "⚠ 일부 실패(smoke F=$F · 훅 bad=$bad) — 환경 차이일 수 있음. 위 ✗ 확인."
fi
echo ""
echo "─────────── 처음이신가요? 이대로만 하면 됩니다 ───────────"
echo " 1. 지금 본 [B] 가 전부 ✓ 면 → 코어는 바로 작동(추가 설정 0)."
echo "    응답규율·dev-discipline·code-claim·loop·deep-interview·ralph·LLM Wiki(로컬)·writing 등."
echo " 2. Claude Code 로 이 폴더에서 첫 세션을 열면 → Claude 가 알아서 설정을 안내·질문합니다."
echo "    (문서를 하나씩 읽을 필요 없음 — Claude 와 대화만.)"
echo " 3. 선택 통합만 본인 것으로(원하는 것만):"
echo "    • LLM Wiki   : export WIKI_ROOT=<노트폴더>           → WIKI.md"
echo "    • 글쓰기(Gemini): ~/.claude/gemini.env 에 키          → ACCOUNTS.md §2"
echo "    • 코드 적대검토 : Codex 플러그인 + ChatGPT           → ACCOUNTS.md §3"
echo "    • 논문/코드 조사: bash scripts/setup_mcp.sh (본인 키)  → ACCOUNTS.md §4"
echo "    없으면? → 그 기능만 Claude 로 대체되거나 생략(코어는 그대로)."
echo " 4. 다 정했으면 → touch .claude/.onboarded  (시작 안내 종료)"
echo "─────────────────────────────────────────────────────────"
echo "전체 첫설치 가이드: SETUP.md  ·  규율: CLAUDE.md"
