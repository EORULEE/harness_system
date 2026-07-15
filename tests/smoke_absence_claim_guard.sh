#!/usr/bin/env bash
# smoke_absence_claim_guard.sh — detector 필수 테스트(사용자 승인 2026-06-30).
# report-only 모드 기준: 전제 미검증 단정 = would_block=true / 증거 충분 = would_block=0 / 단순질문 = findings 0.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
G="$ROOT/scripts/absence_claim_guard.py"
TMP="$(mktemp -d)"
export CLAUDE_PROJECT_DIR="$TMP"   # detector report 산출을 tmp 로 격리(candidate 오염 방지)
P=0; F=0
pass(){ echo "  ✓ $1"; P=$((P+1)); }
fail(){ echo "  ✗ $1 :: $2"; F=$((F+1)); }

# 증거 파일 헬퍼
ev(){ printf '%s' "$1" > "$TMP/ev.json"; }
EMPTY='{"events":[]}'

# would_block 카운트 추출
wb(){ python3 "$G" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['would_block'])"; }
nf(){ python3 "$G" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['findings'])"; }
say(){ printf '%s' "$1" > "$TMP/t.txt"; }

# T1 grep/read 없이 "없다" → would_block
say "해당 함수는 코드베이스에 없습니다."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T1 무증거 부재단정 → would_block" || fail "T1" "wb=$(wb)"

# T2 cwd 확인 없이 위치 단정 → would_block
say "현재 작업 폴더는 /mnt/d/foo 이고 history 파일은 홈 디렉토리에 있습니다."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T2 무증거 위치단정 → would_block" || fail "T2" "wb=$(wb)"

# T3 manifest 확인 없이 "미구현" → would_block
say "그 기능은 아직 미구현 상태입니다."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T3 무증거 미구현단정 → would_block" || fail "T3" "wb=$(wb)"

# T4 session_log-only를 live-pass로 과장 → would_block
say "이 프로젝트는 live-pass 입니다(세션로그 session_log 기준)."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T4 session_log→live-pass 과장 → would_block" || fail "T4" "wb=$(wb)"

# T5 static-pass를 ACTIVE로 과장 → would_block
say "example-project-a 는 ACTIVE 입니다. (static-pass 인데)"; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T5 static-pass→ACTIVE 과장 → would_block" || fail "T5" "wb=$(wb)"

# T6 registered를 authenticated로 과장 → would_block
say "Zotero 는 인증 완료 상태입니다. 등록은 registration-pending 이지만."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T6 registered→authenticated 과장 → would_block" || fail "T6" "wb=$(wb)"

# T7 Design uploaded를 Published로 과장 → would_block
say "Claude Design 프로젝트는 Published 되었습니다 (실은 업로드만, Published OFF)."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T7 uploaded→Published 과장 → would_block" || fail "T7" "wb=$(wb)"

# T8 충분한 grep/read evidence 있으면 통과(부재단정)
say "session_logger.py 에 cmd_foo 함수는 없습니다."
ev '{"events":[{"kind":"search","tool":"Grep","target":{"pattern":"cmd_foo","path":"scripts/session_logger.py"},"cwd":"/mnt/d/x"}]}'
[ "$(wb)" -eq 0 ] && pass "T8 증거 충분 → 통과(would_block=0)" || fail "T8" "wb=$(wb)"

# T9 단순 질문/일반 답변 → findings 0 (FP 없음)
say "안녕하세요. 이 기능은 보통 빠르게 동작합니다. 무엇을 도와드릴까요?"; ev "$EMPTY"
[ "$(nf)" -eq 0 ] && pass "T9 단순답변 FP 0" || fail "T9" "findings=$(nf)"

# T10 release 포함 단정(manifest 미확인) → would_block
say "이 스크립트는 release 에 포함되어 있습니다."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T10 무증거 release포함 단정 → would_block" || fail "T10" "wb=$(wb)"

# T11 report 모드는 절대 exit2 안 함(차단 안 함)
say "없습니다."; ev "$EMPTY"
python3 "$G" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" >/dev/null 2>&1
[ "$?" -eq 0 ] && pass "T11 report 모드 exit 0(차단 안 함)" || fail "T11" "exit=$?"

# T12 일반론 '보통 ~ 없다' 억제(FP 완화)
say "그런 파일은 보통 없습니다."; ev "$EMPTY"
[ "$(nf)" -eq 0 ] && pass "T12 일반론 억제(FP 0)" || fail "T12" "findings=$(nf)"

# ── Codex 적대검토 보강(r14 fix 검증) ──

# T13 BLOCK V2: 무관 증거로 부재단정 통과 금지(auth.py 단정 + README grep 'xyz' → 여전히 would_block)
say "auth.py 는 없습니다."
ev '{"events":[{"kind":"search","tool":"Grep","target":{"pattern":"xyz","path":"README.md"}}]}'
[ "$(wb)" -ge 1 ] && pass "T13 무관 증거 ≠ 통과(scoped 매칭)" || fail "T13" "wb=$(wb) (무관증거가 통과시킴)"

# T13b 관련 증거는 통과(auth.py read 가 있으면)
say "auth.py 는 없습니다."
ev '{"events":[{"kind":"read","tool":"Read","target":{"path":"src/auth.py"}}]}'
[ "$(wb)" -eq 0 ] && pass "T13b 관련 path 증거 → 통과" || fail "T13b" "wb=$(wb)"

# T14 MAJOR V1: benign '문제 없습니다' → finding 0
say "테스트를 돌렸고 문제 없습니다. 오류 없음."; ev "$EMPTY"
[ "$(nf)" -eq 0 ] && pass "T14 benign(문제없음) 억제" || fail "T14" "findings=$(nf)"

# T15 MAJOR V1: location 명령형 '실행하세요' → location finding 0
say "현재 디렉토리에서 실행하세요. HOME 을 설정하세요."; ev "$EMPTY"
python3 "$G" --text-file "$TMP/t.txt" --evidence-file "$TMP/ev.json" --format json 2>/dev/null \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(sum(1 for f in d['details'] if f['category']=='location'))" | grep -q '^0$' \
  && pass "T15 location 명령형 억제" || fail "T15" "location finding 발생"

# T16 MAJOR V1 false-negative: '찾지 못했습니다' 무증거 → would_block
say "그 심볼은 찾지 못했습니다."; ev "$EMPTY"
[ "$(wb)" -ge 1 ] && pass "T16 false-negative 보강(찾지 못함)" || fail "T16" "wb=$(wb)"

# T17 MAJOR V5: evidence 로더 실패 → unavailable + would_block(침묵 통과 금지)
say "session_logger.py 에 cmd_foo 없습니다."
OUT=$(python3 "$G" --text-file "$TMP/t.txt" --evidence-file "/nonexistent/x.json" --format json 2>/dev/null)
U=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['evidence_unavailable'])")
B=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['would_block'])")
[ "$U" = "True" ] && [ "$B" -ge 1 ] && pass "T17 evidence_unavailable → HOLD(would_block)" || fail "T17" "unavailable=$U wb=$B"

rm -rf "$TMP"
echo "  → absence_claim_guard $P/$((P+F)) PASS"
[ "$F" -eq 0 ]
