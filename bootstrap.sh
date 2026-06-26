#!/usr/bin/env bash
# bootstrap — 요구사항 점검 + 검증 smoke 실행
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
echo "== 요구사항 =="; command -v python3 >/dev/null && echo "  python3: $(python3 --version 2>&1)" || { echo "  python3 없음"; exit 1; }
command -v node >/dev/null && echo "  node: $(node -v)" || echo "  node 없음(훅 비활성; core smoke 는 동작)"
echo "== 검증 smoke =="; P=0;F=0
for s in tests/smoke_*.sh; do bash "$s" >/dev/null 2>&1 && { echo "  PASS $(basename "$s" .sh)"; P=$((P+1)); } || { echo "  FAIL $(basename "$s" .sh)"; F=$((F+1)); }; done
echo "== 결과: PASS=$P FAIL=$F =="; [ $F -eq 0 ] && echo "OK — 시스템 동작 확인" || echo "일부 실패(환경 차이 가능)"
