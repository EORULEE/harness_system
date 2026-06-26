#!/usr/bin/env bash
# smoke_shared_knowledge_layer.sh — 모델 공유지식층 canary (격리, 비민감 테스트 프로젝트만).
# 실 publish_shared_context.py 를 fixture active_context 로 구동해 7개 속성 검증.
# 기존 vault/wiki 노트·정본은 읽기만(미접근/무변경). 결정적·오프라인.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="python3"
TMP="$(mktemp -d)"
PASS=0; FAIL=0
ok(){ if [ "$1" = "1" ]; then echo "  PASS $2"; PASS=$((PASS+1)); else echo "  FAIL $2"; FAIL=$((FAIL+1)); fi; }

# 기존 wiki 노트(_system 제외) baseline md5 — 무변경 검증용
BEFORE="$($PY - "$REPO" <<'EOF'
import sys,os,hashlib
repo=sys.argv[1]; root=os.path.join(repo,"vault","wiki")
h=hashlib.sha256()
for dp,_,fs in sorted(os.walk(root)):
    if os.sep+"_system" in dp or os.sep+"review_queue" in dp: continue
    for f in sorted(fs):
        p=os.path.join(dp,f); h.update(p.encode()); h.update(open(p,"rb").read())
print(h.hexdigest())
EOF
)"

# fixture active_context 렌더(실 renderer 사용 → 포맷 정합)
gen_fixture(){  # $1=name $2=project $3=status $4=secretflag
  $PY - "$REPO" "$TMP" "$1" "$2" "$3" "$4" <<'EOF'
import sys,os
repo,tmp,name,proj,status,sec=sys.argv[1:7]
sys.path.insert(0,os.path.join(repo,"scripts"))
from update_active_context import write_active_context
fake="AI"+"za"+"Sy"+"D"+"x"*30
done=["문헌 3편 요약","표 초안 작성","그림 1 캡션"]
if sec=="1": done.append(f"키 로그 정리 (secret {fake})")
data=dict(project_id=proj, source_session_id="canary-"+name, source_event="session_end",
          status=status, current_objective="수체탐지 리뷰 섹션 2 작성",
          completed=done, next_action="섹션 3 초안 작성",
          locked_facts=["대상 저널=RSE","총 섹션 5개"],
          relevant_wiki_notes=["methods/ndwi.md","entities/QTU-Net.md"],
          latest_checkpoint="project_session_checkpoint.md @ test",
          confidence="medium", needs_review=False)
mem=os.path.join(tmp,name,"memory"); os.makedirs(mem,exist_ok=True)
p,_,_=write_active_context(mem,data)
print(p)
EOF
}

run_publish(){ # $1=active $2=outdir $3=project
  $PY "$REPO/scripts/publish_shared_context.py" --active "$1" --out-dir "$2" --project-id "$3" --checkpoint "$TMP/ck.md"
}

echo "==== canary: 모델 공유지식층 (SHARED_CONTEXT) ===="

# --- T1: FRESH fixture → SHARED_CONTEXT 생성 ---
AC=$(gen_fixture fresh test-shared-canary active 0)
OUT="$TMP/out_fresh"
RES=$(run_publish "$AC" "$OUT" test-shared-canary)
SC="$OUT/SHARED_CONTEXT.md"; IDX="$OUT/AGENT_MEMORY_INDEX.yaml"
[ -f "$SC" ] && ok 1 "T1 SHARED_CONTEXT.md 생성" || ok 0 "T1 SHARED_CONTEXT.md 생성"
[ -f "$IDX" ] && ok 1 "T1 AGENT_MEMORY_INDEX.yaml 생성" || ok 0 "T1 AGENT_MEMORY_INDEX.yaml 생성"

# --- T2: ACTIVE_CONTEXT 필드 일치(objective/completed/next/locked/wiki) ---
$PY - "$AC" "$SC" <<'EOF' && ok 1 "T2 active_context 필드 미러 일치" || ok 0 "T2 active_context 필드 미러 일치"
import sys,re
ac=open(sys.argv[1],encoding="utf-8").read(); sc=open(sys.argv[2],encoding="utf-8").read()
need=["수체탐지 리뷰 섹션 2 작성","섹션 3 초안 작성","문헌 3편 요약","표 초안 작성",
      "그림 1 캡션","대상 저널=RSE","총 섹션 5개","methods/ndwi.md","entities/QTU-Net.md"]
miss=[x for x in need if x not in sc]
sys.exit(0 if not miss else (print("missing:",miss) or 1))
EOF

