#!/usr/bin/env bash
# smoke_personas.sh — 범용 페르소나 체계 검증 (계약 AC1~AC8, AC11)
set -u
CORE="$(dirname "$0")/../.claude/skills/_paper-review-core"
SK="$HOME/.claude/skills"
P="$CORE/personas.yaml"
C="$CORE/persona-composition.md"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=== smoke_personas ==="

# T1 (AC1): personas.yaml 존재 + 역할 6종 + self-review
[ -f "$P" ] && python3 -c "import yaml;d=yaml.safe_load(open('$P'));ps=d['personas'];assert all(k in ps for k in ['self-review','peer-review','reviewer-response','writing-polish','patent-assist','report-writer','slide-writer']);print(len(ps))" >/dev/null 2>&1 && ok "T1 personas.yaml 7역할(6+self)" || no "T1 역할 누락"

# T2 (AC1): 각 페르소나 필수 필드(stance·goal·rigor·non_goals)
python3 -c "import yaml;d=yaml.safe_load(open('$P'));assert all(all(f in v for f in ['stance','goal','rigor','non_goals']) for v in d['personas'].values());print('ok')" >/dev/null 2>&1 && ok "T2 필수필드(stance·goal·rigor·non_goals)" || no "T2 필드 누락"

# T3 (AC2): 하드코딩 0 — 페르소나 '정의 값'에만 검사(주석·제외목록 제외)
python3 -c "
import yaml, re
d = yaml.safe_load(open('$P'))
vals = ' '.join(str(v) for p in d['personas'].values() for v in p.values())
bad = re.search(r'\bSAR\b|평택|Pyeongtaek|원격탐사 전문가|수문학 전문가', vals)
assert not bad, bad
print('ok')" >/dev/null 2>&1 && ok "T3 도메인 하드코딩 0(페르소나 값)" || no "T3 도메인 하드코딩 발견"
python3 -c "
import yaml, re
d = yaml.safe_load(open('$P'))
vals = ' '.join(str(v) for p in d['personas'].values() for v in p.values())
bad = re.search(r'\b(GD|RS|EXJ)\b|Journal of Hydrology|Geoscience Frontiers', vals)
assert not bad, bad
print('ok')" >/dev/null 2>&1 && ok "T3b 저널 하드코딩 0(페르소나 값·슬롯만)" || no "T3b 저널 하드코딩 발견"

# T4 (AC2): {domain}·{journal} 슬롯 사용
grep -q "{domain}" "$P" && grep -q "{journal}" "$P" && ok "T4 {domain}·{journal} 슬롯 존재" || no "T4 슬롯 없음"

# T5 (AC3): 리뷰 페르소나 collusion 방지·독립평가 문구
python3 -c "
import yaml;d=yaml.safe_load(open('$P'))
for r in ['self-review','peer-review']:
    du=d['personas'][r]['domain_use']+d['personas'][r].get('non_goals','')
    assert ('동조' in du or 'collusion' in du or '독립' in du), r
print('ok')" >/dev/null 2>&1 && ok "T5 리뷰 페르소나 독립평가·collusion 금지 문구" || no "T5 collusion 방지 문구 없음"

# T6 (AC5·F7): 기계적 3개 제외 — persona frontmatter + BODY(personas.yaml·composition·role ID) 참조 0
python3 -c "import yaml;d=yaml.safe_load(open('$P'));ex=d['excluded_mechanical'];assert all(k in ex for k in ['claim-evidence-audit','multi-model-research','writing-planner']);print('ok')" >/dev/null 2>&1 && ok "T6a personas.yaml 제외목록 3종" || no "T6a 제외목록 누락"
EXOK=1
for s in harness-claim-evidence-audit multi-model-research harness-writing-planner; do
  F="$SK/$s/SKILL.md"; [ -f "$F" ] || continue
  grep -qE "^persona:" "$F" && EXOK=0
  # F7: body에 페르소나 참조 누수도 차단
  grep -qE "personas\.yaml|persona-composition|persona: (peer-review|self-review|reviewer-response)" "$F" && EXOK=0
done
[ "$EXOK" = "1" ] && ok "T6b 기계적3개 persona frontmatter+body 참조 0(F7)" || no "T6b 기계적 스킬에 persona 누수"

