#!/usr/bin/env bash
# smoke_review_doctype.sh — 리뷰 파이프라인 문서유형 일반화 스모크.
# 계약: _output/contracts/contract-review-doctype-generalization-20260710.md (AC1~AC6).
# 문서/config 기반(리뷰 실행=Claude) → 구조·정합·무회귀 정적 검사.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$REPO/.claude/skills/_paper-review-core"
DTP="$CORE/doc-type-profiles"
PASS=0; FAIL=0
ok(){ echo "  PASS $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL $1"; FAIL=$((FAIL+1)); }

echo "==== smoke_review_doctype ===="

# T1 (AC1) — report/generic 프로필 5필드·유효 yaml
five="purpose audience evaluation_axes structure_conventions success_criteria"
t1=1
for prof in report generic; do
  f="$DTP/$prof/profile.yaml"
  [ -f "$f" ] || { t1=0; continue; }
  python3 -c "import sys,yaml; d=yaml.safe_load(open('$f')); import sys as s; sys.exit(0 if all(k in d for k in '$five'.split()) and d['evaluation_axes'] else 1)" 2>/dev/null || t1=0
done
[ "$t1" -eq 1 ] && ok "T1 report·generic 프로필 5필드·유효 yaml" || no "T1 프로필 스키마"

# T2 (AC2) — report 특성: 실행권고 축 포함·논문 축(신규성/통계) 미포함
RA="$(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('$DTP/report/profile.yaml'))['evaluation_axes']))" 2>/dev/null)"
if echo "$RA" | grep -q "실행가능 권고" && ! echo "$RA" | grep -qE "신규성|통계 유의|재현성"; then
  ok "T2 report 축=실행권고 포함·논문 축(신규성/통계) 미포함(특성 중심)"; else no "T2 report 축 특성"; fi

# T3 (AC4 무회귀 ★) — review-rubric 8차원 intact + 공통코어+오버레이 섹션
RB="$CORE/review-rubric.md"
dims="novelty methodology stats_results figures_tables references writing_clarity domain_interpretation ethics_reproducibility"
d_ok=1; for d in $dims; do grep -q "$d" "$RB" || d_ok=0; done
if [ "$d_ok" -eq 1 ] && grep -q "공통 코어 + 특성 오버레이\|공통 코어 + 문서유형 오버레이\|공통 코어" "$RB" && grep -q "doc_type=paper" "$RB"; then
  ok "T3 ★무회귀: 8차원 intact + 공통코어/오버레이·paper 기본 명시"; else no "T3 무회귀(paper 8차원/코어)"; fi

# T4 (AC5 범용) — rubric 코어·스킬에 특정 유형 축 하드코딩 0(오버레이는 프로필에만)
# review-rubric 공통코어 섹션엔 'report'/'실행권고' 하드코딩 없어야(프로필이 정본)
if ! sed -n '/🆕 문서유형 일반화/,/^# (이하/p' "$RB" | grep -q "실행권고\|목표 달성도"; then
  ok "T4 범용: 유형별 축은 프로필에만(rubric 코어 하드코딩 0)"; else no "T4 rubric 코어에 유형축 하드코딩"; fi

# T5 (AC6 특성 중심) — persona-composition 3-b doc_type 단계·프로필 5필드 참조
PC="$CORE/persona-composition.md"
if grep -q "문서유형({doc_type}" "$PC" && grep -q "doc-type-profiles" "$PC" && grep -q "evaluation_axes 오버레이" "$PC"; then
  ok "T5 조합규칙에 doc_type 단계·특성 프로필 파생 명시"; else no "T5 persona-composition doc_type"; fi

# T6 (AC3) — 3 리뷰 스킬 doc_type 인식 노트
s_ok=1
for s in harness-paper-self-review harness-paper-peer-review harness-reviewer-response; do
  grep -q "doc_type) — 리뷰 일반화" "$REPO/.claude/skills/$s/SKILL.md" || s_ok=0
done
[ "$s_ok" -eq 1 ] && ok "T6 3 리뷰 스킬 doc_type 인식(미지정=paper 무회귀)" || no "T6 스킬 doc_type"

# T7 (AC5 범용 실증) — 프로필 추가만으로 신규 유형 가능(코어 무수정): generic이 fallback 축 보유
GA="$(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('$DTP/generic/profile.yaml'))['evaluation_axes']))" 2>/dev/null)"
echo "$GA" | grep -q "목적 적합성" && ok "T7 generic fallback 축(목적적합·근거·완결; 논리·명료는 공통코어) — 무유형 문서 대응" || no "T7 generic fallback"

# T8 (codex #6/#10 회귀) — fallback 안전: 미지정을 무조건 paper 로 두지 않음·추론→generic·journal paper전용
if grep -q "무조건 paper 로 두지 않는다" "$PC" && grep -q "추론 불가/모호 → \*\*generic\*\*" "$PC" && grep -q "journal-profiles 오버레이는 paper 전용" "$PC"; then
  ok "T8 fallback 안전(미지정≠paper·추론→generic·journal paper전용, 보고서 오평가 방지)"; else no "T8 fallback 안전"; fi

