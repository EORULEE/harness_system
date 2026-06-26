#!/usr/bin/env bash
# Evidence Index v1 static smoke (read-mostly; only writes to .claude/runtime/ + temp).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="$ROOT/.claude/runtime"
J="$RT/system_truth_index.json"
P=0; F=0
ok(){ echo "  PASS $1"; P=$((P+1)); }
no(){ echo "  FAIL $1"; F=$((F+1)); }

echo "== 1. indexer 실행 + 3 산출물 =="
python3 "$ROOT/scripts/system_truth_indexer.py" >/dev/null 2>&1
for f in system_truth_index.json system_truth_index.sha256 system_truth_index.log; do
  [ -s "$RT/$f" ] && ok "산출물 $f" || no "산출물 $f 없음/빈값"
done

echo "== 2. index.json 유효 + 도메인 수 =="
dc=$(python3 -c "import json;print(json.load(open('$J'))['domain_count'])" 2>/dev/null || echo 0)
[ "${dc:-0}" -ge 13 ] && ok "도메인 $dc (>=13)" || no "도메인 $dc"

echo "== 3. .sha256 무결성 (index.json 자체 해시 일치) =="
rec=$(awk '{print $1}' "$RT/system_truth_index.sha256")
act=$(sha256sum "$J" | awk '{print $1}')
[ "$rec" = "$act" ] && ok "sha256 일치" || no "sha256 불일치(rec=$rec act=$act)"

echo "== 4. secret 0 (index + log) — indexer SECRET_RE와 정렬(codex-MINOR7) =="
SECRE="AIza[0-9A-Za-z_-]{10,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
if grep -rEq "$SECRE" "$J" "$RT/system_truth_index.log"; then
  no "secret 발견"; else ok "secret 0"; fi

echo "== 5. env_secrets = presence만(내용/hash 없음) =="
python3 - "$J" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
items=d["domains"].get("env_secrets",{}).get("items",[])
bad=[i for i in items if "sha256" in i]   # secret엔 hash 없어야
print("  PASS env_secrets presence-only" if (items and not bad) else "  FAIL env_secrets")
sys.exit(0 if (items and not bad) else 1)
PY
[ $? -eq 0 ] && P=$((P+1)) || F=$((F+1))

echo "== 6. probe --stale = 빌드 직후 all fresh =="
python3 "$ROOT/scripts/system_truth_probe.py" --stale 2>/dev/null | grep -q "fresh (index 신선)" && ok "all fresh" || no "fresh 아님"

echo "== 7. stale 탐지 (격리: /tmp 복사본 변조 — 실 index 무변경, drvfs 레이스 회피) =="
TMPJ="$(mktemp /tmp/sti_smoke_XXXX.json)"
python3 - "$J" "$TMPJ" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
fh=d.get("files_hash",{}); k=next(iter(fh)); fh[k]["sha256"]="0"*64   # 틀린 해시
json.dump(d,open(sys.argv[2],"w",encoding="utf-8"),ensure_ascii=False,indent=2)
PY
# probe --stale는 stale 발견 시 exit 1(의도) → pipefail 회피 위해 출력을 변수로 캡처 후 grep
st_out="$(python3 "$ROOT/scripts/system_truth_probe.py" --index "$TMPJ" --stale 2>/dev/null)"
echo "$st_out" | grep -q "STALE" && ok "stale 탐지됨" || no "stale 미탐지"
rm -f "$TMPJ"   # 복원

echo "== 8. probe --list / domain 동작 =="
python3 "$ROOT/scripts/system_truth_probe.py" --list 2>/dev/null | grep -q "domains" && ok "--list" || no "--list"
python3 "$ROOT/scripts/system_truth_probe.py" skills 2>/dev/null | grep -q "risk=" && ok "domain skills" || no "domain skills"

echo "== 9. --if-stale 자동갱신 게이트 (fresh면 생략) =="
python3 "$ROOT/scripts/system_truth_indexer.py" >/dev/null 2>&1   # 최신화
ifs="$(python3 "$ROOT/scripts/system_truth_indexer.py" --if-stale 2>/dev/null)"
echo "$ifs" | grep -q "갱신 생략" && ok "fresh 시 --if-stale 생략(빠름)" || no "--if-stale 게이트"
# probe 자동갱신 배선(--no-refresh로 생략 가능)
python3 "$ROOT/scripts/system_truth_probe.py" --no-refresh --list >/dev/null 2>&1 && ok "probe --no-refresh 동작" || no "--no-refresh"

echo ""
echo "== 결과: PASS=$P FAIL=$F =="
[ "$F" -eq 0 ] && echo "ALL PASS" || echo "FAILURES=$F"
exit $F
