#!/usr/bin/env python3
"""
step_compliance.py — 모드 B STEP 순서 강제 + 5대 미준수 차단

상태 파일: .claude/runtime/step_compliance.json

5대 검증 항목:
  1. STEP 0 전역 변수 확정 여부
  2. Codex (x-*) 교차검증 수행 여부
  3. STEP 순서 건너뛰기 차단
  4. 사용자 게이트 ([계속]/[시작]) 없이 진행 차단
  5. 범위 확인 없이 구현 진행 차단

사용법:
  python3 scripts/step_compliance.py check          # 현재 상태 검증
  python3 scripts/step_compliance.py advance <step>  # STEP 완료 기록
  python3 scripts/step_compliance.py enter-b         # 모드 B 진입
  python3 scripts/step_compliance.py gate <trigger>  # 사용자 게이트 기록
  python3 scripts/step_compliance.py globals-ok      # 전역 변수 확정
  python3 scripts/step_compliance.py reset           # 상태 초기화
  python3 scripts/step_compliance.py status          # 현재 상태 출력
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RUNTIME_DIR = Path(".claude/runtime")
STATE_FILE = RUNTIME_DIR / "step_compliance.json"

STEP_ORDER = [0, 1, 1.5, 2, 2.5, 3, 4, 5, 6]
STEP_NAMES = {
    0: "전역 변수 확정 + campaign bootstrap",
    1: "전문가 분석",
    1.5: "Cross-pair Challenge",
    2: "RESEARCH.md 작성",
    2.5: "Cross-pair Challenge 2차",
    3: "PLAN.md 작성",
    4: "사용자 검토 + 승인",
    5: "순차 구현 + 3단계 검증",
    6: "최종 통합 검토",
}

# STEP 진행에 사용자 게이트가 필요한 STEP들
GATE_REQUIRED_STEPS = {1, 1.5, 2, 2.5, 3, 4, 5, 6}

DEFAULT_STATE = {
    "active": False,
    "current_step": None,
    "completed_steps": [],
    "globals_confirmed": False,
    "user_gates": [],
    "codex_turns": 0,
    "total_turns": 0,
    "started_at": None,
    "last_updated": None,
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_STATE)


def _save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_enter_b() -> None:
    """모드 B 진입 — 상태 초기화 + 활성화."""
    state = dict(DEFAULT_STATE)
    state["active"] = True
    state["current_step"] = 0
    state["started_at"] = datetime.now().isoformat(timespec="seconds")
    _save_state(state)
    print("✅ 모드 B 진입 — STEP 0부터 시작")


def cmd_globals_ok() -> None:
    """전역 변수 확정 기록."""
    state = _load_state()
    state["globals_confirmed"] = True
    _save_state(state)
    print("✅ 전역 변수 확정 기록됨")


def cmd_gate(trigger: str) -> None:
    """사용자 게이트 통과 기록."""
    state = _load_state()
    entry = {
        "trigger": trigger,
        "at": datetime.now().isoformat(timespec="seconds"),
        "step": state.get("current_step"),
    }
    state.setdefault("user_gates", []).append(entry)
    _save_state(state)
    print(f"✅ 사용자 게이트 '{trigger}' 기록됨 (STEP {state.get('current_step')})")


def cmd_advance(step_str: str) -> None:
    """STEP 완료 기록 + 다음 STEP으로 이동."""
    state = _load_state()
    try:
        step = float(step_str)
        if step == int(step):
            step = int(step)
    except ValueError:
        print(f"❌ 유효하지 않은 STEP: {step_str}", file=sys.stderr)
        sys.exit(1)

    completed = state.get("completed_steps", [])
    if step not in completed:
        completed.append(step)
        completed.sort()
    state["completed_steps"] = completed

    idx = STEP_ORDER.index(step) if step in STEP_ORDER else -1
    if idx < len(STEP_ORDER) - 1:
        state["current_step"] = STEP_ORDER[idx + 1]
    else:
        state["current_step"] = None
        state["active"] = False

    _save_state(state)
    next_step = state["current_step"]
    if next_step is not None:
        print(f"✅ STEP {step} 완료 → 다음: STEP {next_step} ({STEP_NAMES.get(next_step, '')})")
    else:
        print(f"✅ STEP {step} 완료 — 모든 STEP 종료")


def cmd_record_codex() -> None:
    """Codex (x-*) 교차검증 수행 기록."""
    state = _load_state()
    state["codex_turns"] = state.get("codex_turns", 0) + 1
    _save_state(state)


def cmd_record_turn() -> None:
    """B모드 턴 기록."""
    state = _load_state()
    state["total_turns"] = state.get("total_turns", 0) + 1
    _save_state(state)


def cmd_check() -> dict:
    """현재 상태 검증 — 위반 사항 반환.

    반환: {"violations": [...], "warnings": [...], "ok": bool}
    """
    state = _load_state()
    result = {"violations": [], "warnings": [], "ok": True, "state": state}

    if not state.get("active"):
        print(json.dumps(result, ensure_ascii=False))
        return result

    current = state.get("current_step")
    completed = state.get("completed_steps", [])

    # 검증 1: STEP 0 전역 변수 미확정
    if current is not None and current > 0 and not state.get("globals_confirmed"):
        result["violations"].append({
            "id": "GLOBALS_NOT_CONFIRMED",
            "message": "STEP 0 전역 변수가 확정되지 않은 채 STEP 진행 중",
            "severity": "blocking",
        })

    # 검증 2: STEP 순서 건너뛰기
    if current is not None:
        for step in STEP_ORDER:
            if step >= current:
                break
            if step not in completed and step != current:
                result["violations"].append({
                    "id": "STEP_SKIPPED",
                    "message": f"STEP {step} ({STEP_NAMES.get(step, '')})이 완료되지 않은 채 STEP {current}으로 진행",
                    "severity": "blocking",
                })

    # 검증 3: 사용자 게이트 미통과
    gates = state.get("user_gates", [])
    gate_steps = {g.get("step") for g in gates}
    if current is not None and current in GATE_REQUIRED_STEPS:
        prev_step_idx = STEP_ORDER.index(current) - 1 if current in STEP_ORDER else -1
        if prev_step_idx >= 0:
            prev_step = STEP_ORDER[prev_step_idx]
            if prev_step in completed and prev_step not in gate_steps and current not in gate_steps:
                result["warnings"].append({
                    "id": "USER_GATE_MISSING",
                    "message": f"STEP {prev_step}→{current} 진행 시 사용자 게이트([계속]/[시작]) 미확인",
                    "severity": "warning",
                })

    # 검증 4: Codex 교차검증 비율
    total = state.get("total_turns", 0)
    codex = state.get("codex_turns", 0)
    if total >= 3 and codex == 0:
        result["violations"].append({
            "id": "NO_CODEX_CROSS_VALIDATION",
            "message": f"B모드 {total}턴 진행 중 Codex(x-*) 교차검증 0회",
            "severity": "blocking",
        })

    # 검증 5 (v4.6 명세 게이트): Mode B 구현(STEP 5) 진입인데 명세 계약 부재 — advisory.
    # 게이트 강도 = "모호할 때만 필수"(계약) → severity=warning(차단 아님).
    # violations 에 넣지 않으므로 기존 B STEP 강제(ok 판정)에 영향 0 (회귀 보존).
    if current is not None and current >= 5:
        contracts_dir = Path("_output/contracts")
        has_contract = contracts_dir.exists() and any(contracts_dir.glob("contract-*.md"))
        if not has_contract:
            result["warnings"].append({
                "id": "SPEC_GATE_MISSING",
                "message": "STEP 5(구현) 진입인데 명세 계약(_output/contracts/contract-*.md) 부재 — "
                           "요청이 모호했다면 harness-deep-interview 명세 게이트를 거치고 "
                           "Ralph 검증용 수용기준을 확정하세요. (v4.6 extension, advisory)",
                "severity": "warning",
            })

    result["ok"] = len(result["violations"]) == 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_reset() -> None:
    """상태 초기화."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("✅ step_compliance 상태 초기화됨")


