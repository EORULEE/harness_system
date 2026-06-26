#!/usr/bin/env python3
"""
experiment_contract_validator.py — Mode C(자율 실험 루프) 실험 계약 검증기 (F5/F7)

Mode C `cycle.*.yaml` 인프라에서 **cycle 진입 전** 실험 계약(experiment_contract)이
필수 10 필드 + 서브키를 모두 갖췄는지 검증한다. 스키마 정본:
  _output/contracts/mode_c_experiment_contract_schema.yaml  (required_fields / fields.*.required)
설계 정본: docs/mode_c_autoresearch.md. 권위: v4.5 stop-guard·hookify 최종.

⚠️ 자동 게이트 미발효 주의:
  이 프로젝트엔 `.claude/cycle.*.yaml` 인프라가 **없다**(2026-06-05 실측). 따라서 본 검증기는
  "cycle 진입 시 자동 실행"되지 않는다 — Mode C 인프라가 생기면 그 runner 의 진입 게이트에서
  `python3 scripts/experiment_contract_validator.py validate <contract>` 를 호출해 exit!=0 이면
  cycle 진입을 막도록 배선해야 한다. 현 단계 산출물 = **검증 primitive + 배선 지점 문서화**.

사용법:
  python3 scripts/experiment_contract_validator.py validate <contract.yaml|.json>   # 계약 검증
  python3 scripts/experiment_contract_validator.py self-test                          # 내장 회귀(예시 통과 + 결손 실패)
  python3 scripts/experiment_contract_validator.py print-schema                       # 필수필드·서브키 출력

  --schema <path>   스키마 경로 override (기본=_output/contracts/mode_c_experiment_contract_schema.yaml)

exit: 0=통과, 2=위반(violations≥1), 1=사용오류
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML 6.x (probe 확인됨)
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_SCHEMA = Path("_output/contracts/mode_c_experiment_contract_schema.yaml")
CYCLE_GLOB = ".claude/cycle.*.yaml"  # Mode C 인프라 존재 신호(자동게이트 발효 조건)

# 금전·실거래 hard-refuse 정규식 — bare 'coin'/'trading' 미사용(오탐 방지), 큐레이션 + word-boundary.
_MONEY_RE = re.compile(
    r"코인|암호화폐|가상자산|실거래|선물거래|자동매매|매매\s*봇|주문\s*체결|"
    r"\bbitcoin\b|\bcrypto\b|\bbinance\b|\bupbit\b|live[-\s]?trade|"
    r"algo[-\s]?trading|day[-\s]?trading|order\s+execution",
    re.IGNORECASE,
)

# ⚠️ 스키마↔cycle.yaml 정합 한계(검토 메모): 본 검증기는 experiment_contract 스키마
# (_output/contracts/mode_c_experiment_contract_schema.yaml)의 required_fields 를 검증한다.
# 이는 cycle.*.yaml(infra 정의: sandbox/runner/metric/keep_rule/guardrails/budget)와 **별개 아티팩트**다.
# 두 스키마의 필드 정합(예: evaluator↔runner, keep_discard_rule↔keep_rule, forbidden_files↔guardrails.protect)은
# Mode C 인프라(cycle.*.yaml)가 실제 생성될 때 docs/mode_c_autoresearch.md 기준으로 재대조해야 한다.


def _load_any(path: Path) -> dict:
    """YAML 또는 JSON 파일을 dict 로 로드."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("PyYAML 미설치 — YAML 계약을 파싱할 수 없음. JSON 으로 주거나 pyyaml 설치.")
        return yaml.safe_load(text) or {}
    if path.suffix == ".json":
        return json.loads(text)
    # 확장자 불명 — yaml 우선, 실패 시 json
    if yaml is not None:
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            pass
    return json.loads(text)