# T7 (AC4·F1): 역할 스킬 7개(6+self-review) frontmatter persona 참조 — self-review 포함
CNT=0
for s in harness-paper-self-review harness-paper-peer-review harness-reviewer-response harness-writing-polish harness-patent-assist harness-report-writer harness-slide-writer; do
  grep -qE "^persona: " "$SK/$s/SKILL.md" 2>/dev/null && CNT=$((CNT+1))
done
[ "$CNT" = "7" ] && ok "T7 역할 스킬 7개(6+self-review) persona 배선(7/7·F1)" || no "T7 배선 $CNT/7"

# T8 (AC6): 조합 규칙 문서 존재 + fallback + 조합 스크립트 0
[ -f "$C" ] && grep -q "Fallback" "$C" && ! ls "$CORE"/persona_resolve.py >/dev/null 2>&1 && ok "T8 조합문서+fallback, 조합스크립트 0(문서기반)" || no "T8 조합문서/스크립트"

# T9 (AC7): self≠peer 독립성 (다른 stance)
python3 -c "import yaml;d=yaml.safe_load(open('$P'));s=d['personas']['self-review']['stance'];p=d['personas']['peer-review']['stance'];assert s!=p and '독립' in p;print('ok')" >/dev/null 2>&1 && ok "T9 self(harsh)≠peer(독립) 구분" || no "T9 self/peer 미구분"

# T10 (AC8·F5): 범용성 — 실제로 임시 저널·도메인 추가 → personas.yaml·스킬 diff 0(무코드 확장) 시연
JP="$CORE/journal-profiles.yaml"
P_BEFORE=$(md5sum "$P" | cut -d' ' -f1)
S_BEFORE=$(md5sum "$SK/harness-paper-peer-review/SKILL.md" | cut -d' ' -f1)
JP_BAK="$TMP/jp.bak"; cp "$JP" "$JP_BAK"
# 임시 새 저널 프로필 추가(파일 수정) — 조합이 이걸 {journal}로 받는지
cat >> "$JP" <<'EOF'

  __SMOKE_FAKEJRN__:
    full_name: "Smoke Test Journal"
    language: en
    weights: {novelty: 1.5}
EOF
# 검증: 새 저널 추가 후에도 personas.yaml·스킬 unchanged(범용=무코드) + 새 저널이 프로필에 인식
JP_HAS=$(python3 -c "import yaml;d=yaml.safe_load(open('$JP'));print('__SMOKE_FAKEJRN__' in d.get('profiles',{}))" 2>/dev/null)
P_AFTER=$(md5sum "$P" | cut -d' ' -f1)
S_AFTER=$(md5sum "$SK/harness-paper-peer-review/SKILL.md" | cut -d' ' -f1)
cp "$JP_BAK" "$JP"   # 원복(임시 추가 제거)
if [ "$JP_HAS" = "True" ] && [ "$P_BEFORE" = "$P_AFTER" ] && [ "$S_BEFORE" = "$S_AFTER" ]; then
  ok "T10 범용성 실증(새 저널 추가→personas·스킬 diff 0, 무코드 확장)"
else
  no "T10 범용성(저널인식=$JP_HAS personas변경=$([ "$P_BEFORE" = "$P_AFTER" ]&&echo 0||echo 1) 스킬변경=$([ "$S_BEFORE" = "$S_AFTER" ]&&echo 0||echo 1))"
fi

# T11 (F3): collusion precedence 메커니즘 — composition에 역할우선·strip·정설관대금지
grep -q "역할 독립성이 도메인" "$C" && grep -qE "strip|무시·제거" "$C" && grep -q "정설이라 관대 금지" "$C" && ok "T11 collusion precedence 메커니즘(역할우선·strip·정설관대금지)" || no "T11 collusion 메커니즘 미흡"

# T12 (F4): golden 조합 예시 존재(drift 감지)
grep -q "Golden 조합 예시" "$C" && grep -qE "예시 A|예시 B" "$C" && ok "T12 golden 조합 예시(drift 감지)" || no "T12 golden 없음"

echo "=== 결과: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
