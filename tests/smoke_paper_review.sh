#!/usr/bin/env bash
# smoke_paper_review.sh — 논문 리뷰 스킬 3종 정적 검증 (계약 contract-paper-review-skills-20260706 AC1~AC9)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
P=0; F=0
pass(){ echo "  ✓ $1"; P=$((P+1)); }
fail(){ echo "  ✗ $1 :: $2"; F=$((F+1)); }
CORE="$ROOT/.claude/skills/_paper-review-core"
S1="$ROOT/.claude/skills/harness-paper-self-review/SKILL.md"
S2="$ROOT/.claude/skills/harness-paper-peer-review/SKILL.md"
S3="$ROOT/.claude/skills/harness-reviewer-response/SKILL.md"

# AC1: 3 SKILL.md + disable-model-invocation:true + draft-only
for s in "$S1" "$S2" "$S3"; do
  n=$(basename "$(dirname "$s")")
  [ -f "$s" ] && grep -q "disable-model-invocation: true" "$s" && grep -q "draft-only" "$s" \
    && pass "AC1 $n (존재·명시호출·draft-only)" || fail "AC1 $n" "누락"
done

# AC2: 모델명 리터럴 0
LIT=$(grep -hEc 'claude-opus|claude-fable|gpt-5|gemini-[0-9]' "$S1" "$S2" "$S3" 2>/dev/null | paste -sd+ | bc)
[ "${LIT:-0}" = "0" ] && pass "AC2 모델명 리터럴 0" || fail "AC2" "리터럴 $LIT건"

# AC3: 근거 강제 — 템플릿 3종 위치 컬럼 + 스킬 '근거 없는 지적 금지'(T1: 인용→evidence.type 일반화)
T=0
for t in self-review peer-review response-letter; do
  grep -q "위치" "$CORE/report-templates/$t.md" && T=$((T+1))
done
[ "$T" = "3" ] && pass "AC3a 템플릿 3종 위치 필드" || fail "AC3a" "$T/3"
G=$(grep -lE "인용 없는 지적 금지|근거 없는 지적 금지|근거 없는 반박" "$S1" "$S2" "$S3" | wc -l)
[ "$G" = "3" ] && pass "AC3b 스킬 3종 근거강제 문구(인용 또는 evidence.type 근거)" || fail "AC3b" "$G/3"

# AC4: rubric 7차원 — rubric 파일 + 리포트 템플릿(self·peer) 7차원 표 (SCIE_Writing 병합 2026-07-06)
for d in novelty methodology stats_results figures_tables references writing_clarity domain_interpretation ethics_reproducibility; do
  grep -q "$d" "$CORE/review-rubric.md" || fail "AC4 rubric" "$d 없음"
done
grep -c "$d" "$CORE/review-rubric.md" >/dev/null && pass "AC4a rubric 8차원 정의"
for t in self-review peer-review; do
  C=$(grep -cE "novelty|methodology|stats_results|figures_tables|references|writing_clarity|domain_interpretation|ethics_reproducibility" "$CORE/report-templates/$t.md")
  [ "$C" -ge 8 ] && pass "AC4b $t 템플릿 8차원($C)" || fail "AC4b $t" "$C<8"
done

# AC5: codex 필수 게이트 (probe + HOLD)
G=$(grep -lE "codex_probe" "$S1" "$S2" "$S3" | wc -l); H=$(grep -liE "HOLD" "$S1" "$S2" "$S3" | wc -l)
[ "$G" = "3" ] && [ "$H" = "3" ] && pass "AC5 codex 필수(probe+HOLD) 3/3" || fail "AC5" "probe $G/3 HOLD $H/3"

# AC6: journal-profiles.yaml — 3 프로필 + language
python3 - "$CORE/journal-profiles.yaml" <<'PYEOF' && pass "AC6 프로필 3종+language" || fail "AC6" "yaml 검증 실패"
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
ps = d["profiles"]
assert len(ps) >= 3, f"프로필 {len(ps)}<3"
for k, v in ps.items():
    assert "language" in v, f"{k} language 없음"
assert ps["EXJ"]["language"] == "ko"
PYEOF

# AC7: 입력 명세 — ①소스 ②PDF비전 ③심사평+원고
grep -qE "md / tex / docx|md/tex/docx" "$S1" && pass "AC7a ①소스 입력" || fail "AC7a" "명세 없음"
grep -q "dpi≈200\|dpi200" "$S2" && pass "AC7b ②PDF 비전(dpi200)" || fail "AC7b" "명세 없음"
grep -qE "심사평.*원고|텍스트.*PDF" "$S3" && pass "AC7c ③심사평+원고" || fail "AC7c" "명세 없음"