def _load_schema(schema_path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """스키마에서 required_fields 와 per-field required 서브키를 추출."""
    schema = _load_any(schema_path)
    required_fields = list(schema.get("required_fields") or [])
    if not required_fields:
        raise RuntimeError(f"스키마에 required_fields 없음: {schema_path}")
    sub_required: dict[str, list[str]] = {}
    for name, spec in (schema.get("fields") or {}).items():
        if isinstance(spec, dict) and spec.get("required"):
            sub_required[name] = list(spec["required"])
    return required_fields, sub_required


def validate_contract(contract: dict, required_fields: list[str],
                      sub_required: dict[str, list[str]]) -> dict:
    """계약 dict 를 검증. {ok, violations, warnings} 반환."""
    violations: list[dict] = []
    warnings: list[dict] = []

    if not isinstance(contract, dict):
        return {"ok": False, "violations": [{"id": "NOT_A_MAPPING",
                "message": "계약이 매핑(dict)이 아님"}], "warnings": []}

    # (1) 필수 10 필드 존재
    for field in required_fields:
        if field not in contract or contract[field] in (None, "", [], {}):
            violations.append({"id": "MISSING_FIELD", "field": field,
                               "message": f"필수 필드 누락/빈값: {field}"})

    # (2) per-field 필수 서브키
    for field, subkeys in sub_required.items():
        val = contract.get(field)
        if isinstance(val, dict):
            for sk in subkeys:
                if sk not in val or val[sk] in (None, ""):
                    violations.append({"id": "MISSING_SUBKEY", "field": f"{field}.{sk}",
                                       "message": f"{field} 에 필수 서브키 누락: {sk}"})
        elif field in contract:  # 존재하지만 dict 아님
            violations.append({"id": "WRONG_TYPE", "field": field,
                               "message": f"{field} 는 object 여야 함(서브키 {subkeys} 필요)"})

    # (3) 안전 게이트 — circuit_breaker max_iterations ≤ 5 정합
    mi = contract.get("max_iterations")
    if isinstance(mi, int) and mi > 5:
        violations.append({"id": "MAX_ITER_OVER_5", "field": "max_iterations",
                           "message": f"max_iterations={mi} > 5 (circuit_breaker 상한 위반). ≤5 + 미수렴 시 ESCALATED."})

    # (4) 로그 영속화 필수(딥러닝 2대 규율 ①)
    lp = contract.get("log_persistence")
    if isinstance(lp, dict) and lp.get("enabled") is not True:
        violations.append({"id": "LOG_PERSISTENCE_DISABLED", "field": "log_persistence.enabled",
                           "message": "log_persistence.enabled != true — 학습/실험 로그 영속화는 필수(삭제 금지)."})

    # (5) 코인·실거래 hard-refuse 신호 — 파일럿=DL만. 금전 키워드 감지 시 차단.
    # substring 오탐(cointegration/coincidence/'trading off') 방지 위해 word-boundary + 큐레이션.
    # 한국어는 형태상 substring 안전, 영어는 \b 경계·복합어 prefix 요구.
    blob = json.dumps(contract, ensure_ascii=False)
    if _MONEY_RE.search(blob):
        violations.append({"id": "COIN_LIVE_REFUSE", "field": "objective/evaluator",
                           "message": "금전·실거래 신호 감지 — Mode C 파일럿은 DL/세그멘테이션만. "
                                      "코인·실거래는 6전제 충족 전 hard-refuse(schema coin_hard_refuse)."})

    # (6) forbidden_files 체크포인트 불가침 권고(advisory)
    ff = contract.get("forbidden_files")
    if isinstance(ff, list):
        joined = " ".join(str(x) for x in ff).lower()
        if not any(tok in joined for tok in (".ckpt", ".pth", "checkpoint", "holdout", ".git")):
            warnings.append({"id": "FORBIDDEN_WEAK", "field": "forbidden_files",
                             "message": "forbidden_files 에 체크포인트(.ckpt/.pth)·holdout·.git 불가침 패턴이 보이지 않음 — 권고."})

    return {"ok": len(violations) == 0, "violations": violations, "warnings": warnings}


def cmd_validate(contract_path: Path, schema_path: Path) -> int:
    if not contract_path.exists():
        print(f"❌ 계약 파일 없음: {contract_path}", file=sys.stderr)
        return 1
    required_fields, sub_required = _load_schema(schema_path)
    contract = _load_any(contract_path)
    result = validate_contract(contract, required_fields, sub_required)
    # 인프라 부재 정보(자동게이트 미발효) 1줄 부착
    result["mode_c_infra_present"] = bool(list(Path(".").glob(CYCLE_GLOB)))
    if not result["mode_c_infra_present"]:
        result["_note"] = ("cycle.*.yaml 부재 → 이 검증은 수동/배선용. Mode C 인프라 생성 시 "
                           "cycle runner 진입 게이트에서 본 스크립트를 호출해 강제할 것.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def cmd_self_test(schema_path: Path) -> int:
    """내장 회귀: 스키마의 example(완전계약)=통과, 결손계약=실패 확인."""
    schema = _load_any(schema_path)
    required_fields, sub_required = _load_schema(schema_path)

    good = schema.get("example")
    if not isinstance(good, dict):
        print("❌ self-test: 스키마에 example 없음", file=sys.stderr)
        return 1
    r_good = validate_contract(good, required_fields, sub_required)

    # 결손계약: example 에서 필수필드 2개 제거 + max_iterations 위반
    bad = {k: v for k, v in good.items() if k not in ("metric", "log_persistence")}
    bad["max_iterations"] = 9
    r_bad = validate_contract(bad, required_fields, sub_required)

    bad_ids = {v["id"] for v in r_bad["violations"]}
    checks = {
        "example_passes": r_good["ok"] is True,
        "missing_field_detected": "MISSING_FIELD" in bad_ids,
        "max_iter_over_5_detected": "MAX_ITER_OVER_5" in bad_ids,
        "log_persistence_missing_detected": any(
            v["field"] == "log_persistence" for v in r_bad["violations"]),
    }
    all_ok = all(checks.values())
    print(json.dumps({"self_test_ok": all_ok, "checks": checks,
                      "example_result": r_good, "deficient_result": r_bad},
                     ensure_ascii=False, indent=2))
    return 0 if all_ok else 2


def cmd_print_schema(schema_path: Path) -> int:
    required_fields, sub_required = _load_schema(schema_path)
    print(json.dumps({"required_fields": required_fields, "sub_required": sub_required,
                      "mode_c_infra_present": bool(list(Path(".").glob(CYCLE_GLOB)))},
                     ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mode C experiment_contract 검증기 (F5/F7)")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="스키마 경로")
    sub = parser.add_subparsers(dest="cmd")
    v = sub.add_parser("validate", help="계약 검증")
    v.add_argument("contract", help="계약 파일(.yaml|.json)")
    sub.add_parser("self-test", help="내장 회귀 테스트")
    sub.add_parser("print-schema", help="필수필드·서브키 출력")

    args = parser.parse_args()
    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"❌ 스키마 없음: {schema_path}", file=sys.stderr)
        return 1

    cmd = args.cmd or "self-test"
    if cmd == "validate":
        return cmd_validate(Path(args.contract), schema_path)
    if cmd == "self-test":
        return cmd_self_test(schema_path)
    if cmd == "print-schema":
        return cmd_print_schema(schema_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
