#!/usr/bin/env bash
# install_into_project.sh — 기존 프로젝트 폴더에 하네스를 "연동"(설치)한다.
#   폴더를 옮기지 않는다. 하네스 설정만 당신 프로젝트 안으로 복사하고,
#   기존 CLAUDE.md / settings.json 은 덮어쓰지 않고 보존·병합한다.
# 사용법:  bash install_into_project.sh /경로/내-연구프로젝트
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${1:-}"
if [ -z "$DST" ]; then
  echo "사용법: bash install_into_project.sh <당신의-기존-프로젝트-폴더>"
  echo "  예:   bash install_into_project.sh ~/research/flood-segmentation"
  exit 1
fi
[ -d "$DST" ] || { echo "✗ 폴더가 없습니다: $DST"; exit 1; }
DST="$(cd "$DST" && pwd)"
[ "$DST" = "$SRC" ] && { echo "✗ 하네스 폴더 자신에는 설치할 필요가 없습니다."; exit 1; }

echo "═══════════ 하네스 → 기존 프로젝트 연동 ═══════════"
echo "  대상: $DST"
echo "  (연구 데이터·코드는 건드리지 않습니다. 하네스 설정만 추가.)"
echo ""

# 1) 코드 폴더 = add-only(기존 파일 보존, 누락분만 채움)
for d in hooks scripts tests; do
  mkdir -p "$DST/$d"
  cp -rn "$SRC/$d/." "$DST/$d/" 2>/dev/null || true
  echo "  ✓ $d/"
done

# 2) 스킬 45개 (add-only)
mkdir -p "$DST/.claude/skills"
cp -rn "$SRC/.claude/skills/." "$DST/.claude/skills/" 2>/dev/null || true
echo "  ✓ .claude/skills/ (45)"

# 2b) _output/ (fleet-dashboard 콜렉터 + release 마커 — 일부 smoke 가 참조). add-only.
mkdir -p "$DST/_output"
cp -rn "$SRC/_output/." "$DST/_output/" 2>/dev/null || true
echo "  ✓ _output/ (collector·release 마커)"

# 3) selftest 도 넣어 그 프로젝트에서 검증 가능하게
cp -n "$SRC/selftest.sh" "$DST/selftest.sh" 2>/dev/null || true
for doc in SETUP.md ACCOUNTS.md WIKI.md CLAUDE.md; do :; done

# 4) CLAUDE.md — 기존 보존 + @import 로 하네스 규율 활성(텍스트는 안 합침)
if [ -f "$DST/CLAUDE.md" ]; then
  cp -f "$SRC/CLAUDE.md" "$DST/CLAUDE.harness.md"   # 하네스 규율 본문(재실행 시 최신으로 갱신)
  if grep -q "@CLAUDE.harness.md" "$DST/CLAUDE.md"; then
    echo "  • 기존 CLAUDE.md 에 이미 '@CLAUDE.harness.md' import 있음(중복 안 함) · 본문 갱신"
  else
    printf '\n<!-- harness 규율 import (이 두 줄만 지우면 하네스 규율 비활성) -->\n@CLAUDE.harness.md\n' >> "$DST/CLAUDE.md"
    echo "  ✓ 기존 CLAUDE.md 보존 + 끝에 '@CLAUDE.harness.md' import 추가 → 당신 규율 + 하네스 규율 둘 다 활성"
  fi
else
  cp "$SRC/CLAUDE.md" "$DST/CLAUDE.md"
  echo "  ✓ CLAUDE.md"
fi

# 5) settings.json — 훅 배선 '병합'(기존 훅 보존 + 하네스 훅 추가, 중복 제외)
python3 - "$SRC/.claude/settings.json" "$DST/.claude/settings.json" <<'PY'
import json, sys, os, shutil
src_p, dst_p = sys.argv[1], sys.argv[2]
src = json.load(open(src_p, encoding="utf-8"))
backed = False
if os.path.exists(dst_p):
    shutil.copy(dst_p, dst_p + ".bak"); backed = True
    dst = json.load(open(dst_p, encoding="utf-8"))
else:
    dst = {}
dst.setdefault("hooks", {})
added = 0
for event, groups in src.get("hooks", {}).items():
    cur = dst["hooks"].setdefault(event, [])
    seen = {json.dumps(g, sort_keys=True, ensure_ascii=False) for g in cur}
    for g in groups:
        key = json.dumps(g, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            cur.append(g); seen.add(key); added += 1
# 하네스가 쓰는 그 외 최상위 키는 기존에 없을 때만 채움(기존 우선)
for k, v in src.items():
    if k != "hooks":
        dst.setdefault(k, v)
os.makedirs(os.path.dirname(dst_p), exist_ok=True)
json.dump(dst, open(dst_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  ✓ .claude/settings.json 훅 병합 (+{added} 그룹" + (", 기존은 .bak 백업)" if backed else ", 신규 생성)"))
PY

echo ""
echo "═══════════ 검증 ═══════════"
( cd "$DST" && bash selftest.sh 2>&1 | grep -E "smoke [0-9]+/|코어 정상|일부 실패" )
echo ""
echo "✅ 연동 완료. 이제:"
echo "    cd \"$DST\"  &&  claude"
echo "  그 폴더에서 Claude Code 를 켜면 하네스가 자동 인식됩니다(연구 데이터 그대로)."
echo "  되돌리기: 위에서 추가된 hooks/ scripts/ tests/ .claude/skills/ 와"
echo "            settings.json(.bak 로 복원) 만 제거하면 됩니다."
