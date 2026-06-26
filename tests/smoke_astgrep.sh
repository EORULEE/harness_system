#!/usr/bin/env bash
# ast-grep smoke (Evidence Index 보완). ast-grep 없으면 graceful skip(필수 의존 아님).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SG="$ROOT/.claude/skills/_evidence-core/astgrep/sgconfig.yml"
AG="$(command -v ast-grep || echo "$HOME/.npm-global/bin/ast-grep")"
P=0; F=0
ok(){ echo "  PASS $1"; P=$((P+1)); }
no(){ echo "  FAIL $1"; F=$((F+1)); }

if ! [ -x "$AG" ] && ! command -v ast-grep >/dev/null 2>&1; then
  echo "  SKIP ast-grep 미설치 — 하네스는 ast-grep 없이도 동작(필수 의존 아님)"; exit 0
fi
"$AG" --version >/dev/null 2>&1 && ok "ast-grep 가용 ($("$AG" --version))" || { no "ast-grep 실행 불가"; exit 1; }

cnt(){ # $1=dir $2=ruleId
  "$AG" scan -c "$SG" --json "$ROOT/$1" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len([x for x in d if x.get('ruleId')=='$2']))" 2>/dev/null || echo 0
}

echo "== 1. config + 3 rule 유효 (scan 무에러) =="
"$AG" scan -c "$SG" "$ROOT/hooks" >/dev/null 2>&1 && ok "scan 실행 OK" || no "scan 에러"

echo "== 2. 구조 매치 카운트(기대 하한) =="
he=$(cnt hooks hook-process-exit);  [ "${he:-0}" -ge 3 ] && ok "hooks process.exit=$he (>=3)" || no "process.exit=$he"
se=$(cnt scripts py-sys-exit);      [ "${se:-0}" -ge 2 ] && ok "scripts sys.exit=$se (>=2)" || no "sys.exit=$se"
fd=$(cnt scripts py-func-def);      [ "${fd:-0}" -ge 1 ] && ok "scripts func-def=$fd (>=1)" || no "func-def=$fd"

echo "== 3. AST vs 텍스트 차별성(핵심 가치) =="
T="$(mktemp /tmp/agsmoke_XXXX.mjs)"
printf '// process.exit(2) in a comment\nconst s = "process.exit(2)";\nprocess.exit(2);\n' > "$T"
ag_m=$("$AG" -p 'process.exit($C)' -l js "$T" 2>/dev/null | grep -c 'process.exit')
rg_m=$(rg -c 'process.exit\(2\)' "$T" 2>/dev/null || echo 0)
# ast-grep=1(실제 호출만), rg=3(주석+문자열+호출)
{ [ "$ag_m" = "1" ] && [ "$rg_m" = "3" ]; } && ok "ast-grep=$ag_m(호출만) vs rg=$rg_m(전부) — 구조 정확성 입증" || no "차별성 미입증(ag=$ag_m rg=$rg_m)"
rm -f "$T"

echo "== 4. probe 자동 ast-grep 배선 (must_read 도메인) =="
# index 최신화 후 probe stop_guard가 자동으로 ast-grep 구조 anchor를 surface하는지
python3 "$ROOT/scripts/system_truth_indexer.py" >/dev/null 2>&1
pout="$(python3 "$ROOT/scripts/system_truth_probe.py" stop_guard 2>/dev/null)"
echo "$pout" | grep -q "ast-grep 구조 anchor" && ok "must_read 자동 ast-grep 호출됨" || no "자동 호출 안 됨"
echo "$pout" | grep -q "process.exit" && ok "stop.mjs 실 exit anchor surface" || no "exit anchor 없음"
# index_ok 도메인은 ast-grep 미호출(과호출 방지)
sout="$(python3 "$ROOT/scripts/system_truth_probe.py" skills 2>/dev/null)"
echo "$sout" | grep -q "ast-grep 구조 anchor" && no "index_ok에서 과호출" || ok "index_ok(skills) 미호출(정상)"

echo "== 5. secret 0 (rules·config) — SECRET_RE 정렬(codex-MINOR7) =="
if grep -rEq "AIza[0-9A-Za-z_-]{10,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----" "$(dirname "$SG")"; then no "secret"; else ok "secret 0"; fi

echo ""
echo "== 결과: PASS=$P FAIL=$F =="
[ "$F" -eq 0 ] && echo "ALL PASS" || echo "FAILURES=$F"
exit $F