# ── T1 (유형 무관 개선) 케이스 — 계약 contract-review-t1-typeagnostic-20260710 ──

# T9 (AC-E1/E4) — 증거 유형 5종 + omission 인용 면제 + external_rule normative_basis
if grep -q "## 증거 규칙" "$RB" \
   && grep -q "excerpt" "$RB" && grep -q "omission" "$RB" && grep -q "cross_reference" "$RB" \
   && grep -q "visual" "$RB" && grep -q "external_rule" "$RB" \
   && grep -q "원문 인용 면제" "$RB" && grep -q "normative_basis" "$RB"; then
  ok "T9 증거 유형 5종 + omission 인용면제 + external_rule normative_basis"; else no "T9 증거 유형"; fi

# T10 (AC-N1/N2) — axis_state 4종 + 입력부족≠문서결함
if grep -q "## 축별 평가 상태" "$RB" && grep -q "not_assessed_missing_input" "$RB" \
   && grep -q "not_applicable" "$RB" && grep -qF "not_assessed_missing_input ≠ 낮은 점수" "$RB" \
   && grep -qE "남용 금지|커버리지 회피" "$RB"; then
  ok "T10 axis_state 4종 + 입력부족≠문서결함 + 남용가드"; else no "T10 axis_state"; fi

# T11 (AC-N3/N4) — not_assessed→verdict not_assessable 정합 + paper 무회귀
if grep -qF "not_assessed_missing_input → verdict = **not_assessable**" "$RB" \
   && grep -qF "8차원 커버리지 100% 무회귀" "$RB"; then
  ok "T11 not_assessed→verdict 정합 + paper 8차원 무회귀"; else no "T11 not_assessed 정합"; fi

# T12 (AC-C1/C2/C3) — context-profiles 스캐폴드 + 스키마 + journal 하위호환(무변경)
CP="$CORE/context-profiles/README.md"
if [ -f "$CP" ] && grep -q "schema: context_profile" "$CP" && grep -q "journal-profiles.yaml" "$CP" \
   && [ -f "$CORE/journal-profiles.yaml" ] && grep -q "schema: journal_profile" "$CORE/journal-profiles.yaml"; then
  ok "T12 context-profiles 스캐폴드+스키마+journal 하위호환(무변경)"; else no "T12 context-profiles"; fi

# T13 (AC-C4) — 4층 오버레이 우선순위 문서화
if grep -q "## 오버레이 우선순위" "$RB" && grep -q "generic fallback" "$RB"; then
  ok "T13 4층 오버레이 우선순위 문서화"; else no "T13 우선순위"; fi

# ── T2 (slide·proposal 프로필 — 실문서 특성분석 기반) ──

# T14 — slide·proposal 프로필 5필드 + 유효 yaml + 논문 축 미이식 + not_assessed 규약
t14=1
for prof in slide proposal; do
  f="$DTP/$prof/profile.yaml"
  [ -f "$f" ] || { t14=0; continue; }
  python3 -c "import sys,yaml; d=yaml.safe_load(open('$f')); sys.exit(0 if all(k in d for k in '$five'.split()) and d['evaluation_axes'] else 1)" 2>/dev/null || t14=0
  grep -q "논문 rubric 8차원 이식 금지" "$f" || t14=0
  grep -q "not_assessed" "$f" || t14=0
done
[ "$t14" -eq 1 ] && ok "T14 slide·proposal 프로필 5필드·비이식·not_assessed 규약" || no "T14 T2 프로필"

# T15 — slide=delivery 분리(deck-only not_assessed) · proposal=외부기준 우선+required_inputs
if grep -q "실전달력" "$DTP/slide/profile.yaml" 2>/dev/null \
   && grep -q "required_inputs" "$DTP/proposal/profile.yaml" 2>/dev/null \
   && grep -q "공고문·RFP·배점표가 제공되면" "$DTP/proposal/profile.yaml" 2>/dev/null; then
  ok "T15 slide deck/delivery 분리 + proposal 외부기준 우선·required_inputs"; else no "T15 T2 특수 규약"; fi

# T16 — 추론 신호에 slide·proposal 추가(명시>추론>generic 불변)
if grep -q "발표 지표" "$PC" && grep -q "제안 지표" "$PC" && grep -q "추론 불가/모호 → \*\*generic\*\*" "$PC"; then
  ok "T16 doc_type 추론에 slide·proposal 신호(해소 순서 불변)"; else no "T16 추론 신호"; fi

echo "==== smoke 결과: PASS=$PASS  FAIL=$FAIL ===="
[ "$FAIL" -eq 0 ]
