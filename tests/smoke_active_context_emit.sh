#!/usr/bin/env bash
# smoke_active_context_emit.sh — Memory Continuity v2: ACTIVE_CONTEXT emit 주입 + freshness gate 회귀.
#
# 대상: memory_sync.py `session-hook --emit-stdout` 의 _emit_active_context_core().
#  - 핵심 상태(status·objective·completed·next_action·locked_facts·checkpoint) bundle 앞 1회 주입.
#  - completed/locked_facts = 원문 verbatim(요약·추론 없음·각 최대 10·중복 제거).
#  - freshness gate: emit 직전 source checkpoint 와 sha256(없으면 mtime) 비교 →
#      stale 이면 상태필드 미주입, ⚠️ STALE 경고·재처리 안내만(오래된 상태 현재 사실化 방지).
# 파싱 = yaml.safe_load(기존 helper). secret 마스킹 = update_active_context(write 시).
# 격리: temp HOME + temp project. 실 memory/checkpoint/settings/runtime 무접촉. LLM/네트워크 없음. 결정적.
set -u
SCRIPTS="$(cd "$(dirname "$0")/../scripts" && pwd)"
MS="$SCRIPTS/memory_sync.py"
PASS=0; FAIL=0
ok(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
ng(){ echo "  ❌ $1"; FAIL=$((FAIL+1)); }
sanitize(){ X="$1" python3 -c "import re,os;print(re.sub(r'[^a-zA-Z0-9]','-',os.environ['X']))"; }
# new_proj: temp HOME + proj 디렉토리 + memory root. echo "H|P|PID|MEM"
new_proj(){ local H P PID MEM; H=$(mktemp -d); P="$H/proj"; mkdir -p "$P"; PID=$(sanitize "$P")
  MEM="$H/.claude/projects/$PID/memory"; mkdir -p "$MEM"; echo "$H|$P|$PID|$MEM"; }
# Windows python expanduser("~")=USERPROFILE → emit 에 둘 다 설정(Git-Bash 크로스환경).
emit(){ ( cd "$2" && HOME="$1" USERPROFILE="$1" CLAUDE_PROJECT_DIR="$2" python3 "$MS" session-hook --emit-stdout 2>/dev/null ); }
# write_ac MEM PROJID CPSHA UPDATED  <stdin: __PROJID__/__CPSHA__/__UPDATED__ 치환>
write_ac(){ sed -e "s#__PROJID__#$2#g" -e "s#__CPSHA__#$3#g" -e "s#__UPDATED__#$4#g" > "$1/_active_context.md"; }
sha_of(){ sha256sum "$1" | cut -d' ' -f1; }
AC_HDR="ACTIVE CONTEXT (Memory Continuity v2"      # 이모지 제외 ASCII (MSYS grep) — 항상 grep -F
BUN_HDR="Memory Context Bundle"
STALE_M="STALE ACTIVE CONTEXT"

echo "== F1: checkpoint hash 일치 → 정상 emit (4필드·verbatim·dedup·특수문자) =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'checkpoint body v1\n' > "$MEM/project_session_checkpoint.md"
CPSHA=$(sha_of "$MEM/project_session_checkpoint.md")
write_ac "$MEM" "$PID" "$CPSHA" "2026-06-22T12:00:00" <<'AC'
---
schema_version: "active_context/v2"
project_id: "__PROJID__"
source_event: "session_end"
status: "completed"
current_objective: "F1-OBJ 한글:콜론 verbatim"
completed:
  - "F1-완료-한글-항목 (35/35 PASS)"
  - "DUP-ITEM"
  - "DUP-ITEM"
next_action: "F1-NEXT"
locked_facts:
  - "F1-고정 수치 9/9 · 특수문자"
source_checkpoint: "project_session_checkpoint.md"
source_checkpoint_sha256: "__CPSHA__"
updated_at: "__UPDATED__"
latest_checkpoint: "cp @ x"
confidence: "high"
needs_review: false
---
AC
OUT="$(emit "$H" "$P")"
printf '%s\n' "$OUT" | grep -qF "$AC_HDR" && ok "ACTIVE CONTEXT 헤더" || ng "헤더 누락"
printf '%s\n' "$OUT" | grep -qF "$STALE_M" && ng "정상인데 STALE" || ok "STALE 아님(정상)"
printf '%s\n' "$OUT" | grep -qF "F1-OBJ 한글:콜론 verbatim" && ok "objective verbatim(콜론·한글)" || ng "objective 누락"
printf '%s\n' "$OUT" | grep -qF "F1-완료-한글-항목 (35/35 PASS)" && ok "completed verbatim" || ng "completed 누락"
printf '%s\n' "$OUT" | grep -qF "F1-NEXT" && ok "next_action" || ng "next_action 누락"
printf '%s\n' "$OUT" | grep -qF "F1-고정 수치 9/9 · 특수문자" && ok "locked_facts verbatim" || ng "locked_facts 누락"
dc=$(printf '%s\n' "$OUT" | grep -cF "DUP-ITEM"); [ "$dc" -eq 1 ] && ok "completed 중복 제거(1)" || ng "중복 ${dc}"
n4=0; for pat in "현재 목표:" "- 완료:" "다음 행동:" "고정 사실(locked):"; do printf '%s\n' "$OUT" | grep -qF -- "$pat" && n4=$((n4+1)); done
[ "$n4" -eq 4 ] && ok "4핵심필드 포함" || ng "핵심필드 $n4/4"
printf '%s\n' "$OUT" | grep -qF -- "- ⚠️ needs_review" && ng "검증됐는데 needs_review" || ok "needs_review 없음(hash 검증됨)"

echo "== F2: checkpoint hash 불일치 → STALE 경고, 4상태필드 미주입 (bundle 정상) =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'checkpoint body v2-CHANGED\n' > "$MEM/project_session_checkpoint.md"
write_ac "$MEM" "$PID" "0000000000000000000000000000000000000000000000000000000000000000" "2026-06-22T12:00:00" <<'AC'
---
project_id: "__PROJID__"
status: "completed"
current_objective: "F2-STALEOBJ-SHOULDNOTAPPEAR"
completed:
  - "F2-STALEDONE-SHOULDNOTAPPEAR"
next_action: "F2-STALENEXT-SHOULDNOTAPPEAR"
locked_facts:
  - "F2-STALELF-SHOULDNOTAPPEAR"
source_checkpoint: "project_session_checkpoint.md"
source_checkpoint_sha256: "__CPSHA__"
updated_at: "__UPDATED__"
---
AC
OUT2="$(emit "$H" "$P")"
printf '%s\n' "$OUT2" | grep -qF "$STALE_M" && ok "STALE 경고 표시" || ng "STALE 경고 누락"
printf '%s\n' "$OUT2" | grep -qF "SHOULDNOTAPPEAR" && ng "stale 상태필드 주입됨" || ok "4상태필드 미주입"
printf '%s\n' "$OUT2" | grep -qF "project_session_checkpoint.md" && ok "checkpoint 경로 표시" || ng "checkpoint 경로 누락"
printf '%s\n' "$OUT2" | grep -qF "$BUN_HDR" && ok "bundle 정상(회귀 없음)" || ng "bundle 누락"

echo "== F3: hash 없음 + checkpoint mtime 더 최신 → STALE =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'cp newer\n' > "$MEM/project_session_checkpoint.md"
touch -d "2026-06-22 11:00:00" "$MEM/project_session_checkpoint.md"   # updated_at(10:00) 보다 최신
write_ac "$MEM" "$PID" "" "2026-06-22T10:00:00" <<'AC'
---
project_id: "__PROJID__"
status: "completed"
current_objective: "F3-OBJ-SHOULDNOTAPPEAR"
next_action: "F3-NEXT-SHOULDNOTAPPEAR"
source_checkpoint: "project_session_checkpoint.md"
source_checkpoint_sha256: "__CPSHA__"
updated_at: "__UPDATED__"
---
AC
OUT3="$(emit "$H" "$P")"
printf '%s\n' "$OUT3" | grep -qF "$STALE_M" && ok "mtime 최신 → STALE" || ng "STALE 미판정"
printf '%s\n' "$OUT3" | grep -qF "SHOULDNOTAPPEAR" && ng "stale 필드 주입" || ok "상태필드 미주입"

echo "== F4: hash 없음 + checkpoint mtime 더 오래됨 → 정상 emit =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'cp older\n' > "$MEM/project_session_checkpoint.md"
touch -d "2026-06-22 10:00:00" "$MEM/project_session_checkpoint.md"   # updated_at(12:00) 보다 과거
write_ac "$MEM" "$PID" "" "2026-06-22T12:00:00" <<'AC'
---
project_id: "__PROJID__"
status: "completed"
current_objective: "F4-OBJ-FRESH"
next_action: "F4-NEXT"
source_checkpoint: "project_session_checkpoint.md"
source_checkpoint_sha256: "__CPSHA__"
updated_at: "__UPDATED__"
---
AC
OUT4="$(emit "$H" "$P")"
printf '%s\n' "$OUT4" | grep -qF "$STALE_M" && ng "최신인데 STALE" || ok "STALE 아님(정상)"
printf '%s\n' "$OUT4" | grep -qF "F4-OBJ-FRESH" && ok "objective 정상 주입" || ng "objective 누락"

echo "== F5: project_id 불일치 → 미주입 (bundle 정상) =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'cp\n' > "$MEM/project_session_checkpoint.md"
write_ac "$MEM" "WRONG-PROJECT-ID" "x" "2026-06-22T12:00:00" <<'AC'
---
project_id: "__PROJID__"
status: "completed"
current_objective: "F5-SHOULDNOTAPPEAR"
source_checkpoint: "project_session_checkpoint.md"
---
AC
OUT5="$(emit "$H" "$P")"
printf '%s\n' "$OUT5" | grep -qF "SHOULDNOTAPPEAR" && ng "불일치인데 주입" || ok "project_id 불일치 미주입"
printf '%s\n' "$OUT5" | grep -qF "$AC_HDR" && ng "헤더 출력됨" || ok "ACTIVE CONTEXT 헤더 없음"
printf '%s\n' "$OUT5" | grep -qF "$BUN_HDR" && ok "bundle 정상" || ng "bundle 누락"

echo "== F6: checkpoint 없음 → needs_review(검증불가), 날조 없음 (STALE 단정 아님) =="
IFS='|' read -r H P PID MEM < <(new_proj)   # checkpoint 미생성
write_ac "$MEM" "$PID" "" "2026-06-22T12:00:00" <<'AC'
---
project_id: "__PROJID__"
status: "completed"
current_objective: "F6-OBJ"
next_action: "F6-NEXT"
source_checkpoint: "project_session_checkpoint.md"
source_checkpoint_sha256: "__CPSHA__"
updated_at: "__UPDATED__"
---
AC
OUT6="$(emit "$H" "$P")"
printf '%s\n' "$OUT6" | grep -qF "$STALE_M" && ng "검증불가인데 STALE 단정" || ok "STALE 단정 안 함"
printf '%s\n' "$OUT6" | grep -qF -- "- ⚠️ needs_review" && ok "needs_review 표시(검증 불가)" || ng "needs_review 누락"
printf '%s\n' "$OUT6" | grep -qF "F6-OBJ" && ok "저장된 필드 표시(날조 없음)" || ng "필드 누락"

echo "== F7: MEMORY/KB bundle 회귀 (부재/손상 시에도 bundle 정상·SessionStart 계속) =="
IFS='|' read -r H P PID MEM < <(new_proj)   # _active_context.md 없음
OUT7a="$(emit "$H" "$P")"
printf '%s\n' "$OUT7a" | grep -qF "$BUN_HDR" && ok "부재 시 bundle 정상" || ng "부재 bundle 누락"
printf '%s\n' "$OUT7a" | grep -qF "$AC_HDR" && ng "부재인데 ACTIVE CONTEXT" || ok "부재 시 ACTIVE CONTEXT 없음"
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'broken: [[[ : :\nproject_id\n' > "$MEM/_active_context.md"   # 손상 frontmatter
OUT7b="$(emit "$H" "$P")"
printf '%s\n' "$OUT7b" | grep -qF "$BUN_HDR" && ok "손상 시 bundle 정상(예외→무출력 통과)" || ng "손상 bundle 깨짐"

echo "== F8: secret residual 0 (update_active_context 마스킹 → fresh emit 보존) =="
IFS='|' read -r H P PID MEM < <(new_proj)
printf 'cp for secret\n' > "$MEM/project_session_checkpoint.md"
CPSHA=$(sha_of "$MEM/project_session_checkpoint.md")
python3 - "$MEM" "$SCRIPTS" "$PID" "$CPSHA" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
from update_active_context import write_active_context
write_active_context(sys.argv[1], {
  "project_id": sys.argv[3], "status": "completed",
  "current_objective": "obj AIzaFAKETESTKEYfaketestkey0123456789 key",
  "completed": ["leak sk-FAKETESTKEYfaketestkey0123456789abcd"],
  "next_action": "n", "locked_facts": ["ghp_FAKETESTKEYfaketestkey0123456789abcd"],
  "source_checkpoint": "project_session_checkpoint.md",
  "source_checkpoint_sha256": sys.argv[4],
})
PY
OUT8="$(emit "$H" "$P")"
resid=$(printf '%s\n' "$OUT8" | SCR="$SCRIPTS" python3 -c "import sys,os;sys.path.insert(0,os.environ['SCR']);from secret_masking import residual_count;print(residual_count(sys.stdin.read()))" 2>/dev/null)
[ "${resid:-x}" = "0" ] && ok "emit secret residual=0" || ng "residual=${resid}"
printf '%s\n' "$OUT8" | grep -qE "AIzaFAKE[0-9A-Za-z_-]{20,}|sk-FAKE[A-Za-z0-9]{20,}|ghp_FAKE[A-Za-z0-9]{20,}" && ng "raw 가짜키 노출" || ok "raw secret 패턴 없음"

echo
echo "==== ACTIVE_CONTEXT emit+freshness smoke 결과: PASS=$PASS  FAIL=$FAIL ===="
[ "$FAIL" -eq 0 ] || exit 1
