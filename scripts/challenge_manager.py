#!/usr/bin/env python3
"""challenge_manager.py v1 — Cross-pair challenge 오케스트레이션 (STEP 1.5)

목적:
  - STEP 1 완료 후 STEP 2 진입 전에 페어 간 명시적 도전 강제
  - 도전 매트릭스 선언 → Claude가 Task 분기 실행 → 결과 기록
  - session_log.jsonl 에 cross-pair-challenge 이벤트로 audit

설계 원칙:
  - 실제 Task 분기는 Claude가 함 (이 스크립트는 manifest 생성 + 기록)
  - audit log 에 누가 누구를 도전했고 findings가 몇 개인지 기록
  - 수동 호출 가능한 CLI 형태

사용 흐름:
  # 1. 도전 매니페스트 생성 (이게 뭘 해야 하는지 선언)
  python scripts/challenge_manager.py plan \\
    --scope min|standard|extended \\
    --pairs PAIR-SAR,PAIR-AI,PAIR-VOLC

  # 2. Claude가 매니페스트 읽고 Task 분기 실행 (여기서 개입 없음)

  # 3. 각 도전 결과 기록
  python scripts/challenge_manager.py record \\
    --challenger PAIR-QA \\
    --target PAIR-SAR \\
    --findings 2

  # 4. 완료 확인
  python scripts/challenge_manager.py status

의존성: harness_common.py, session_logger.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, save_yaml_atomic, load_yaml, now_iso, atomic_write, HAS_YAML
    )
except ImportError as e:
    sys.stderr.write(f"❌ harness_common 로드 실패: {e}\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요: pip install pyyaml --break-system-packages\n")
    sys.exit(1)


# ────────────────────────────── 경로 ──────────────────────────────

RUNTIME_DIR = Path(".claude/runtime")
CHALLENGES_DIR = RUNTIME_DIR / "challenges"
SESSION_LOG = RUNTIME_DIR / "session_log.jsonl"


# ────────────────────────────── 매트릭스 정의 ──────────────────────────────

# "min": PAIR-QA가 모든 도메인 페어 도전 (최소 구성)
# "standard": DEV→LEAD + QA→모두 + METHODS→모두 (권장)
# "extended": standard + 도메인 페어끼리 (확장, 상관 오류 위험)

CHALLENGE_MATRIX = {
    "min": {
        "description": "PAIR-QA only — boundary verification",
        "challenges": [
            {"challenger": "PAIR-QA", "target": "*domain*",
             "focus": "경계면 정합성: 시공간 해상도, 단위, shape, silent failure"},
        ],
    },
    "standard": {
        "description": "DEV→LEAD + QA→domains + METHODS→domains (권장)",
        "challenges": [
            {"challenger": "PAIR-DEV", "target": "PAIR-LEAD",
             "focus": "플랜 구현 현실성, 의존성, 자원 가정"},
            {"challenger": "PAIR-QA", "target": "*domain*",
             "focus": "경계면 정합성: 시공간 해상도, 단위, shape, silent failure"},
            {"challenger": "PAIR-METHODS", "target": "*domain*",
             "focus": "평가 기준 일관성, 통계 함정, 재현성"},
        ],
    },
    "extended": {
        "description": "standard + 도메인 페어 간 교차 도전 (상관 오류 위험)",
        "challenges": [
            {"challenger": "PAIR-DEV", "target": "PAIR-LEAD",
             "focus": "플랜 구현 현실성"},
            {"challenger": "PAIR-QA", "target": "*domain*",
             "focus": "경계면 정합성"},
            {"challenger": "PAIR-METHODS", "target": "*domain*",
             "focus": "평가·통계 일관성"},
            {"challenger": "*domain*", "target": "*domain-other*",
             "focus": "도메인 가정 충돌 (라운드 로빈)"},
        ],
    },
}


def _turn_id() -> str:
    cur = RUNTIME_DIR / "current_turn.txt"
    if cur.exists():
        return cur.read_text(encoding="utf-8").strip()
    return "no-turn"


def _append_event(event: str, payload: dict[str, Any]) -> None:
    """session_log.jsonl 에 이벤트 기록 (session_logger 와 같은 포맷)."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": now_iso(),
        "turn": _turn_id(),
        "event": event,
        "payload": payload,
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with file_lock(SESSION_LOG, timeout=3.0):
        with open(SESSION_LOG, "a", encoding="utf-8") as f:
            f.write(line)


