#!/usr/bin/env bash
# smoke_code_claim_evidence — dev-discipline 'code-claim evidence gate'(Layer 1·2) 파일럿 검증.
# 읽기전용(fixture=mktemp). assertion 삭제/skip/강제PASS 금지.
# 대상: scripts/code_claim_lint.py + 규율 정본 + 배선(cheatsheet·evidence표·trigger-policy).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINT="$ROOT/scripts/code_claim_lint.py"
DDC="$ROOT/.claude/skills/_dev-discipline-core"
RULES="$DDC/code-claim-evidence-rules.md"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
P=0; F=0; ok(){ echo "  ✓ $1"; P=$((P+1)); }; no(){ echo "  ✗ $1"; F=$((F+1)); }
run(){ python3 "$LINT" "$1" >/dev/null 2>&1; echo $?; }   # exit code만(pipefail 무관)

# ── Layer 2 lint 동작 ──
# T1 인용 없는 코드-동작 주장 → flag(exit 1)
printf 'compute_lst 는 200x200 crop 전체의 평균을 계산한다.\n' > "$TMP/bad.md"
[ "$(run "$TMP/bad.md")" = 1 ] && ok "T1 무근거 코드-동작 주장 → flag(exit1)" || no "T1 bad"
# T2 file:line 인용 있는 동작 주장 → pass(exit 0)
printf 'compute_lst 는 img_ref 마스크만 평균을 계산한다 (geoai.py:1365).\n' > "$TMP/good.md"
[ "$(run "$TMP/good.md")" = 0 ] && ok "T2 인용 있는 주장 → pass(exit0)" || no "T2 good"
# T3 코드-동작 주장 아님(중립 prose) → pass
printf '이번 배포는 사용자 승인 후 진행하며 일정은 내일입니다.\n' > "$TMP/neutral.md"
[ "$(run "$TMP/neutral.md")" = 0 ] && ok "T3 중립 prose → pass(exit0)" || no "T3 neutral"
# T4 fenced code block 안의 주장은 무시(prose 아님)
printf '설명입니다.\n```\ncompute_lst 는 평균을 계산한다\n```\n끝.\n' > "$TMP/fence.md"
[ "$(run "$TMP/fence.md")" = 0 ] && ok "T4 fenced code block 내부는 스캔 제외" || no "T4 fence"
# T5 규범/메타 문장("~해야/금지/류")은 주장 아님 → pass
printf '"X 가 Y 를 계산한다" 류 모든 동작 주장은 인용을 동반한다.\n' > "$TMP/meta.md"
[ "$(run "$TMP/meta.md")" = 0 ] && ok "T5 규범/메타 서술 → 주장 아님(FP 억제)" || no "T5 meta"
# T6 stdin('-') 입력 지원
printf 'parse_x 는 토큰을 반환한다.\n' | python3 "$LINT" - >/dev/null 2>&1
[ "$?" = 1 ] && ok "T6 stdin('-') 입력 + 무근거 flag" || no "T6 stdin"
# T7 read-only: lint 가 입력/디스크 수정 안 함
grep -qE "open\([^)]*['\"]w|os.remove|rmtree|\.unlink\(|write_text" "$LINT" && no "T7 lint write 호출 있음" || ok "T7 lint read-only(write/destructive 0)"

# ── 정본·배선 ──
# T8 규율 정본 존재
[ -f "$RULES" ] && ok "T8 code-claim-evidence-rules.md 존재" || no "T8 rules 없음"
# T9 Layer 1(serena)·2(evidence)·3(cross-model) 명시
grep -q "serena" "$RULES" && grep -q "file:line" "$RULES" && grep -qi "cross-model\|codex" "$RULES" && ok "T9 3층(serena·evidence·cross-model) 명시" || no "T9 층 누락"
# T10 cheatsheet 가 규율 파일 링크(배선)
grep -q "code-claim-evidence-rules\|code-claim evidence" "$DDC/dev-discipline-cheatsheet.md" && ok "T10 cheatsheet 배선" || no "T10 cheatsheet 미배선"
# T11 evidence-before-completion 표에 코드-동작 행 추가
grep -q "code-claim-evidence-rules\|코드 동작\|생산 함수" "$DDC/evidence-before-completion-rules.md" && ok "T11 evidence표 행 추가" || no "T11 evidence표 미반영"
# T12 trigger-policy 에 code-analysis 트리거
grep -qi "code-claim\|코드-동작\|코드 분석\|생산 함수" "$DDC/dev-discipline-trigger-policy.md" && ok "T12 trigger-policy 트리거" || no "T12 trigger 미반영"
# T13 정본 memory 링크(feedback_read_producing_function)
grep -q "feedback_read_producing_function" "$RULES" && ok "T13 정본 memory 링크" || no "T13 memory 링크 없음"

echo "[code-claim-evidence] PASS $P / FAIL $F"; [ $F -eq 0 ]
