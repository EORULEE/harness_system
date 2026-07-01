#!/usr/bin/env bash
# smoke_ledger_variant_hardening.sh — r12 ledger 변종 정규화 스캐너 검증 (T1~T15).
# ledger_evidence.scan_ledger_evidence 가 5 실변종을 올바르게 분류하는지 + strict rule + name collision.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LE="$ROOT/fleet-dashboard/ledger_evidence.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $1 :: $2"; }

# 공통 topology(alias = sar·volc·insar·dl·data)
mk_topo(){ mkdir -p "$1/.claude"; cat > "$1/.claude/PAIR_TOPOLOGY.yaml" <<'EOF'
schema: pair_topology/v1
project: fx
level: upgrade
pairs:
  - pair_id: sar
    c_agent: "c-sar"
    x_agent: "x-sar"
  - pair_id: volc
    c_agent: "c-volc"
    x_agent: "x-volc"
  - pair_id: insar
    c_agent: "c-insar"
    x_agent: "x-insar"
  - pair_id: dl
    c_agent: "c-dl"
    x_agent: "x-dl"
  - pair_id: data
    c_agent: "c-data"
    x_agent: "x-data"
EOF
}
# scan helper: classification 들 출력
cls(){ python3 "$LE" "$1" --topology "$1/.claude/PAIR_TOPOLOGY.yaml" 2>/dev/null | grep -oE '"classification": "[^"]+"' | sed 's/.*: "//;s/"//'; }
has(){ echo "$1" | grep -qx "$2"; }

# T1 standard triad → pair-live-pass
P="$TMP/t1"; mk_topo "$P"; d="$P/_claude/loops/std-1"; mkdir -p "$d"
echo 'recipe: cross-domain' > "$d/contract.yaml"
printf '{"event":"start"}\n{"event":"verifier_c_sar"}\n{"event":"verifier_x_volc"}\n' > "$d/events.jsonl"
echo '{"status":"PASS"}' > "$d/verdict.json"
has "$(cls "$P")" "pair-live-pass" && ok "T1 standard_triad→pair-live-pass" || no "T1" "$(cls "$P")"

# T2 flat loop files → pair-live-pass
P="$TMP/t2"; mk_topo "$P"; mkdir -p "$P/_claude/loops"
echo 'recipe: x' > "$P/_claude/loops/loop-sarvolc.contract.json" 2>/dev/null
printf '{"event":"start"}\n{"data":{"agents":["c-sar","x-volc"]}}\n' > "$P/_claude/loops/loop-sarvolc.events.jsonl"
echo '{"status":"PASS"}' > "$P/_claude/loops/loop-sarvolc.verdict.json"
has "$(cls "$P")" "pair-live-pass" && ok "T2 flat_loop_files→pair-live-pass" || no "T2" "$(cls "$P")"

# T3 split (verdict+events in loop dir, no contract) → pair from events → pair-live-pass
P="$TMP/t3"; mk_topo "$P"; d="$P/_claude/loops/split-1"; mkdir -p "$d"
printf '{"event":"start"}\n{"data":{"pair":"sar"}}\n{"data":{"pair":"ai"}}\n' > "$d/events.jsonl"
echo '{"status":"PASS"}' > "$d/verdict.json"
R="$(cls "$P")"; { has "$R" "pair-live-pass" || has "$R" "split_contract_verdict"; } ; has "$R" "pair-live-pass" && ok "T3 split→pair-live-pass" || no "T3" "$R"

# T4 thin events + contract selected_pairs + PASS → live-pass-thin-events
P="$TMP/t4"; mk_topo "$P"; d="$P/_claude/loops/thin-1"; mkdir -p "$d"
printf 'recipe: cross-domain\nselected_pairs: dl, data\n' > "$d/contract.yaml"
printf '{"event":"start"}\n{"event":"finalize"}\n' > "$d/events.jsonl"
echo '{"status":"PASS"}' > "$d/verdict.json"
has "$(cls "$P")" "live-pass-thin-events" && ok "T4 thin_events→live-pass-thin-events" || no "T4" "$(cls "$P")"

# T5 Ralph md verdict PASS → pair-live-pass
P="$TMP/t5"; mk_topo "$P"; mkdir -p "$P/_output/ralph"
cat > "$P/_output/ralph/verdict-crossdomain.md" <<'EOF'
# Verdict — SAR ↔ InSAR
## 최종 판정: ✅ PASS (AC1·AC2·AC3)
| AC1 정합 | 결정적 | PASS |
| AC2 근거 | 결정적 | PASS |
c-sar/x-sar, c-insar/x-insar 2 iteration 수렴
EOF
has "$(cls "$P")" "pair-live-pass" && ok "T5 ralph_md→pair-live-pass" || no "T5" "$(cls "$P")"

