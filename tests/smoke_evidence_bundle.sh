#!/usr/bin/env bash
# smoke_evidence_bundle.sh — 결론 전 전제 검사: 무증거 전제 → HOLD, 증거 전제 → evidenced.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E="$ROOT/scripts/evidence_bundle.py"
TMP="$(mktemp -d)"; export CLAUDE_PROJECT_DIR="$TMP"   # detector report 격리(candidate 오염 방지)
P=0; F=0
pass(){ echo "  ✓ $1"; P=$((P+1)); }
fail(){ echo "  ✗ $1 :: $2"; F=$((F+1)); }
jq_(){ python3 -c "import json,sys;print(json.load(sys.stdin)$1)"; }

# 무증거 부재단정 → any_hold true
printf '그 함수는 없습니다.' > "$TMP/t.txt"; echo '{"events":[]}' > "$TMP/ev.json"
OUT=$(python3 "$E" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json)
[ "$(echo "$OUT" | jq_ "['any_hold']")" = "True" ] && pass "무증거 전제 → any_hold" || fail "hold" "$OUT"
echo "$OUT" | grep -q "전제 HOLD 있음" && pass "verifier_directive=전제 먼저 처리" || fail "directive" "없음"

# 증거 충분 → evidenced, any_hold false
printf 'session_logger.py 에 cmd_foo 는 없습니다.' > "$TMP/t.txt"
echo '{"events":[{"kind":"search","tool":"Grep","target":{"pattern":"cmd_foo","path":"scripts/session_logger.py"}}]}' > "$TMP/ev.json"
OUT=$(python3 "$E" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json)
[ "$(echo "$OUT" | jq_ "['any_hold']")" = "False" ] && pass "증거 전제 → evidenced(any_hold False)" || fail "ev" "$OUT"
echo "$OUT" | grep -q "결론 검토 진행 가능" && pass "directive=결론 진행 가능" || fail "directive2" "없음"

# 단정 없는 일반 답변 → premise 0
printf '안녕하세요 도와드리겠습니다.' > "$TMP/t.txt"; echo '{"events":[]}' > "$TMP/ev.json"
OUT=$(python3 "$E" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json)
[ "$(echo "$OUT" | jq_ "['premise_count']")" = "0" ] && pass "단정없음 → 전제 0(FP 0)" || fail "fp" "$OUT"

# G 스펙 명명필드 존재 + 의미
printf 'session_logger.py 에 cmd_foo 는 없습니다.' > "$TMP/t.txt"
echo '{"events":[{"kind":"search","tool":"Grep","target":{"pattern":"cmd_foo","path":"scripts/session_logger.py"}},{"kind":"read","tool":"Read","target":{"path":"scripts/x.py"}}]}' > "$TMP/ev.json"
OUT=$(python3 "$E" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json)
echo "$OUT" | python3 -c "import json,sys;d=json.load(sys.stdin);assert all(k in d for k in ['required_facts','searched_paths','read_files','grep_queries','unresolved_assumptions']),'missing G fields'" 2>/dev/null \
  && pass "G 명명필드(required_facts/searched_paths/read_files/grep_queries/unresolved_assumptions) 존재" || fail "G필드" "누락"
[ "$(echo "$OUT" | jq_ "['grep_queries']")" = "['cmd_foo']" ] && pass "grep_queries=ledger pattern 반영" || fail "grep_q" "$(echo "$OUT"|jq_ "['grep_queries']")"
[ "$(echo "$OUT" | jq_ "['read_files']")" = "['scripts/x.py']" ] && pass "read_files=ledger read 반영" || fail "read_f" "$(echo "$OUT"|jq_ "['read_files']")"

# 증거 부족 전제 → unresolved_assumptions 에 (precondition HOLD 분리, 결론 dispute 아님)
printf 'auth.py 는 없습니다.' > "$TMP/t.txt"; echo '{"events":[]}' > "$TMP/ev.json"
OUT=$(python3 "$E" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json)
[ "$(echo "$OUT" | jq_ "['unresolved_assumptions']|len(__import__('builtins').__dict__) if False else len(json.loads(sys.stdin) if False else [1])")" ] 2>/dev/null
UA=$(echo "$OUT" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['unresolved_assumptions']))")
[ "$UA" -ge 1 ] && pass "증거부족 → unresolved_assumptions(precondition HOLD 분리)" || fail "unresolved" "len=$UA"

rm -rf "$TMP"
echo "  → evidence_bundle $P/$((P+F)) PASS"
[ "$F" -eq 0 ]
