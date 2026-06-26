#!/usr/bin/env python3
"""
mode_c_entry_gate.py — Mode C(자율 실험 루프) cycle 진입 게이트 (B4 배선)

실제 Mode C cycle runner 가 **한 사이클에 진입하기 전** 호출하는 게이트.
experiment_contract_validator.py 를 cycle 진입 게이트에 배선하고, 추가로
experiment_contract ↔ cycle.*.yaml 필드 정합을 재대조한다.

3 단계:
  (1) 인프라 확인     — cycle.*.yaml 존재? 없으면 Mode C 미발효(진입 안 함, exit 3)
  (2) 계약 검증       — experiment_contract_validator.py validate <contract>
                        exit != 0 (위반/파일오류) → 진입 차단
  (3) 정합 재대조     — contract.metric.name/direction ↔ cycle.metric.key/direction (hard)
                        cycle.guardrails.protect ⊆ contract.forbidden_files (advisory)
                        cycle.keep_rule 존재 ↔ contract.keep_discard_rule (advisory)

세 단계 모두 통과해야만 cycle 진입 허용. 통과해도 **실제 실험 실행은 runner 책임**이며,
본 게이트는 진입 가부만 판정한다. 권위: v4.5 stop-guard·hookify 최종. 자동게이트 ⊆ 기계 게이트.

라이브러리 사용:
    from mode_c_entry_gate import entry_gate
    ok, report = entry_gate("contract.yaml", ".claude/cycle.proj.yaml")
    if not ok:
        abort_cycle(report)          # 진입 차단

CLI 사용:
    python3 scripts/mode_c_entry_gate.py --contract <c.yaml> --cycle <.claude/cycle.*.yaml> [--schema <s.yaml>]
    exit: 0=진입허용, 2=차단(검증 또는 정합 위반), 3=인프라 부재, 1=사용오류
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VALIDATOR = REPO_ROOT / "scripts" / "experiment_contract_validator.py"
DEFAULT_SCHEMA = REPO_ROOT / "_output" / "contracts" / "mode_c_experiment_contract_schema.yaml"


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML 미설치 — Mode C 게이트는 yaml 필요.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _run_validator(contract_path: Path, schema_path: Path, validator_path: Path) -> dict:
    """experiment_contract_validator.py validate 를 subprocess 로 호출. {exit, stdout, ok, violations} 반환."""
    # ⚠️ validator 의 --schema 는 top-level 인자(subcommand 앞). 순서 중요:
    #    validator.py --schema <s> validate <c>   (validate 뒤에 두면 argparse 오류)
    proc = subprocess.run(
        [sys.executable, str(validator_path), "--schema", str(schema_path),
         "validate", str(contract_path)],
        capture_output=True, text=True,
    )
    parsed = None
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {
        "exit": proc.returncode,
        "ok": proc.returncode == 0,
        "violations": (parsed or {}).get("violations", []),
        "stderr": proc.stderr.strip(),
    }


def _reconcile(contract: dict, cycle: dict) -> dict:
    """experiment_contract ↔ cycle.*.yaml 필드 정합 재대조. {violations, warnings} 반환.
    설계 정본 docs/mode_c_autoresearch.md: evaluator↔runner, metric↔metric,
    keep_discard_rule↔keep_rule, forbidden_files↔guardrails.protect."""
    violations: list[dict] = []
    warnings: list[dict] = []

    c_metric = contract.get("metric") or {}
    y_metric = cycle.get("metric") or {}
    # metric 이름 정합 (hard): runner 가 내는 지표 != 계약이 최적화하는 지표면 위험
    if isinstance(c_metric, dict) and isinstance(y_metric, dict):
        if c_metric.get("name") != y_metric.get("key"):
            violations.append({"id": "RECONCILE_METRIC_NAME",
                "message": f"contract.metric.name={c_metric.get('name')!r} != cycle.metric.key={y_metric.get('key')!r}"})
        if c_metric.get("direction") != y_metric.get("direction"):
            violations.append({"id": "RECONCILE_METRIC_DIRECTION",
                "message": f"contract.metric.direction={c_metric.get('direction')!r} != cycle.metric.direction={y_metric.get('direction')!r}"})

    # forbidden_files 가 guardrails.protect 를 커버하는지 (advisory)
    protect = set((cycle.get("guardrails") or {}).get("protect") or [])
    forbidden = set(contract.get("forbidden_files") or [])
    uncovered = protect - forbidden
    if uncovered:
        warnings.append({"id": "RECONCILE_PROTECT",
            "message": f"cycle.guardrails.protect 중 contract.forbidden_files 미포함: {sorted(uncovered)}"})

    # keep 규칙 양쪽 존재 (advisory)
    if not (cycle.get("keep_rule") and contract.get("keep_discard_rule")):
        warnings.append({"id": "RECONCILE_KEEP_RULE",
            "message": "keep_rule(cycle) 또는 keep_discard_rule(contract) 누락 — KEEP? 판정 정합 불가"})

    return {"violations": violations, "warnings": warnings}


def entry_gate(contract_path, cycle_path, schema_path=None, validator_path=None) -> tuple[bool, dict]:
    """Mode C cycle 진입 게이트. (ok, report) 반환. ok=True 면 진입 허용."""
    contract_path = Path(contract_path)
    cycle_path = Path(cycle_path)
    schema_path = Path(schema_path) if schema_path else DEFAULT_SCHEMA
    validator_path = Path(validator_path) if validator_path else DEFAULT_VALIDATOR

    report: dict = {"stages": {}, "blocked_reason": None}

    # (1) 인프라 확인
    infra = cycle_path.exists()
    report["stages"]["infra"] = {"cycle_yaml": str(cycle_path), "present": infra}
    if not infra:
        report["blocked_reason"] = "INFRA_ABSENT"
        report["entry"] = "NOT_ACTIVATED"
        return False, report

    # (2) 계약 검증 (validator 배선)
    val = _run_validator(contract_path, schema_path, validator_path)
    report["stages"]["validation"] = val
    if not val["ok"]:
        report["blocked_reason"] = "CONTRACT_INVALID"
        report["entry"] = "BLOCKED"
        return False, report

    # (3) contract ↔ cycle.yaml 정합 재대조
    contract = _load_yaml(contract_path)
    cycle = _load_yaml(cycle_path)
    rec = _reconcile(contract, cycle)
    report["stages"]["reconcile"] = rec
    if rec["violations"]:
        report["blocked_reason"] = "RECONCILE_MISMATCH"
        report["entry"] = "BLOCKED"
        return False, report

    report["entry"] = "ALLOWED"
    return True, report


def main() -> int:
    ap = argparse.ArgumentParser(description="Mode C cycle 진입 게이트 (validator 배선 + 정합 재대조)")
    ap.add_argument("--contract", required=True, help="experiment_contract 파일(.yaml/.json)")
    ap.add_argument("--cycle", required=True, help="cycle.*.yaml 인프라 파일 경로")
    ap.add_argument("--schema", default=None, help="experiment_contract 스키마(기본=정본 경로)")
    ap.add_argument("--validator", default=None, help="validator 스크립트(기본=scripts/experiment_contract_validator.py)")
    args = ap.parse_args()

    if not Path(args.contract).exists():
        print(f"❌ 계약 파일 없음: {args.contract}", file=sys.stderr)
        return 1

    ok, report = entry_gate(args.contract, args.cycle, args.schema, args.validator)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    reason = report.get("blocked_reason")
    if ok:
        print("[gate] ✅ ALLOWED — cycle 진입 허용 (실제 실험 실행은 runner 책임)", file=sys.stderr)
        return 0
    if reason == "INFRA_ABSENT":
        print("[gate] ⏸ NOT_ACTIVATED — cycle.*.yaml 부재 → Mode C 미발효(진입 안 함)", file=sys.stderr)
        return 3
    print(f"[gate] ❌ BLOCKED — {reason} → cycle 진입 차단", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
