#!/usr/bin/env bash
# Serena read-only smoke — 서버가 실제로 노출하는 도구셋에 editing/shell이 없는지 검증.
# (serena tools list는 레지스트리 전체라 부적합 — 서버 기동 로그가 권위)
set -uo pipefail
P=0; F=0
ok(){ echo "  PASS $1"; P=$((P+1)); }
no(){ echo "  FAIL $1"; F=$((F+1)); }
AG="$(command -v serena || echo "$HOME/.local/bin/serena")"
if ! [ -x "$AG" ] && ! command -v serena >/dev/null 2>&1; then
  echo "  SKIP serena 미설치 — 하네스는 serena 없이도 동작(필수 아님)"; exit 0
fi

echo "== 서버 기동 → 실제 노출 도구 캡처 =="
LOG="$(timeout 15 "$AG" start-mcp-server --context claude-code 2>&1 | grep -E "Exposed tools \(|Number of exposed" | tail -2)"
echo "  $LOG" | head -2
EXP="$(echo "$LOG" | grep -oE "\[[^]]*\]" | tail -1)"
[ -n "$EXP" ] && ok "노출 도구 캡처됨" || { no "노출 도구 로그 못 잡음"; exit 1; }

echo "== read-only 강제: editing/shell 도구 0건 노출 =="
BAD=0
for t in execute_shell_command create_text_file replace_content replace_symbol_body \
         replace_lines insert_at_line insert_after_symbol insert_before_symbol delete_lines \
         rename_symbol safe_delete_symbol write_memory edit_memory delete_memory rename_memory; do
  echo "$EXP" | grep -q "'$t'" && { no "editing 노출: $t"; BAD=1; }
done
[ "$BAD" -eq 0 ] && ok "editing/shell 노출 0 (read-only 강제됨)"

echo "== retrieval 핵심 도구는 노출 =="
echo "$EXP" | grep -q "find_referencing_symbols" && ok "find_referencing_symbols 노출(cross-file 참조)" || no "참조 도구 누락"
echo "$EXP" | grep -q "find_symbol" && ok "find_symbol 노출" || no "find_symbol 누락"

echo "== 설정 무전송/secret =="
grep -qE "api[_-]?key|token|secret" "$HOME/.serena/serena_config.yml" 2>/dev/null && echo "  (config에 key 라인 — 값 확인 필요)" || ok "config secret 라인 0"

echo ""
echo "== 결과: PASS=$P FAIL=$F =="
[ "$F" -eq 0 ] && echo "ALL PASS" || echo "FAILURES=$F"
exit $F