# --- T3: source sha256 일치 ---
SHA_FILE=$($PY -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$AC")
SHA_DOC=$(grep -oE 'source_sha256: "[0-9a-f]+"' "$SC" | grep -oE '[0-9a-f]{64}')
[ "$SHA_FILE" = "$SHA_DOC" ] && ok 1 "T3 source sha256 일치 ($SHA_DOC)" || ok 0 "T3 source sha256 일치 ($SHA_FILE != $SHA_DOC)"

# --- T4: stale 탐지 (fresh=false / stale fixture=true / project 불일치=true) ---
grep -q 'stale: false' "$SC" && ok 1 "T4a fresh → stale:false" || ok 0 "T4a fresh → stale:false"
AC_S=$(gen_fixture staled test-shared-canary stale 0)
run_publish "$AC_S" "$TMP/out_stale" test-shared-canary >/dev/null
grep -q 'stale: true' "$TMP/out_stale/SHARED_CONTEXT.md" && grep -q 'stale_reason: "status_stale"' "$TMP/out_stale/SHARED_CONTEXT.md" \
  && ok 1 "T4b status=stale → stale:true" || ok 0 "T4b status=stale → stale:true"
run_publish "$AC" "$TMP/out_mis" WRONG-PROJECT >/dev/null
grep -q 'stale: true' "$TMP/out_mis/SHARED_CONTEXT.md" && grep -q 'project_mismatch' "$TMP/out_mis/SHARED_CONTEXT.md" \
  && ok 1 "T4c project 불일치 → stale:true" || ok 0 "T4c project 불일치 → stale:true"

# --- T5: secret residual 0 (fake key 주입 fixture) ---
AC_SEC=$(gen_fixture sec test-shared-canary active 1)
RES_SEC=$(run_publish "$AC_SEC" "$TMP/out_sec" test-shared-canary)
RESID=$(echo "$RES_SEC" | $PY -c "import json,sys;print(json.load(sys.stdin)['residual_secrets'])")
grep -qE 'AIza[0-9A-Za-z_-]{20,}' "$TMP/out_sec/SHARED_CONTEXT.md" && SECFOUND=1 || SECFOUND=0
{ [ "$RESID" = "0" ] && [ "$SECFOUND" = "0" ]; } && ok 1 "T5 secret residual 0 (마스킹됨)" || ok 0 "T5 secret residual 0 (resid=$RESID found=$SECFOUND)"
grep -q 'REDACTED' "$TMP/out_sec/SHARED_CONTEXT.md" && ok 1 "T5b 마스킹 placeholder 존재" || ok 0 "T5b 마스킹 placeholder 존재"

# --- T6: 2KB 이하 + transcript 미포함 + 'source of truth 아님' 배너 ---
BYTES=$(wc -c < "$SC")
[ "$BYTES" -le 2048 ] && ok 1 "T6 SHARED_CONTEXT ≤2KB ($BYTES)" || ok 0 "T6 SHARED_CONTEXT ≤2KB ($BYTES)"
grep -q 'source of truth가 아닙니다' "$SC" && ok 1 "T6b 'source of truth 아님' 배너" || ok 0 "T6b 배너"
grep -qiE 'last_user_hint|transcript' "$SC" && ok 0 "T6c transcript 원문 미포함" || ok 1 "T6c transcript 원문 미포함"

# --- T7: 기존 wiki 노트 무변경 ---
AFTER="$($PY - "$REPO" <<'EOF'
import sys,os,hashlib
repo=sys.argv[1]; root=os.path.join(repo,"vault","wiki")
h=hashlib.sha256()
for dp,_,fs in sorted(os.walk(root)):
    if os.sep+"_system" in dp or os.sep+"review_queue" in dp: continue
    for f in sorted(fs):
        p=os.path.join(dp,f); h.update(p.encode()); h.update(open(p,"rb").read())
print(h.hexdigest())
EOF
)"
[ "$BEFORE" = "$AFTER" ] && ok 1 "T7 기존 wiki 노트 무변경" || ok 0 "T7 기존 wiki 노트 변경됨!"

# --- T8: AGENT_MEMORY_INDEX = 포인터만(내용 사본 아님) ---
grep -q 'pointers:' "$IDX" && ! grep -q '문헌 3편 요약' "$IDX" && ok 1 "T8 INDEX=포인터만(완료내용 미복제)" || ok 0 "T8 INDEX 포인터만"

rm -rf "$TMP"
echo "==== smoke 결과: PASS=$PASS  FAIL=$FAIL ===="
[ "$FAIL" = "0" ] && exit 0 || exit 1
