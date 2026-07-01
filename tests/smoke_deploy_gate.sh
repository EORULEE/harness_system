#!/usr/bin/env bash
# smoke_deploy_gate — 배포 preflight/postflight 게이트 검증 (G8~G10·Integrity Audit 교훈 내장).
# 읽기전용. fixtures(fleet-agent-pair) 재사용. assertion 삭제/skip/강제PASS 금지.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATE="$ROOT/scripts/deploy_gate.py"
FX="$ROOT/tests/fixtures/fleet-agent-pair"
# r13: deny-by-default 패키징이 strip 하는 휘발성 fixture(proj-observed session_log) 런타임 재생성 → offline/clone 설치본 T9 false-fail 방지
. "$ROOT/tests/lib/volatile_fixtures.sh"; regen_volatile_fixtures "$FX"
# r13: hermetic 배포-인프라 fixture — central(fleet-dashboard 정합)·rollback(archive 개방) 검사를 실제 인프라 존재여부와 분리(T7/T13). pristine clone 에서도 게이트 로직 검증(--infra-root).
INFRA="$(mktemp -d)"; trap 'rm -rf "$INFRA"' EXIT
mkdir -p "$INFRA/fleet-dashboard" "$INFRA/_output/release/current" "$INFRA/_output/release/archive/seed"
for x in fleet_summary.py fleet_aggregate.py render.py fleet-registry.json; do : > "$INFRA/fleet-dashboard/$x"; done
P=0; F=0; ok(){ echo "  ✓ $1"; P=$((P+1)); }; no(){ echo "  ✗ $1"; F=$((F+1)); }
g(){ python3 "$GATE" "$@" 2>/dev/null; }
jq_field(){ python3 -c 'import sys,json;d=json.load(sys.stdin);exec("v=d"+sys.argv[1]);print(v)' "$1"; }