# ────────────────────────────── 명령: plan ──────────────────────────────

def cmd_plan(args):
    """Cross-pair challenge 매니페스트 생성."""
    if args.scope not in CHALLENGE_MATRIX:
        sys.stderr.write(f"❌ scope 는 {list(CHALLENGE_MATRIX.keys())} 중 하나여야 함.\n")
        sys.exit(1)

    matrix = CHALLENGE_MATRIX[args.scope]
    pairs = [p.strip() for p in args.pairs.split(",") if p.strip()] if args.pairs else []

    # domain 페어 필터 (PAIR-DEV/QA/LEAD/METHODS 는 표준 역할이므로 제외)
    STANDARD_ROLES = {"PAIR-DEV", "PAIR-QA", "PAIR-LEAD", "PAIR-METHODS", "PAIR-VIS", "PAIR-RES"}
    domain_pairs = [p for p in pairs if p not in STANDARD_ROLES]

    # 구체적 challenge 목록 확장
    concrete = []
    for spec in matrix["challenges"]:
        challenger = spec["challenger"]
        target = spec["target"]
        focus = spec["focus"]

        # 와일드카드 확장
        if target == "*domain*":
            for dp in domain_pairs:
                concrete.append({
                    "challenger": challenger,
                    "target": dp,
                    "focus": focus,
                    "status": "pending",
                })
        elif challenger == "*domain*" and target == "*domain-other*":
            # 라운드 로빈: 각 도메인이 다른 도메인 도전
            for i, dp_a in enumerate(domain_pairs):
                for dp_b in domain_pairs[i+1:]:
                    concrete.append({
                        "challenger": dp_a, "target": dp_b,
                        "focus": focus, "status": "pending",
                    })
        else:
            # 구체적 페어 지정
            concrete.append({
                "challenger": challenger, "target": target,
                "focus": focus, "status": "pending",
            })

    # 매니페스트 저장
    CHALLENGES_DIR.mkdir(parents=True, exist_ok=True)
    turn = _turn_id()
    manifest_path = CHALLENGES_DIR / f"{turn}-{args.phase}-manifest.yaml"
    manifest = {
        "turn_id": turn,
        "phase": args.phase,            # v2.6.3: pre-research (STEP 1.5) | pre-plan (STEP 2.5)
        "created_at": now_iso(),
        "scope": args.scope,
        "matrix_description": matrix["description"],
        "domain_pairs": domain_pairs,
        "challenges": concrete,
        "total_challenges": len(concrete),
        "completed": 0,
    }
    save_yaml_atomic(manifest_path, manifest)

    _append_event("cross-pair-plan", {
        "scope": args.scope,
        "total_challenges": len(concrete),
        "manifest_path": str(manifest_path),
    })

    if args.format == "json":
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    print(f"✅ Cross-pair challenge 매니페스트 생성")
    print(f"   매트릭스: {args.scope} ({matrix['description']})")
    print(f"   총 도전 수: {len(concrete)}")
    print(f"   매니페스트: {manifest_path}")
    print("")
    print("다음 단계 — 각 도전을 Claude 가 Task 로 실행:")
    for i, ch in enumerate(concrete, 1):
        print(f"   {i}. {ch['challenger']} → {ch['target']}  [{ch['focus'][:50]}]")
    print("")
    print("실행 완료 후:")
    print(f"   python {sys.argv[0]} record --challenger <C> --target <T> --findings <N>")


# ────────────────────────────── 명령: record ──────────────────────────────