# AC8: writing-router 3 트리거
R="$ROOT/.claude/skills/harness-writing-router/SKILL.md"
for sk in harness-paper-self-review harness-paper-peer-review harness-reviewer-response; do
  grep -q "$sk" "$R" && pass "AC8 router: $sk" || fail "AC8" "$sk 미등록"
done

# AC9: 재사용 배선 — claim-evidence-audit·Zotero(날조 금지)·wiki
for s in "$S1" "$S2"; do
  n=$(basename "$(dirname "$s")")
  grep -q "claim-evidence-audit" "$s" && grep -qE "Zotero" "$s" && grep -q "wiki" "$s" \
    && pass "AC9 $n 배선 3종" || fail "AC9 $n" "배선 누락"
done
grep -qE "Zotero" "$S3" && grep -q "wiki" "$S3" && pass "AC9 reviewer-response 배선" || fail "AC9 r-r" "누락"


# AC12: Strengths 섹션 (균형·공정 — SCIE_Writing 병합)
for t in self-review peer-review; do
  grep -q "## Strengths" "$CORE/report-templates/$t.md" && pass "AC12 $t Strengths 섹션" || fail "AC12 $t" "없음"
done
grep -q "Strengths" "$CORE/review-rubric.md" && pass "AC12 rubric 균형원칙" || fail "AC12 rubric" "없음"

# AC13: 1-10 점수척도 + 정량 판정기준 + Critical 3-tier
grep -q "9-10" "$CORE/review-rubric.md" && grep -q "정량 판정 기준" "$CORE/review-rubric.md" \
  && pass "AC13a 점수척도+정량기준" || fail "AC13a" "없음"
grep -q "critical" "$CORE/review-rubric.md" && pass "AC13b 3-tier(critical)" || fail "AC13b" "없음"
for t in self-review peer-review; do
  grep -q "## Critical" "$CORE/report-templates/$t.md" && grep -q "점수(1-10)" "$CORE/report-templates/$t.md" \
    && pass "AC13c $t Critical+점수컬럼" || fail "AC13c $t" "없음"
done

# AC14: 실행 체크리스트 + ethics 프로필 가중
grep -q "실행 체크리스트" "$CORE/review-rubric.md" && pass "AC14a 실행 체크리스트" || fail "AC14a" "없음"
python3 -c "
import yaml
d = yaml.safe_load(open('$CORE/journal-profiles.yaml'))
assert 'ethics_reproducibility' in d['default']['weights']" && pass "AC14b ethics 가중" || fail "AC14b" "없음"


# AC15: Editor-prompt 병합 (Questions to Authors · Scope Fit · scope 필드 · 메커니즘 깊이) 2026-07-06
for t in self-review peer-review; do
  grep -q "## Questions to Authors" "$CORE/report-templates/$t.md" && pass "AC15a $t Questions 섹션" || fail "AC15a $t" "없음"
done
grep -q "Scope Fit" "$CORE/report-templates/self-review.md" && grep -q "desk-screening" "$CORE/report-templates/self-review.md" \
  && pass "AC15b self-review ScopeFit+desk" || fail "AC15b" "없음"
python3 -c "
import yaml
d = yaml.safe_load(open('$CORE/journal-profiles.yaml'))
for k in ('EXJ','RS','GD'): assert 'scope' in d['profiles'][k], k" && pass "AC15c scope 필드 3/3" || fail "AC15c" "누락"
grep -q "메커니즘을 깊이" "$CORE/review-rubric.md" && pass "AC15d 메커니즘 깊이" || fail "AC15d" "없음"


# AC16: 페르소나 상향(수석 편집위원) + 위협모델링 체크 5건 (2026-07-06)
grep -q "수석 편집위원" "$S1" && pass "AC16a self-review 편집위원 페르소나" || fail "AC16a" "없음"
grep -q "위협모델링 체크" "$CORE/review-rubric.md" && grep -q "fold-wise" "$CORE/review-rubric.md" \
  && grep -q "pseudo-replication" "$CORE/review-rubric.md" && grep -q "명칭-구현 충실도" "$CORE/review-rubric.md" \
  && pass "AC16b 위협모델링 5체크" || fail "AC16b" "누락"

echo "  → paper_review $P/$((P+F)) PASS"
[ "$F" = "0" ]
