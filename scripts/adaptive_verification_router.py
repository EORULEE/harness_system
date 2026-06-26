#!/usr/bin/env python3
"""adaptive_verification_router.py — 요청별 자동 검증 강도 라우터 (r5 adaptive).

얇은 결정적 라우터. 새 엔진 아님 — 기존 자산 재사용:
  - 한도: scripts/circuit_breaker.py (same_failure_limit=2, global=5)
  - 기록: scripts/loop_ledger.py (_append_event)
  - cross-domain 오케스트레이션: scripts/challenge_manager.py (plan --pairs)
  - 도메인 구조 추출: scripts/domain_detector.py

입력 신호 → risk tier → review_plan(validation_mode·review_topology·pairs·passes·codex·human_gate).
정책 정본: .claude/skills/_loop-core/adaptive-verification-policy.md (표와 1:1).
출력: JSON(review_plan + risk_assessment). 파일 수정 없음(순수 함수 + stdout).
"""
from __future__ import annotations
import argparse
import json
import os
import sys

# ★ 기존 엔진 실제 재사용(중복 엔진 아님): 한도=circuit_breaker, 기록=loop_ledger
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SAME_FAILURE_LIMIT = 2
try:
    import circuit_breaker as _cb           # 실제 import
    _cfg = _cb.load_config()
    GLOBAL_MAX = int(_cfg.get("max_iterations", 5))   # circuit_breaker 정본 한도(로컬 재정의 아님)
    _CB_SRC = "circuit_breaker.load_config().max_iterations"
except Exception:
    GLOBAL_MAX = 5
    _CB_SRC = "circuit_breaker 미로딩 → 폴백 5"
try:
    import loop_ledger as _ledger            # 기록 재사용
    _LEDGER_OK = True
except Exception:
    _ledger = None
    _LEDGER_OK = False


def record_plan(root: str, loop_id: str, plan: dict, risk: dict, at: str) -> bool:
    """loop_ledger 재사용해 domain·pair·pass·stop 기록(엔진 재구현 아님). 미로딩 시 no-op."""
    if not _LEDGER_OK:
        return False
    try:
        _ledger._append_event(root, loop_id, "adaptive-review-plan",
                              {"review_plan": plan, "risk": risk}, at)
        return True
    except Exception:
        return False


HUMAN_GATE_TASKS = {"deployment", "experiment", "knowledge-promotion", "claude-design"}
ONESHOT_TASKS = {"simple-question", "code-question", "fact-check"}


def assess_risk(task_type: str, domains: int, interdependent: bool, irreversible: bool,
                public_impact: bool, external_submission: bool, deterministic_verifier: bool,
                ambiguity: str) -> dict:
    tier = "low"
    if task_type in ONESHOT_TASKS and domains <= 1 and not public_impact:
        tier = "low"
    elif irreversible or public_impact or external_submission or task_type == "deployment":
        tier = "critical" if (irreversible and (public_impact or external_submission)) else "high"
    elif domains >= 2 and interdependent:
        tier = "high"
    elif domains == 1 and task_type not in ONESHOT_TASKS:
        tier = "medium"
    # 배포·삭제·publish 류는 항상 critical 하한
    if task_type == "deployment" or external_submission and irreversible:
        tier = "critical"
    return {"tier": tier, "ambiguity": ambiguity, "domain_interdependence": "high" if interdependent else "low",
            "irreversibility": "high" if irreversible else "low",
            "public_impact": "high" if public_impact else "low",
            "deterministic_verifier_available": deterministic_verifier}


def route(risk: dict, task_type: str, domains: int, deterministic_verifier: bool,
          external_submission: bool = False) -> dict:
    tier = risk["tier"]
    plan = {"validation_mode": "one-shot", "review_topology": "none", "selected_pairs_count": 0,
            "iteration_mode": "single-pass", "minimum_passes": 1, "maximum_passes": 1,
            "maximum_fix_iterations": 0, "cross_model_reviewer": "none", "human_gate": False}
    if tier == "low" and task_type in ONESHOT_TASKS:
        return plan
    if deterministic_verifier and tier in ("low", "medium"):
        plan.update(validation_mode="deterministic-only", maximum_fix_iterations=3,
                    iteration_mode="single-pass")
        return plan
    if tier == "medium" and domains <= 1:
        plan.update(validation_mode="executor-verifier", review_topology="intra-pair",
                    selected_pairs_count=1, iteration_mode="two-pass", minimum_passes=2, maximum_passes=2)
        return plan
    if tier == "high":
        plan.update(validation_mode="executor-verifier", review_topology="cross-domain",
                    selected_pairs_count=min(max(domains, 2), 3), iteration_mode="adaptive",
                    minimum_passes=2, maximum_passes=3)
        if task_type in HUMAN_GATE_TASKS or risk["public_impact"] == "high" or external_submission:
            plan.update(cross_model_reviewer="codex-1x", human_gate=True)
        return plan
    if tier == "critical":
        plan.update(validation_mode="human-gated", review_topology="cross-domain",
                    selected_pairs_count=min(max(domains, 2), 3), iteration_mode="adaptive",
                    minimum_passes=2, maximum_passes=3, cross_model_reviewer="codex-1x", human_gate=True)
        return plan
    # fallback (medium 단일도메인 외)
    plan.update(validation_mode="executor-verifier", review_topology="intra-pair",
                selected_pairs_count=1, iteration_mode="two-pass", minimum_passes=2, maximum_passes=2)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="adaptive verification router (deterministic)")
    ap.add_argument("--task-type", required=True)
    ap.add_argument("--domains", type=int, default=1, help="관련 도메인 수")
    ap.add_argument("--interdependent", action="store_true")
    ap.add_argument("--irreversible", action="store_true")
    ap.add_argument("--public-impact", action="store_true")
    ap.add_argument("--external-submission", action="store_true")
    ap.add_argument("--deterministic-verifier", action="store_true")
    ap.add_argument("--ambiguity", default="low", choices=["low", "medium", "high"])
    args = ap.parse_args()

    risk = assess_risk(args.task_type, args.domains, args.interdependent, args.irreversible,
                       args.public_impact, args.external_submission, args.deterministic_verifier,
                       args.ambiguity)
    plan = route(risk, args.task_type, args.domains, args.deterministic_verifier, args.external_submission)
    out = {
        "review_plan": plan,
        "risk_assessment": risk,
        "limits": {"same_failure_limit": SAME_FAILURE_LIMIT, "maximum_global_iterations": GLOBAL_MAX,
                   "global_max_source": _CB_SRC, "ledger_reuse": _LEDGER_OK,
                   "engine": "circuit_breaker.py(import)·loop_ledger.py(import)"},
        "cross_domain_engine": "challenge_manager.py (review_topology==cross-domain 일 때)",
        "_note": "결정적 라우터. 6~8 전체 pair 호출 안 함 — selected_pairs_count 만. 실제 pair 선택=pair_router.py",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
