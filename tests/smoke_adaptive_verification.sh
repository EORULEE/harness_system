#!/usr/bin/env bash
# smoke_adaptive_verification — r5 adaptive 검증 (T1-T27). 읽기전용·결정적.
set -uo pipefail
FO="$(cd "$(dirname "$0")/.." && pwd)"
LC="$FO/.claude/skills/_loop-core"
AR="python3 $FO/scripts/adaptive_verification_router.py"
PR="python3 $FO/scripts/pair_router.py"
P=0; F=0; ok(){ echo "  ✓ $1"; P=$((P+1)); }; no(){ echo "  ✗ $1"; F=$((F+1)); }
jq_get(){ python3 -c "import sys,json;d=json.load(sys.stdin);print(d$1)"; }

# T1 상태조회 → one-shot·pair0·no gate
r=$($AR --task-type simple-question --domains 1); m=$(echo "$r"|jq_get "['review_plan']['validation_mode']"); pc=$(echo "$r"|jq_get "['review_plan']['selected_pairs_count']"); hg=$(echo "$r"|jq_get "['review_plan']['human_gate']")
[ "$m" = one-shot ] && [ "$pc" = 0 ] && [ "$hg" = False ] && ok "T1 상태조회 one-shot·pair0·gate없음" || no "T1 ($m/$pc/$hg)"
# T2 작은 코드 버그 + 결정적 → deterministic-only·fix≤3·no cross-domain
r=$($AR --task-type code-bugfix --domains 1 --deterministic-verifier); m=$(echo "$r"|jq_get "['review_plan']['validation_mode']"); fx=$(echo "$r"|jq_get "['review_plan']['maximum_fix_iterations']"); tp=$(echo "$r"|jq_get "['review_plan']['review_topology']")
[ "$m" = deterministic-only ] && [ "$fx" = 3 ] && [ "$tp" = none ] && ok "T2 코드버그 deterministic·fix3·cross없음" || no "T2 ($m/$fx/$tp)"
# T3 InSAR coherence 단일도메인 전문 → intra-pair·2-pass
r=$($AR --task-type code-feature --domains 1); m=$(echo "$r"|jq_get "['review_plan']['review_topology']"); pa=$(echo "$r"|jq_get "['review_plan']['maximum_passes']")
[ "$m" = intra-pair ] && [ "$pa" = 2 ] && ok "T3 단일도메인 intra-pair·2-pass" || no "T3 ($m/$pa)"
# T4 InSAR+화산 복합 → cross-domain·pair2
r=$($AR --task-type research --domains 2 --interdependent); tp=$(echo "$r"|jq_get "['review_plan']['review_topology']"); pc=$(echo "$r"|jq_get "['review_plan']['selected_pairs_count']")
[ "$tp" = cross-domain ] && [ "$pc" = 2 ] && ok "T4 InSAR+화산 cross-domain·pair2" || no "T4 ($tp/$pc)"
# T5 SOC+위성+DL → pair3(최대)
r=$($AR --task-type research --domains 3 --interdependent); pc=$(echo "$r"|jq_get "['review_plan']['selected_pairs_count']")
[ "$pc" = 3 ] && ok "T5 SOC+위성+DL pair3(최대)" || no "T5 ($pc)"
# T6 다른 SOC 의미 → project_scope_conflict, 조용한 override 금지
grep -q "project_scope_conflict" "$LC/schemas/project-glossary-schema.yaml" && grep -q "조용히 덮지 않" "$LC/schemas/project-glossary-schema.yaml" && ok "T6 SOC project_scope_conflict·조용한override금지" || no "T6"
# T7 취약성+위성+사회경제 → cross-domain pair≤3
r=$($AR --task-type research --domains 3 --interdependent); tp=$(echo "$r"|jq_get "['review_plan']['review_topology']")
[ "$tp" = cross-domain ] && ok "T7 취약성+위성+사회경제 cross-domain" || no "T7 ($tp)"
# T8 논문 내부 초안 → Codex 강제 없음
r=$($AR --task-type writing --domains 1); cm=$(echo "$r"|jq_get "['review_plan']['cross_model_reviewer']")
[ "$cm" = none ] && ok "T8 내부 초안 Codex 강제없음" || no "T8 ($cm)"
# T9 외부 제출 최종본 → Codex1·human gate
r=$($AR --task-type writing --domains 2 --external-submission); cm=$(echo "$r"|jq_get "['review_plan']['cross_model_reviewer']"); hg=$(echo "$r"|jq_get "['review_plan']['human_gate']")
[ "$cm" = codex-1x ] && [ "$hg" = True ] && ok "T9 외부제출(단독) Codex1·human gate" || no "T9 ($cm/$hg)"
# T10 딥러닝 실험 → human gate (Mode C 자동 0은 정책)
r=$($AR --task-type experiment --domains 1 --irreversible); hg=$(echo "$r"|jq_get "['review_plan']['human_gate']")
if [ "$hg" = True ]; then ok "T10 실험 human gate(Mode C 자동실행은 별도 정책)"; else no "T10 ($hg)"; fi
# T11 배포 → human gate critical
r=$($AR --task-type deployment --domains 1 --irreversible --public-impact); hg=$(echo "$r"|jq_get "['review_plan']['human_gate']"); ti=$(echo "$r"|jq_get "['risk_assessment']['tier']")
[ "$hg" = True ] && [ "$ti" = critical ] && ok "T11 배포 human gate·critical" || no "T11 ($hg/$ti)"
# T12 Python 버전 → pair0
r=$($AR --task-type fact-check --domains 1); pc=$(echo "$r"|jq_get "['review_plan']['selected_pairs_count']")
[ "$pc" = 0 ] && ok "T12 단순사실 pair0" || no "T12 ($pc)"
# T13 역할 중복 → 중복 pair 0 (pair_router dedup)
r=$($PR --topology cross-domain --active-layers "method_domains,method_domains,science_domains"); c=$(echo "$r"|jq_get "['count']")
[ "$c" = 2 ] && ok "T13 역할중복 dedup(3입력→2)" || no "T13 ($c)"
# T14 기존 upgrade → 기존 pair·overlay 보존
grep -q "기존 pair 전부 보존\|기존 pair·overlay 보존\|이름·역할·권한 임의변경 금지\|임의변경 금지" "$LC/schemas/pair-topology-schema.yaml" && ok "T14 upgrade 기존 pair 보존" || no "T14"
# T15 x-agent 권한 → Write/Edit 0
grep -q "Write/Edit 금지" "$LC/schemas/pair-topology-schema.yaml" && ok "T15 x-agent Write/Edit 금지" || no "T15"
# T16 iteration → 동일실패2 HOLD·전역5
r=$($AR --task-type code-feature --domains 1); sf=$(echo "$r"|jq_get "['limits']['same_failure_limit']"); gm=$(echo "$r"|jq_get "['limits']['maximum_global_iterations']")
[ "$sf" = 2 ] && [ "$gm" = 5 ] && ok "T16 동일실패2·전역5(circuit_breaker)" || no "T16 ($sf/$gm)"
# T17 결정적 verifier 우선
grep -q "결정적 검증 우선\|에이전트 의견보다 결정적" "$LC/adaptive-verification-policy.md" && ok "T17 결정적 verifier 우선" || no "T17"
# T18 Codex vs x-agent 구분
grep -q "Codex 결과는 정본 아님" "$LC/cross-domain-review-policy.yaml" && ok "T18 Codex≠정본(x-agent와 구분)" || no "T18"
# T19 ledger domain·pair·pass·stop 기록 (loop_ledger 재사용)
grep -qE "^import loop_ledger|import loop_ledger as" "$FO/scripts/adaptive_verification_router.py" && grep -qE "^import circuit_breaker|import circuit_breaker as" "$FO/scripts/adaptive_verification_router.py" && ok "T19 circuit_breaker·loop_ledger 실제 import 재사용" || no "T19"
# T20 secret residual 0 (신규 파일)
n=$(grep -rohE "EXAMPLE_API_KEY=[A-Za-z0-9]|ghp_[A-Za-z0-9]{20}|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}" "$FO/scripts/adaptive_verification_router.py" "$FO/scripts/pair_router.py" "$LC/adaptive-verification-policy.md" "$LC/cross-domain-review-policy.yaml" "$LC"/schemas/*.yaml 2>/dev/null | wc -l)
[ "$n" -eq 0 ] && ok "T20 신규파일 secret 0" || no "T20 ($n)"

  echo "  ⊘ T21-T27 SKIP — post-r3 자산(fleet/kb/design)은 public core 제외"
echo "[adaptive] PASS $P / FAIL $F"; [ $F -eq 0 ]