# T1 audit level: new-machine → DEEP
[ "$(g preflight --project "$FX/proj-real-ledger" --new-machine | jq_field "['selected_audit_level']")" = DEEP ] && ok "T1 new-machine→DEEP" || no "T1 DEEP"
# T2 audit level: active+small-delta → FAST
[ "$(g preflight --project "$FX/proj-real-ledger" --active --small-delta | jq_field "['selected_audit_level']")" = FAST ] && ok "T2 active+small→FAST" || no "T2 FAST"
# T3 audit level: pair-creation → STANDARD
[ "$(g preflight --project "$FX/proj-real-ledger" --pair-creation | jq_field "['selected_audit_level']")" = STANDARD ] && ok "T3 pair-creation→STANDARD" || no "T3 STANDARD"
# T4 x-agent Write/Edit → CRITICAL/HOLD
[ "$(g preflight --project "$FX/proj-implicit-write" | jq_field "['final_state']")" = HOLD ] && ok "T4 x-agent write→HOLD(CRITICAL)" || no "T4 x-write HOLD"
# T5 agent file != valid pair (cx-no-topology: valid 0, cx_files 4)
v=$(g preflight --project "$FX/proj-cx-no-topology" | jq_field "['per_project'][0]['agent_pair']['valid_pairs']")
cf=$(g preflight --project "$FX/proj-cx-no-topology" | jq_field "['per_project'][0]['agent_pair']['cx_files']")
[ "$v" = 0 ] && [ "$cf" = 4 ] && ok "T5 agent파일($cf)≠valid pair($v)" || no "T5 agent≠pair"
# T6 broken pair → HOLD (proj-full 에 data pair broken). g 가 HOLD 시 exit2 → 출력 먼저 캡처(pipefail 회피)
t6=$(g preflight --project "$FX/proj-full"); echo "$t6" | jq_field "['per_project'][0]['agent_pair']['findings']" | grep -q broken && ok "T6 broken pair 탐지" || no "T6 broken"
# T7 static-pass != ACTIVE: valid pair 있고 ledger 0 → postflight CONDITIONAL(ACTIVE 아님)
t7=$(g postflight --infra-root "$INFRA" --project "$FX/proj-static"); [ "$(echo "$t7" | jq_field "['final_state']")" = CONDITIONAL ] && ok "T7 static-pass≠ACTIVE(ledger 0→CONDITIONAL)" || no "T7 static≠ACTIVE"
# T8 formal ledger 있음+PASS → live-pass (proj-real-ledger postflight PASS)
lp=$(g postflight --project "$FX/proj-real-ledger" | jq_field "['per_project'][0]['formal_loop_ledger']['live_pass']")
[ "$lp" = 2 ] && ok "T8 formal ledger+PASS→live_pass=2" || no "T8 live_pass=$lp"
# T9 session_log-only != formal verdict: observed-only → ACTIVE 금지 (HOLD→exit2, 출력 먼저 캡처)
t9=$(g postflight --project "$FX/proj-observed"); echo "$t9" | jq_field "['per_project'][0]['formal_loop_ledger']['findings']" | grep -q "observed-only" && ok "T9 session_log-only→ACTIVE 금지(observed-only)" || no "T9 observed-only"
# T10 contract-only verdict(verdict 파일 없음) → live 0 (날조 방지)
[ "$(g postflight --project "$FX/proj-contract-only-verdict" | jq_field "['per_project'][0]['formal_loop_ledger']['live_pass']")" = 0 ] && ok "T10 contract-only verdict→live 0" || no "T10 contract-only"
# T11 runtime gate: STANDARD/DEEP 에서 실행, FAST 에서 skip
t11=$(g preflight --project "$FX/proj-real-ledger" --active --small-delta); echo "$t11" | jq_field "['checks_skipped_with_reason']" | grep -q runtime_parity && ok "T11 FAST는 runtime_parity skip(사유 명시)" || no "T11 skip"
t12=$(g preflight --project "$FX/proj-real-ledger" --new-machine); echo "$t12" | jq_field "['runtime_parity']['gate']" | grep -q runtime_parity && ok "T12 DEEP는 runtime_parity 실행" || no "T12 runtime run"
# T13 rollback/security gate: archive 개방 + secret 0 (hermetic infra-root → 실 archive 존재여부와 분리)
t13=$(g preflight --infra-root "$INFRA" --project "$FX/proj-real-ledger"); echo "$t13" | jq_field "['rollback_security']['archive_openable']" | grep -qi true && ok "T13 rollback archive 개방" || no "T13 archive"
[ "$(g preflight --project "$FX/proj-real-ledger" | jq_field "['rollback_security']['secret_residual']")" = 0 ] && ok "T14 secret residual 0" || no "T14 secret"
# T15 표준 출력 필드 전부 존재
need='selected_audit_level selection_reason checks_to_run checks_skipped_with_reason expected_materialization formal_loop_ledger_requirement preflight_result final_state'
out=$(g preflight --project "$FX/proj-real-ledger")
miss=0; for k in $need; do echo "$out" | grep -q "\"$k\"" || miss=$((miss+1)); done
[ "$miss" = 0 ] && ok "T15 표준 출력 필드 8종 전부 존재" || no "T15 출력 누락 $miss"
# T16 금지 등식 7개 명시
[ "$(echo "$out" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['forbidden_equalities']))")" = 7 ] && ok "T16 금지 등식 7개" || no "T16 금지등식"
# T17 read-only: deploy_gate 가 입력 파일 수정 안 함(destructive 호출 0)
grep -qE "shutil.rmtree|os.remove|\.unlink\(|\.write_text|open\([^)]*,[^)]*['\"]w" "$GATE" && no "T17 write 호출 있음" || ok "T17 deploy_gate write/destructive 0(읽기전용)"
# T18 (Codex WARN 보완) 실제 rollback archive 개방을 non-hermetic 으로 검증. pristine clone(archive 미존재)엔 명시 skip — 배포 머신서 실검증.
if [ -d "$ROOT/_output/release/archive" ] && [ -n "$(ls -A "$ROOT/_output/release/archive" 2>/dev/null)" ]; then
  t18=$(g preflight --project "$FX/proj-real-ledger"); echo "$t18" | jq_field "['rollback_security']['archive_openable']" | grep -qi true && ok "T18 실제 rollback archive 개방(non-hermetic)" || no "T18 real archive"
else
  ok "T18 실제 archive 없음(pristine clone) → skip(배포 머신서 실검증; hermetic T13 로 로직 커버)"
fi

echo "[deploy_gate] PASS $P / FAIL $F"; [ $F -eq 0 ]