# T6 session_log only (events only, no verdict) → observed-only
P="$TMP/t6"; mk_topo "$P"; d="$P/_claude/loops/obs-1"; mkdir -p "$d"
printf '{"event":"start"}\n{"data":{"pair":"sar"}}\n' > "$d/events.jsonl"
has "$(cls "$P")" "observed-only" && ok "T6 no-verdict→observed-only" || no "T6" "$(cls "$P")"

# T7 verdict FAIL → HOLD
P="$TMP/t7"; mk_topo "$P"; d="$P/_claude/loops/fail-1"; mkdir -p "$d"
printf '{"event":"verifier_c_sar"}\n' > "$d/events.jsonl"; echo '{"status":"FAIL"}' > "$d/verdict.json"
has "$(cls "$P")" "HOLD" && ok "T7 verdict FAIL→HOLD" || no "T7" "$(cls "$P")"

# T8 verdict missing → not ACTIVE (observed-only/never-used)
P="$TMP/t8"; mk_topo "$P"; d="$P/_claude/loops/nov-1"; mkdir -p "$d"; echo 'recipe: x' > "$d/contract.yaml"
R="$(cls "$P")"; { has "$R" "observed-only" || has "$R" "never-used"; } && ok "T8 verdict missing→not-active" || no "T8" "$R"

# T9 malformed (verdict/status 충돌) → HOLD
P="$TMP/t9"; mk_topo "$P"; d="$P/_claude/loops/mal-1"; mkdir -p "$d"
printf '{"event":"verifier_c_sar"}\n' > "$d/events.jsonl"; echo '{"status":"PASS","verdict":"FAIL"}' > "$d/verdict.json"
has "$(cls "$P")" "HOLD" && ok "T9 malformed→HOLD" || no "T9" "$(cls "$P")"

# T10 axis/prose over-collection 방지: verdict PASS인데 alias 없는 prose 토큰만 → HOLD(unresolved)
P="$TMP/t10"; mk_topo "$P"; d="$P/_claude/loops/prose-1"; mkdir -p "$d"
printf '{"event":"start"}\n{"data":{"agent":"some-free-prose-axis"}}\n' > "$d/events.jsonl"
echo '{"status":"PASS"}' > "$d/verdict.json"
has "$(cls "$P")" "HOLD" && ok "T10 over-collection 방지(unresolved→HOLD)" || no "T10" "$(cls "$P")"

# T11 same project name different path → record 의 abs_path 가 구분
P1="$TMP/a/<example-project>"; P2="$TMP/b/<example-project>"; mk_topo "$P1"; mk_topo "$P2"
d="$P1/_claude/loops/s"; mkdir -p "$d"; printf '{"event":"verifier_c_sar"}\n'>"$d/events.jsonl"; echo '{"status":"PASS"}'>"$d/verdict.json"
A1=$(python3 "$LE" "$P1" --machine m1 2>/dev/null | grep -o '"project_absolute_path": "[^"]*"' | head -1)
A2=$(python3 "$LE" "$P2" --machine m2 2>/dev/null | grep -o '"project_absolute_path": "[^"]*"' | head -1)
[ "$A1" != "$A2" ] && ok "T11 same-name diff-path 구분(abs_path)" || no "T11" "$A1 == $A2"

# T12 missing topology alias → unresolved/HOLD (no false live)
P="$TMP/t12"; mkdir -p "$P/.claude"; d="$P/_claude/loops/noalias"; mkdir -p "$d"
printf '{"event":"verifier_c_xyz"}\n' > "$d/events.jsonl"; echo '{"status":"PASS"}' > "$d/verdict.json"
R="$(python3 "$LE" "$P" 2>/dev/null | grep -oE '"classification": "[^"]+"' | sed 's/.*: "//;s/"//')"
{ has "$R" "HOLD" || has "$R" "observed-only"; } && ! has "$R" "pair-live-pass" && ok "T12 no-alias→no false live" || no "T12" "$R"

# T13 G8~G10 회귀
if [ -f "$ROOT/tests/smoke_fleet_agent_pair_observability.sh" ]; then
  bash "$ROOT/tests/smoke_fleet_agent_pair_observability.sh" >/dev/null 2>&1 && ok "T13 G8-G10 회귀 PASS" || no "T13" "fleet_agent_pair smoke 실패"
else echo "  ⊘ T13 SKIP — fleet observability suite는 public core 제외(멀티머신 전용)"; fi

# T14 deploy_gate 17/17 회귀
if [ -f "$ROOT/tests/smoke_deploy_gate.sh" ]; then
  bash "$ROOT/tests/smoke_deploy_gate.sh" >/dev/null 2>&1 && ok "T14 deploy_gate 회귀 PASS" || no "T14" "deploy_gate smoke 실패"
else no "T14" "smoke 없음"; fi

# T15 secret residual 0 (모듈 자체)
if grep -qE 'ghp_[A-Za-z0-9]{20}|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}' "$LE"; then no "T15" "secret in module"; else ok "T15 secret residual 0"; fi

echo "[ledger_variant] PASS $PASS / FAIL $FAIL"
[ "$FAIL" -eq 0 ]
