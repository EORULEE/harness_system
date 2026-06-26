#!/usr/bin/env bash
# Static smoke for the Superpowers-vendored Dev Discipline Suite (offline, deterministic).
# Verifies: dmi:true on all new skills · no runtime/auto-trigger leakage · provenance · secret 0
# · existing _dev-discipline-core 2 files unchanged.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SK="$ROOT/.claude/skills"
VDIR="$SK/_dev-discipline-core/vendors/obra-superpowers"
fail=0; pass=0
ok(){ echo "  PASS $1"; pass=$((pass+1)); }
no(){ echo "  FAIL $1"; fail=$((fail+1)); }

NEW_SKILLS="harness-skill-tdd harness-systematic-debugging harness-tdd-implementation harness-spec-quality-review harness-code-quality-review harness-dev-closeout harness-dev-router"
# 6 discipline skill = dmi:true(명시) · dev-router = dmi:false(자동 해석, 2026-06-16)
DISCIPLINE_SKILLS="harness-skill-tdd harness-systematic-debugging harness-tdd-implementation harness-spec-quality-review harness-code-quality-review harness-dev-closeout"

echo "== 1. discipline 6 skill = dmi:true + frontmatter, dev-router = dmi:false =="
for s in $DISCIPLINE_SKILLS; do
  f="$SK/$s/SKILL.md"
  [ -f "$f" ] || { no "$s missing"; continue; }
  grep -q "^disable-model-invocation: true" "$f" && grep -q "^name: $s" "$f" \
    && grep -qE "^description: Use when " "$f" && ok "$s frontmatter+dmi:true" || no "$s frontmatter/dmi"
done
dr="$SK/harness-dev-router/SKILL.md"
grep -q "^disable-model-invocation: false" "$dr" && grep -qE "^description: Use when " "$dr" \
  && ok "harness-dev-router dmi:false(자동 해석)" || no "dev-router dmi:false"

echo "== 2a. 7 SKILL.md = 채택 런타임 문구 0 (invocable 단위는 청정) =="
SKILL_FILES=$(for s in $NEW_SKILLS; do echo "$SK/$s/SKILL.md"; done)
# upstream 리터럴 runtime 신호만(내 한국어 거부 서술과 충돌 회피)
RUNTIME_RE="triggers automatically|Do not pause to check in|mandatory workflows, not suggestions|/plugin install|marketplace add"
if grep -lE "$RUNTIME_RE" $SKILL_FILES 2>/dev/null; then no "skill에 런타임 문구"; else ok "7 skill 런타임 문구 0"; fi

echo "== 2b. core 규율: 런타임 패턴은 '거부 인용'만 허용 (adoption 0) =="
# core .md(vendors 제외)에서 런타임 문구가 나오면, 그 줄은 반드시 거부맥락이어야 함
CORE_FILES=$(ls "$SK"/_dev-discipline-core/*.md)
adopt=0
while IFS= read -r line; do
  echo "$line" | grep -qE "불채택|가져오지 않|제거|금지|않는다|아님|미채택|X\b" || { echo "    ⚠️ 비거부 런타임 줄: $line" | cut -c1-120; adopt=1; }
done < <(grep -hE "$RUNTIME_RE" $CORE_FILES 2>/dev/null)
[ "$adopt" -eq 0 ] && ok "core 런타임 문구 = 전부 거부맥락(adoption 0)" || no "core에 런타임 adoption"
# 정책이 거부를 명시적으로 문서화하는지 (positive)
grep -q "불채택" "$SK/_dev-discipline-core/superpowers-adaptation-policy.md" && ok "adaptation-policy 거부 명문화" || no "거부 명문 누락"

echo "== 3. 출처 보존 =="
[ -f "$VDIR/upstream-commit.txt" ] && grep -q "284be590" "$VDIR/upstream-commit.txt" && ok "commit SHA 핀" || no "commit.txt"
[ -f "$VDIR/LICENSE" ] && grep -qi "MIT" "$VDIR/LICENSE" && ok "LICENSE(MIT)" || no "LICENSE"
n=$(ls "$VDIR"/upstream-*.md 2>/dev/null | wc -l); [ "$n" -eq 7 ] && ok "upstream snapshot 7개" || no "snapshot $n/7"

echo "== 4. secret 0 (전 신규 파일) =="
if grep -rEl "AIza[0-9A-Za-z_-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-" \
   $SKILL_FILES $CORE_FILES "$VDIR" 2>/dev/null; then no "secret 발견"; else ok "secret 0"; fi

echo "== 5. allowed-tools 최소(Write/Edit 없음) =="
we=0; for s in $NEW_SKILLS; do
  grep -qE "allowed-tools:.*(Write|Edit)" "$SK/$s/SKILL.md" && { no "$s has Write/Edit"; we=1; }
done; [ "$we" -eq 0 ] && ok "Write/Edit 미부여 확인"

echo "== 6. cheatsheet 불변(md5) + trigger-policy 의도적 확장(§10) =="
exp_cheat="cd6e8604333442443b8f3a8a26936917"
a=$(md5sum "$SK/_dev-discipline-core/dev-discipline-cheatsheet.md" 2>/dev/null | cut -d' ' -f1)
[ "$a" = "$exp_cheat" ] && ok "cheatsheet md5 불변($exp_cheat)" || no "cheatsheet 변경됨($a)"
# trigger-policy는 2026-06-16 '알아서 처리'로 §10 추가(의도적 확장) — 자동적용 매핑 존재 확인
grep -q "Dev Discipline Suite 자동 적용 매핑" "$SK/_dev-discipline-core/dev-discipline-trigger-policy.md" \
  && ok "trigger-policy §10 자동적용 매핑 존재(의도적 확장)" || no "trigger-policy §10 누락"

echo ""
echo "== 결과: PASS=$pass FAIL=$fail =="
[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "FAILURES=$fail"
exit $fail
