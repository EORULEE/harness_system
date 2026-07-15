#!/usr/bin/env bash
# smoke_paper_final_check.sh — paper_final_check.py 정적+동작 검증 (계약 AC1~6·AC12, codex F-10/F-11 보강)
set -u
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/paper_final_check.py"
PROF="$(dirname "$0")/../.claude/skills/_paper-review-core/journal-profiles.yaml"; [ -f "$PROF" ] || PROF="$HOME/.claude/skills/_paper-review-core/journal-profiles.yaml"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
# 특정 체크 status 추출(json)
chk(){ python3 "$SCRIPT" x.docx --md "$1" ${3:+--journal $3} --profiles "$PROF" --json 2>/dev/null \
  | python3 -c "import sys,json;print([r['status'] for r in json.load(sys.stdin)['results'] if r['check']=='$2'][0])" 2>/dev/null; }
verdict(){ python3 "$SCRIPT" x.docx --md "$1" ${2:+--journal $2} --profiles "$PROF" >/dev/null 2>&1; echo $?; }

echo "=== smoke_paper_final_check ==="

# T1 (AC1)
[ -f "$SCRIPT" ] && python3 "$SCRIPT" -h >/dev/null 2>&1 && ok "T1 존재·--help" || no "T1"
# T2 (AC6)
grep -iqE "flood|평택|pyeongtaek" "$SCRIPT" && no "T2 flood 리터럴" || ok "T2 flood 특정값 0"

# T3: 깨끗한 영문 = PASS
cat > "$TMP/clean.md" <<'EOF'
Abstract
Clean english abstract with enough words here to be safe and totally fine indeed.
1. Introduction
See Figure 1, Table 1. Figure 2 too.
Figure 1. a.
Figure 2. b.
Table 1. c.
EOF
[ "$(verdict "$TMP/clean.md")" = "0" ] && ok "T3 clean=PASS" || no "T3 clean 오탐"

# T4 (AC3): 한글 수식 잔재(영문 저널) → HARD FAIL
cat > "$TMP/kr.md" <<'EOF'
Abstract
English body mostly here fine.
(5) $D = {AUC}_{공간} - x$
Figure 1. cap.
EOF
[ "$(chk "$TMP/kr.md" lang_residue RS)" = "FAIL" ] && ok "T4 한글수식 영문저널→HARD" || no "T4"

# T5 (AC5): placeholder → HARD FAIL
printf 'Abstract\nEnglish text fine.\nTODO: fill\nFigure 1. c.\n' > "$TMP/ph.md"
[ "$(chk "$TMP/ph.md" placeholder)" = "FAIL" ] && ok "T5 placeholder→HARD" || no "T5"

# T6 (AC2): parity 참조 Figure2 캡션없음 → HARD FAIL
printf 'Abstract\nEnglish fine.\nSee Figure 2.\nFigure 1. only one.\n' > "$TMP/par.md"
[ "$(chk "$TMP/par.md" parity)" = "FAIL" ] && ok "T6 parity 결함→HARD" || no "T6"

# T7 (F-10): 진짜 오탐 토큰 — 'configuration Table 2' 접두, 정상 참조는 PASS
cat > "$TMP/fp.md" <<'EOF'
Abstract
English. The configuration Table 1 and subFigure notes. See Table 1 and Figure 1.
Figure 1. cap.
Table 1. cap.
EOF
[ "$(chk "$TMP/fp.md" parity)" = "PASS" ] && ok "T7 parity 오탐억제(configuration/subFigure)" || no "T7 오탐"

# T8 (AC4): 저널 초록한도 초과 → WARN(경고, exit0)
{ echo "Abstract"; python3 -c "print(' '.join(['word']*250))"; echo "1. Introduction"; echo "See Figure 1."; echo "Figure 1. c."; } > "$TMP/long.md"
[ "$(chk "$TMP/long.md" abstract_len RS)" = "WARN" ] && ok "T8 초록초과→WARN(exit0 유지)" || no "T8"

# T9 (F-06): 한글 저널(EXJ) 한글잔재 → WARN(투고 안 막음)
cat > "$TMP/ko.md" <<'EOF'
초록
본 연구는 한글 논문입니다. 그림 1을 참조.
그림 1. 캡션.
EOF
[ "$(verdict "$TMP/ko.md" EXJ)" = "0" ] && [ "$(chk "$TMP/ko.md" lang_residue EXJ)" = "WARN" ] && ok "T9 한글저널 한글→WARN(투고허용)" || no "T9 한글저널 막힘"

# T10 (F-05): 참고문헌 zone 한글은 영문저널서도 제외(오탐 안 함)
cat > "$TMP/bib.md" <<'EOF'
Abstract
Pure english body text here totally fine.
Figure 1. cap. See Figure 1.
References
Hong, G. (2020). 한국어 제목. Journal of Test.
EOF
[ "$(chk "$TMP/bib.md" lang_residue RS)" = "PASS" ] && ok "T10 참고문헌 한글 제외" || no "T10 서지 오탐"

# T11 (F-03): 범위 참조 'Figures 1-3' → 캡션 3개 있으면 PASS
cat > "$TMP/rng.md" <<'EOF'
Abstract
English fine. See Figures 1-3 for results.
Figure 1. a.
Figure 2. b.
Figure 3. c.
EOF
[ "$(chk "$TMP/rng.md" parity)" = "PASS" ] && ok "T11 범위 Figures 1-3 파싱" || no "T11 범위 미파싱"

# T12 (F-01): 영문 Eq. 참조 카운트 — Eq. 5 참조하나 수식(5) 없음 → HARD
cat > "$TMP/eq.md" <<'EOF'
Abstract
English fine. As shown in Eq. 5 the result holds.
(1) $y = x$
Figure 1. c. See Figure 1.
EOF
[ "$(chk "$TMP/eq.md" parity)" = "FAIL" ] && ok "T12 영문 Eq.5 미존재→HARD" || no "T12 Eq 미카운트"

# T13 (F-11): caption_seq 결번 → WARN
cat > "$TMP/seq.md" <<'EOF'
Abstract
English fine. See Figure 1 and Figure 3.
Figure 1. a.
Figure 3. c.
EOF
[ "$(chk "$TMP/seq.md" caption_seq)" = "WARN" ] && ok "T13 캡션결번(2)→WARN" || no "T13"

echo "=== 결과: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