def cmd_record(args):
    """도전 결과를 매니페스트 + audit log 에 기록."""
    turn = _turn_id()
    manifest_path = CHALLENGES_DIR / f"{turn}-{args.phase}-manifest.yaml"
    if not manifest_path.exists():
        sys.stderr.write(f"❌ 현재 턴의 매니페스트 없음: {manifest_path}\n")
        sys.stderr.write(f"   먼저 'plan' 명령으로 생성하세요.\n")
        sys.exit(1)

    with file_lock(manifest_path, timeout=5.0):
        manifest = load_yaml(manifest_path) or {}
        challenges = manifest.get("challenges", [])
        matched = None
        for ch in challenges:
            if ch["challenger"] == args.challenger and ch["target"] == args.target:
                matched = ch
                break
        if not matched:
            sys.stderr.write(f"❌ 매니페스트에서 해당 도전 쌍 없음: {args.challenger} → {args.target}\n")
            sys.exit(1)
        matched["status"] = "completed"
        matched["findings"] = int(args.findings)
        matched["completed_at"] = now_iso()
        if args.summary:
            matched["summary"] = args.summary
        if args.severity_max:
            matched["severity_max"] = args.severity_max
        manifest["completed"] = sum(1 for c in challenges if c.get("status") == "completed")
        save_yaml_atomic(manifest_path, manifest)

    _append_event("cross-pair-challenge", {
        "challenger": args.challenger,
        "target": args.target,
        "findings": int(args.findings),
        "severity_max": args.severity_max,
        "summary": (args.summary or "")[:200],
    })

    out = {
        "status": "recorded",
        "challenger": args.challenger,
        "target": args.target,
        "findings": args.findings,
        "manifest_progress": f"{manifest['completed']}/{manifest['total_challenges']}",
    }
    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"✅ 도전 기록: {args.challenger} → {args.target} (findings={args.findings})")
        print(f"   진행: {manifest['completed']}/{manifest['total_challenges']}")


# ────────────────────────────── 명령: status ──────────────────────────────

def cmd_status(args):
    """현재 턴의 challenge 진행 상태 확인."""
    turn = _turn_id()
    manifest_path = CHALLENGES_DIR / f"{turn}-{args.phase}-manifest.yaml"
    if not manifest_path.exists():
        if args.format == "json":
            print(json.dumps({"status": "no-manifest", "turn_id": turn}))
        else:
            print("ℹ️  현재 턴에 cross-pair challenge 매니페스트 없음")
        return

    manifest = load_yaml(manifest_path) or {}

    if args.format == "json":
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    print(f"━━━ Cross-pair challenge 상태 (turn {turn}) ━━━")
    print(f"  매트릭스: {manifest.get('scope')} — {manifest.get('matrix_description')}")
    print(f"  진행:      {manifest.get('completed', 0)}/{manifest.get('total_challenges', 0)}")
    print("")
    for i, ch in enumerate(manifest.get("challenges", []), 1):
        status_icon = "✅" if ch.get("status") == "completed" else "⏳"
        findings = f" (findings={ch.get('findings', '?')})" if ch.get("status") == "completed" else ""
        print(f"  {status_icon} {i}. {ch['challenger']} → {ch['target']}{findings}")
        if ch.get("summary"):
            print(f"      └─ {ch['summary'][:80]}")


# ────────────────────────────── 명령: verify ──────────────────────────────

