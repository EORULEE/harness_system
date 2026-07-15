#!/usr/bin/env bash
# smoke_salience_packet.sh — 위치/존재/세션 질문만 짧게 주입, 일반/글쓰기는 무주입, 전체규율 재주입 안 함.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
H="$ROOT/hooks/salience-packet.mjs"
P=0; F=0
pass(){ echo "  ✓ $1"; P=$((P+1)); }
fail(){ echo "  ✗ $1 :: $2"; F=$((F+1)); }
inj(){ echo "{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"$1\"}" | node "$H" 2>/dev/null; }
has(){ inj "$1" | grep -q "salience"; }

# 주입 대상
has "그 파일 어디 있어?" && pass "위치질문 주입" || fail "위치" "무주입"
has "현재 cwd 가 어디야?" && pass "cwd질문 주입" || fail "cwd" "무주입"
has "이 함수 존재해?" && pass "존재질문 주입" || fail "존재" "무주입"
has "지난 세션 찾아줘" && pass "세션찾기 주입" || fail "세션" "무주입"

# 무주입 대상
has "안녕 고마워" && fail "일반대화" "주입됨" || pass "일반대화 무주입"
has "보고서 작성해줘" && fail "글쓰기" "주입됨" || pass "글쓰기 억제(무주입)"
has "이 코드 리팩터해줘" && fail "구현" "주입됨" || pass "구현 억제(무주입)"

# 전체 규율 재주입 안 함(짧아야): 출력 길이 600자 미만
LEN=$(inj "그 파일 어디 있어?" | wc -c)
[ "$LEN" -lt 600 ] && pass "짧은 packet(전체규율 재주입 안 함, ${LEN}자)" || fail "길이" "${LEN}자(과다)"

# 출력 형식 = additionalContext JSON
inj "어디 있어?" | python3 -c "import json,sys;d=json.load(sys.stdin);assert d['hookSpecificOutput']['hookEventName']=='UserPromptSubmit'" 2>/dev/null \
  && pass "additionalContext JSON 형식" || fail "형식" "JSON 불일치"

echo "  → salience_packet $P/$((P+F)) PASS"
[ "$F" -eq 0 ]
