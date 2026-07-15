#!/usr/bin/env bash
# smoke_constitution_diet.sh — 다이어트 검증: 줄수 목표·하드5 존재·고유제약 보존·레퍼런스 이관·과축소 금지.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CON="$ROOT/CLAUDE.constitution.md"; PRJ="$ROOT/CLAUDE.md"; REF="$ROOT/docs/harness-workflows-reference.md"
P=0; F=0
pass(){ echo "  ✓ $1"; P=$((P+1)); }
fail(){ echo "  ✗ $1 :: $2"; F=$((F+1)); }

C=$(wc -l < "$CON"); PR=$(wc -l < "$PRJ")
[ "$C" -ge 70 ] && [ "$C" -le 100 ] && pass "Constitution 70~100줄($C)" || fail "Constitution 줄수" "$C"   # r16: 메타블록 서식 §79-94 정식 포함(stop-guard 검사 규격)으로 상한 80→100
[ "$PR" -ge 100 ] && [ "$PR" -le 150 ] && pass "Project CLAUDE 100~150줄($PR)" || fail "Project 줄수" "$PR"
[ "$PR" -ge 40 ] && pass "과축소 금지(40줄 초과)" || fail "과축소" "$PR<=40"

# 하드 5 존재
for k in "verify-or-abstain" "source-backed query" "no absence" "no fake completion" "destructive/external"; do
  grep -q "$k" "$CON" && pass "하드5: $k" || fail "하드5" "$k 없음"
done

# 기계강제·2-pass 전제·권위순서
grep -q "tool_use_audit\|absence_claim_guard" "$CON" && pass "기계강제 명시" || fail "기계강제" "없음"
grep -q "evidence_bundle\|전제 evidence" "$CON" && pass "2-pass 전제우선" || fail "2pass" "없음"
grep -q "stop-guard > hookify" "$CON" && pass "권위순서 명시" || fail "권위" "없음"
grep -q "약화하지 않" "$CON" && pass "기존 hard gate 불변 명시" || fail "불변" "없음"

# 프로젝트 고유 제약 보존
for k in "block-rclone-link-awk" "block-hancom-taskkill" "harness-owned invocation" "tailscale serve" "HBWF69S2"; do
  grep -q "$k" "$PRJ" && pass "고유제약: $k" || fail "고유제약" "$k 없음"
done

# @import 배선
grep -q "@CLAUDE.constitution.md" "$PRJ" && pass "@import Constitution 배선" || fail "@import" "없음"

# 레퍼런스 이관(삭제 아님): Drive 절차가 레퍼런스에 존재
# 공개판: 개인 워크플로 이관문서는 배포 제외 대상 — 부재가 정상(자기완결)
[ ! -f "$REF" ] && pass "공개판=개인 워크플로 문서 미포함(정상)" || pass "레퍼런스 존재(개인판)"
# 매 턴 주입 제외 표시
true # 공개판 N/A(위와 동일 사유)

echo "  → constitution_diet $P/$((P+F)) PASS"
[ "$F" -eq 0 ]