def cmd_verify(args):
    """STEP 2 진입 전 검증: 모든 challenge 완료됐는가."""
    turn = _turn_id()
    manifest_path = CHALLENGES_DIR / f"{turn}-{args.phase}-manifest.yaml"
    if not manifest_path.exists():
        if args.strict:
            sys.stderr.write(f"❌ 매니페스트 없음: {manifest_path}\n")
            sys.stderr.write("   --strict 모드에서는 plan 명령이 선행되어야 함.\n")
            sys.exit(1)
        # 관대한 모드: 매니페스트 없으면 통과
        if args.format == "json":
            print(json.dumps({"status": "no-manifest", "pass": True}))
        else:
            print("ℹ️  매니페스트 없음 — cross-pair challenge 스킵됨")
        return

    manifest = load_yaml(manifest_path) or {}
    completed = manifest.get("completed", 0)
    total = manifest.get("total_challenges", 0)
    pending = [c for c in manifest.get("challenges", []) if c.get("status") != "completed"]

    out = {
        "status": "ok" if completed == total else "incomplete",
        "pass": completed == total,
        "completed": completed,
        "total": total,
        "pending": [(c["challenger"], c["target"]) for c in pending],
    }

    if completed < total:
        sys.stderr.write(f"❌ Cross-pair challenge 미완료: {completed}/{total}\n")
        for ch in pending:
            sys.stderr.write(f"   ⏳ {ch['challenger']} → {ch['target']}\n")
        if args.format == "json":
            print(json.dumps(out, ensure_ascii=False))
        sys.exit(2)

    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"✅ 모든 cross-pair challenge 완료 ({completed}/{total}) — STEP 2 진입 가능")


# ────────────────────────────── argparse ──────────────────────────────

VALID_PHASES = ("pre-research", "pre-plan")


def build_parser():
    p = argparse.ArgumentParser(
        description=("challenge_manager — cross-pair challenge 오케스트레이션. "
                     "STEP 1.5 (pre-research, 기본) + STEP 2.5 (pre-plan, v2.6.3+).")
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="도전 매니페스트 생성")
    pl.add_argument("--scope", default="standard", choices=list(CHALLENGE_MATRIX.keys()),
                    help="기본값 standard (권장). min=QA only, extended=도메인 간 추가")
    pl.add_argument("--pairs", required=True,
                    help="쉼표 구분 페어 목록 (예: PAIR-SAR,PAIR-AI,PAIR-DEV,PAIR-LEAD,PAIR-QA,PAIR-METHODS)")
    pl.add_argument("--phase", default="pre-research", choices=VALID_PHASES,
                    help=("v2.6.3+: pre-research (STEP 1.5, RESEARCH.md 직전, 기본) | "
                          "pre-plan (STEP 2.5, PLAN.md 직전, extended 권장)"))
    pl.add_argument("--format", choices=["text", "json"], default="text")

    rc = sub.add_parser("record", help="도전 결과 기록")
    rc.add_argument("--challenger", required=True, help="도전자 페어 (예: PAIR-QA)")
    rc.add_argument("--target", required=True, help="도전 대상 페어")
    rc.add_argument("--findings", required=True, help="발견된 문제 수 (0=no finding)")
    rc.add_argument("--severity-max",
                    choices=["none", "minor", "major", "critical"],
                    help="가장 심각한 finding severity")
    rc.add_argument("--summary", help="요약 (200자 이내)")
    rc.add_argument("--phase", default="pre-research", choices=VALID_PHASES,
                    help="기록 대상 phase (plan 명령과 동일하게 지정)")
    rc.add_argument("--format", choices=["text", "json"], default="text")

    st = sub.add_parser("status", help="현재 턴 진행 상태")
    st.add_argument("--phase", default="pre-research", choices=VALID_PHASES)
    st.add_argument("--format", choices=["text", "json"], default="text")

    vf = sub.add_parser("verify", help="모든 challenge 완료 검증")
    vf.add_argument("--strict", action="store_true",
                    help="매니페스트 없을 때 실패 (기본: 통과)")
    vf.add_argument("--phase", default="pre-research", choices=VALID_PHASES,
                    help=("STEP 2 진입 전: --phase pre-research. "
                          "STEP 3 (PLAN.md) 진입 전: --phase pre-plan."))
    vf.add_argument("--format", choices=["text", "json"], default="text")

    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        "plan": cmd_plan,
        "record": cmd_record,
        "status": cmd_status,
        "verify": cmd_verify,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
