#!/usr/bin/env python3
"""
loop_contract_validator.py — Loop Engineering Control Plane 계약 검증기 (r3 후보).

자연어 요청 1건당 1 loop_contract 가 스키마(필수필드 + enum + recipe 실재)를 모두
갖췄는지 검증한다. 스키마 정본:
  .claude/skills/_loop-core/loop-contract-schema.yaml

사용법:
  python3 scripts/loop_contract_validator.py validate <contract.yaml|.json>
  python3 scripts/loop_contract_validator.py self-test
  python3 scripts/loop_contract_validator.py print-schema

  --recipes-dir <path>   recipe 디렉토리 override (기본 .claude/skills/_loop-core/recipes)

exit: 0=통과, 2=위반(violations≥1), 1=사용오류

대화 컨텍스트는 loop 상태의 정본이 아니다 — 정본은 디스크의 contract.yaml 이며 본 검증기를
통과해야 한다.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_RECIPES = os.path.join(ROOT, ".claude", "skills", "_loop-core", "recipes")

REQUIRED_FIELDS = [
    "loop_id", "created_at", "request", "task_type", "recipe", "executor",
    "validation_mode", "steps", "budget", "editable_paths", "human_gates",
    "success_conditions", "hold_conditions", "state", "approval",
]

TASK_TYPES = {
    "simple-question", "code-bugfix", "code-feature", "code-question",
    "research", "fact-check", "writing", "experiment", "document-form",
    "claude-design", "knowledge-promotion", "deployment", "long-compute",
    "visual-generation",
}

VALIDATION_MODES = {
    "one-shot", "deterministic-only", "executor-verifier", "cross-model", "human-gated",
}

STATE_KEYS = {"contract", "ledger", "verdict", "artifact"}


def _load(path):
    """contract 파일 로드 — .json 은 json, .yaml/.yml 은 PyYAML(있으면)."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        return json.loads(text)
    # yaml
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        # PyYAML 부재 — JSON 으로 시도(상위호환), 아니면 사용오류
        try:
            return json.loads(text)
        except Exception:
            sys.stderr.write("❌ PyYAML 미설치 + JSON 아님: yaml 계약은 PyYAML 필요\n")
            sys.exit(1)


def validate(contract, recipes_dir):
    """contract dict 를 검증해 violations 리스트 반환(빈 리스트=통과)."""
    v = []
    if not isinstance(contract, dict):
        return ["contract 가 매핑(dict)이 아님"]

    # 1) 필수필드
    for k in REQUIRED_FIELDS:
        if k not in contract or contract[k] in (None, ""):
            v.append(f"필수필드 누락: {k}")

    # 2) task_type enum
    tt = contract.get("task_type")
    if tt is not None and tt not in TASK_TYPES:
        v.append(f"task_type enum 위반: {tt!r} (허용 {sorted(TASK_TYPES)})")

    # 3) validation_mode = list, 각 원소 enum
    vm = contract.get("validation_mode")
    if vm is not None:
        modes = vm if isinstance(vm, list) else [vm]
        if not modes:
            v.append("validation_mode 비어 있음(≥1 필요)")
        for m in modes:
            if m not in VALIDATION_MODES:
                v.append(f"validation_mode enum 위반: {m!r} (허용 {sorted(VALIDATION_MODES)})")

    # 4) recipe 실재(파일 존재)
    rc = contract.get("recipe")
    if rc is not None:
        rpath = os.path.join(recipes_dir, f"{rc}.yaml")
        if not os.path.isfile(rpath):
            v.append(f"recipe 미실재: {rc} ({rpath} 없음)")

    # 5) steps = 비어있지 않은 list, 각 원소는 'action' 키를 가진 dict
    st = contract.get("steps")
    if st is not None:
        if not isinstance(st, list) or len(st) == 0:
            v.append("steps 는 비어있지 않은 list 여야 함")
        else:
            for i, s in enumerate(st):
                if not isinstance(s, dict) or "action" not in s:
                    v.append(f"steps[{i}] 는 'action' 키를 가진 dict 여야 함")

    # 5b) budget = dict
    bg = contract.get("budget")
    if bg is not None and not isinstance(bg, dict):
        v.append("budget 는 dict 여야 함")

    # 6) editable_paths / human_gates = list(빈 list 허용)
    for k in ("editable_paths", "human_gates", "success_conditions", "hold_conditions"):
        val = contract.get(k)
        if val is not None and not isinstance(val, list):
            v.append(f"{k} 는 list 여야 함")
    for k in ("success_conditions", "hold_conditions"):
        val = contract.get(k)
        if isinstance(val, list) and len(val) == 0:
            v.append(f"{k} 는 ≥1 항목 필요")

    # 7) state = dict + 핵심 키
    state = contract.get("state")
    if state is not None:
        if not isinstance(state, dict):
            v.append("state 는 dict 여야 함")
        else:
            for sk in STATE_KEYS:
                if sk not in state:
                    v.append(f"state 키 누락: {sk}")
            # 대화가 아니라 디스크가 정본 — contract/ledger/verdict 경로가 _claude/loops 하위인지 + 경로탈출(..) 금지
            for sk in ("contract", "ledger", "verdict"):
                pv = state.get(sk, "")
                if isinstance(pv, str) and pv:
                    norm = pv.replace("\\", "/")
                    if "_claude/loops/" not in norm:
                        v.append(f"state.{sk} 경로 규약 위반(_claude/loops/<loop_id>/ 기대): {pv}")
                    if ".." in norm.split("/"):
                        v.append(f"state.{sk} 경로에 '..' 금지(경로 탈출): {pv}")

    # 8) approval.plan_approved 존재 + boolean 타입
    ap = contract.get("approval")
    if isinstance(ap, dict):
        if "plan_approved" not in ap:
            v.append("approval.plan_approved 누락")
        elif not isinstance(ap["plan_approved"], bool):
            v.append("approval.plan_approved 는 boolean 이어야 함")
    elif ap is not None:
        v.append("approval 은 dict 여야 함")

    return v