def cmd_status() -> None:
    """현재 상태 출력."""
    state = _load_state()
    if not state.get("active"):
        print("step_compliance: 비활성 (모드 B 아님)")
        return

    current = state.get("current_step")
    completed = state.get("completed_steps", [])
    print(f"모드 B 활성 (시작: {state.get('started_at', '?')})")
    print(f"  현재 STEP: {current} ({STEP_NAMES.get(current, '완료')})")
    print(f"  완료 STEP: {completed}")
    print(f"  전역 변수: {'✅ 확정' if state.get('globals_confirmed') else '❌ 미확정'}")
    print(f"  사용자 게이트: {len(state.get('user_gates', []))}회")
    print(f"  Codex 턴: {state.get('codex_turns', 0)} / 전체 {state.get('total_turns', 0)}턴")


def main():
    parser = argparse.ArgumentParser(description="모드 B STEP 순서 강제")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("enter-b", help="모드 B 진입")
    sub.add_parser("globals-ok", help="전역 변수 확정")
    g = sub.add_parser("gate", help="사용자 게이트 기록")
    g.add_argument("trigger", help="트리거 문자열 (예: [계속], [시작])")
    a = sub.add_parser("advance", help="STEP 완료")
    a.add_argument("step", help="완료된 STEP 번호")
    sub.add_parser("record-codex", help="Codex 턴 기록")
    sub.add_parser("record-turn", help="B모드 턴 기록")
    sub.add_parser("check", help="상태 검증")
    sub.add_parser("reset", help="상태 초기화")
    sub.add_parser("status", help="현재 상태")

    args = parser.parse_args()
    cmd = args.cmd or "status"

    if cmd == "enter-b":
        cmd_enter_b()
    elif cmd == "globals-ok":
        cmd_globals_ok()
    elif cmd == "gate":
        cmd_gate(args.trigger)
    elif cmd == "advance":
        cmd_advance(args.step)
    elif cmd == "record-codex":
        cmd_record_codex()
    elif cmd == "record-turn":
        cmd_record_turn()
    elif cmd == "check":
        cmd_check()
    elif cmd == "reset":
        cmd_reset()
    elif cmd == "status":
        cmd_status()


if __name__ == "__main__":
    main()