def _minimal_valid(recipes_dir):
    """self-test 용 최소 유효 계약(존재하는 recipe 사용)."""
    # 존재하는 recipe 하나 선택(결정적: 정렬 후 첫 번째)
    recipe = "simple-question"
    try:
        names = sorted(f[:-5] for f in os.listdir(recipes_dir) if f.endswith(".yaml"))
        if names:
            recipe = names[0]
    except OSError:
        pass
    lid = "code-bugfix-20260623-190000-a1b2"
    return {
        "loop_id": lid,
        "created_at": "2026-06-23",
        "request": "이 버그 고쳐줘",
        "task_type": "code-bugfix",
        "recipe": recipe,
        "executor": "dev-suite",
        "validation_mode": ["deterministic-only", "executor-verifier"],
        "steps": [{"id": 1, "action": "진단", "uses": "harness-systematic-debugging"}],
        "budget": {"max_iterations": 3, "max_minutes": 30, "repeat_fail_hold": 2},
        "editable_paths": ["src/**", "tests/**"],
        "human_gates": [],
        "success_conditions": ["재현 테스트 RED→GREEN"],
        "hold_conditions": ["같은 실패 2회"],
        "state": {
            "contract": f"_claude/loops/{lid}/contract.yaml",
            "ledger": f"_claude/loops/{lid}/events.jsonl",
            "verdict": f"_claude/loops/{lid}/verdict.json",
            "artifact": f"_output/loops/{lid}/",
        },
        "approval": {"plan_approved": True, "approved_at": "2026-06-23", "approved_via": "AskUserQuestion"},
    }


def self_test(recipes_dir):
    ok = _minimal_valid(recipes_dir)
    v1 = validate(ok, recipes_dir)
    if v1:
        print("❌ self-test: 유효 계약이 위반 처리됨:", v1)
        return 2
    # 깨진 계약들
    bad_cases = []
    b1 = dict(ok); b1["task_type"] = "nonsense"; bad_cases.append(("task_type enum", b1))
    b2 = dict(ok); del b2["budget"]; bad_cases.append(("필수필드 누락", b2))
    b3 = dict(ok); b3["validation_mode"] = ["made-up"]; bad_cases.append(("vmode enum", b3))
    b4 = dict(ok); b4["recipe"] = "does-not-exist-xyz"; bad_cases.append(("recipe 미실재", b4))
    b5 = dict(ok); b5["state"] = dict(ok["state"]); b5["state"]["contract"] = "/tmp/x/contract.yaml"
    bad_cases.append(("state 경로규약", b5))
    b6 = dict(ok); b6["steps"] = ["문자열 step(형상 위반)"]; bad_cases.append(("steps 형상", b6))
    b7 = dict(ok); b7["approval"] = {"plan_approved": "yes"}; bad_cases.append(("plan_approved bool", b7))
    b8 = dict(ok); b8["budget"] = "unlimited"; bad_cases.append(("budget dict", b8))
    b9 = dict(ok); b9["state"] = dict(ok["state"])
    b9["state"]["ledger"] = "_claude/loops/../../etc/events.jsonl"
    bad_cases.append(("state .. 탈출", b9))
    fails = 0
    for label, bad in bad_cases:
        if not validate(bad, recipes_dir):
            print(f"❌ self-test: 깨진 계약이 통과됨 ({label})")
            fails += 1
    if fails:
        return 2
    print(f"✅ self-test PASS (유효 1 통과 · 깨진 {len(bad_cases)} 거부)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Loop contract validator")
    ap.add_argument("cmd", choices=["validate", "self-test", "print-schema"])
    ap.add_argument("contract", nargs="?", help="validate 시 계약 파일 경로")
    ap.add_argument("--recipes-dir", default=DEFAULT_RECIPES)
    args = ap.parse_args()

    if args.cmd == "print-schema":
        print(json.dumps({
            "required_fields": REQUIRED_FIELDS,
            "task_types": sorted(TASK_TYPES),
            "validation_modes": sorted(VALIDATION_MODES),
            "state_keys": sorted(STATE_KEYS),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "self-test":
        return self_test(args.recipes_dir)

    if args.cmd == "validate":
        if not args.contract:
            sys.stderr.write("사용오류: validate <contract 경로>\n")
            return 1
        if not os.path.isfile(args.contract):
            sys.stderr.write(f"사용오류: 파일 없음 {args.contract}\n")
            return 1
        contract = _load(args.contract)
        v = validate(contract, args.recipes_dir)
        if v:
            print(f"❌ INVALID ({len(v)} violations):")
            for x in v:
                print("  -", x)
            return 2
        print("✅ VALID")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
