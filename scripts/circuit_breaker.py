#!/usr/bin/env python3
"""
circuit_breaker.py v2 — 3-tier consent system (Citadel inspired)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v1 → v2 변화
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v1은 트리거 발생 시 stderr에 옵션 A/B/C를 "출력만" 함.
v2는 사용자 결정을 기억하고, 다음 동일 트리거에 자동 적용한다.

추가 기능:
  consult          — 🆕 consent 정책대로 결정 반환 (에이전트 호출용)
  configure        — 🆕 트리거별 consent tier 변경
  session-status   — 🆕 세션 내 결정 이력 조회
  reset-session    — 🆕 세션 메모리 초기화

Consent tier:
  always-ask       매번 사용자에게 확인
  session-allow    세션 동안 첫 결정을 기억 (TTL 24h)
  auto-allow       설정된 default_action 무조건 사용 (never_auto_allow=true는 예외)

트리거별 기본 정책 (harness.json에서 변경 가능):
  3_consecutive_fails       session-allow → default: pair_lead_decides
  exceeded_max_iterations   session-allow → default: pair_lead_decides
  token_budget_warning      session-allow → default: null (사용자 지정)
  token_budget_exceeded     always-ask    → never_auto_allow=true (비용 안전장치)

Memory 통합:
  session-allow의 **첫 만남 결정**은 `memory_sync add decision`에 자동 기록.
  이후 재사용은 기록하지 않음 (노이즈 방지).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
.claude/runtime/
├── harness.json            # 설정 (consent 정책 포함)
├── breaker_state.json      # iteration 이력 (v1과 동일)
└── session_consent.yaml    # 🆕 세션 결정 기억 (TTL 24h)

의존성: harness_common.py (같은 디렉토리)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 공용 유틸 import
sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, save_yaml_atomic, atomic_write, load_yaml, HAS_YAML,
        load_json, save_json_atomic, read_modify_write_json,
    )
except ImportError:
    sys.stderr.write("❌ harness_common.py가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)

# ────────────────────────────── 경로 / 상수 ──────────────────────────────

CLAUDE_DIR = Path(".claude")
RUNTIME_DIR = CLAUDE_DIR / "runtime"
CONFIG_FILE = RUNTIME_DIR / "harness.json"
STATE_FILE = RUNTIME_DIR / "breaker_state.json"
CONSENT_FILE = RUNTIME_DIR / "session_consent.yaml"

MEMORY_SCRIPT = Path(__file__).parent / "memory_sync.py"

# 3-tier consent
TIER_ALWAYS_ASK = "always-ask"
TIER_SESSION_ALLOW = "session-allow"
TIER_AUTO_ALLOW = "auto-allow"
VALID_TIERS = [TIER_ALWAYS_ASK, TIER_SESSION_ALLOW, TIER_AUTO_ALLOW]

# 지원되는 action
ACTIONS = {
    "pair_lead_decides": "PAIR-LEAD 독자 결정 (현재 최선안 채택)",
    "escalate_to_user": "사용자 결정 요청 (대안 제시)",
    "halt_and_redesign": "작업 중단 및 재설계",
    "terminate_iteration": "수렴 감지 — iteration 종료 (convergence_detected 용)",
}

# 지원되는 trigger
TRIGGERS = [
    "3_consecutive_fails",
    "exceeded_max_iterations",
    "token_budget_warning",
    "token_budget_exceeded",
    "convergence_detected",   # v2.4.2: 연속 PASS로 수렴 감지
    "codex_rescue_overuse",   # v2.4.3: 세션 내 (구 플러그인) codex:rescue 한도 초과 — 계측 키 보존
]

DEFAULT_CONFIG = {
    "circuit_breaker": {
        "max_iterations": 5,
        "convergence_threshold": 2,
        "token_budget_warning": 50000,
        "token_budget_hard_limit": 100000,
        # v2.4.3 — (구 플러그인) codex:rescue 사용 한도 — 플러그인 제거(2026-07-13) 후 count=0 무해, 계측 로직 보존
        # rescue는 "Claude와 같은 일을 독립적으로 시키는" 모드라 상관된 오류를
        # 낳을 수 있고, 공식 README도 장시간 사용 시 사용량 급증 경고.
        # 기본 비대칭 구조(Claude=Constructive, Codex=Critical)에서는
        # 대부분 codex exec 적대검토(CLI)로 대체되어야 하고,
        # rescue는 "정말 독립된 경로"가 필요한 경우에만 허용된다.
        "codex_rescue_per_session": 3,       # 세션당 hard 상한
        "codex_rescue_warning_at": 2,        # 경고 임계
        "consent": {
            "default_mode": TIER_ALWAYS_ASK,
            "session_ttl_hours": 24,
            "per_trigger": {
                "3_consecutive_fails": {
                    "mode": TIER_SESSION_ALLOW,
                    "default_action": "pair_lead_decides",
                },
                "exceeded_max_iterations": {
                    "mode": TIER_SESSION_ALLOW,
                    "default_action": "pair_lead_decides",
                },
                "token_budget_warning": {
                    "mode": TIER_SESSION_ALLOW,
                    "default_action": None,
                },
                "token_budget_exceeded": {
                    "mode": TIER_ALWAYS_ASK,
                    "default_action": None,
                    "never_auto_allow": True,
                },
                # v2.4.2: 수렴 감지는 "자동 종료" 제안 — 부정적이 아닌 긍정적 신호.
                # 에이전트가 불필요한 iteration을 회피하는 용도. 기본은 자동 통과.
                "convergence_detected": {
                    "mode": TIER_SESSION_ALLOW,
                    "default_action": "terminate_iteration",
                },
                # v2.4.3: rescue 과다 사용은 설계 문제를 시사.
                # "이미 3번 rescue 호출됐음. 정말 또 필요한가?" 를 사용자에게 확인.
                "codex_rescue_overuse": {
                    "mode": TIER_ALWAYS_ASK,
                    "default_action": None,
                    "never_auto_allow": False,  # 사용자가 "이번만 허용" 가능
                },
            },
        },
    }
}


DEFAULT_STATE = {
    "items": {},
    "total_tokens": 0,
    "token_sources": {
        "tool_io_estimate": 0,
        "subagent_transcript_estimate": 0,
        "manual_override": 0,
    },
    "command_counts": {},
    "command_mentions": {},
    "activity": {},
    "processed_transcripts": [],
    "tracking": {
        "skipped_missing_transcript": 0,
        "skipped_unreadable_transcript": 0,
    },
}

# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_dirs():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        with file_lock(CONFIG_FILE, timeout=5.0):
            atomic_write(CONFIG_FILE, json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n")
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.stderr.write(f"⚠️  harness.json 파싱 실패 — 기본값 사용\n")
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    with file_lock(CONFIG_FILE, timeout=5.0):
        atomic_write(CONFIG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def _normalize_state(state: dict | None) -> dict:
    normalized = load_json(STATE_FILE, default=DEFAULT_STATE) if state is None else state
    normalized.setdefault("items", {})
    normalized.setdefault("total_tokens", 0)
    ts = normalized.setdefault("token_sources", {})
    ts.setdefault("tool_io_estimate", 0)
    ts.setdefault("subagent_transcript_estimate", 0)
    ts.setdefault("manual_override", 0)
    normalized.setdefault("command_counts", {})
    normalized.setdefault("command_mentions", {})
    normalized.setdefault("activity", {})
    normalized.setdefault("processed_transcripts", [])
    tr = normalized.setdefault("tracking", {})
    tr.setdefault("skipped_missing_transcript", 0)
    tr.setdefault("skipped_unreadable_transcript", 0)
    if isinstance(normalized.get("processed_transcripts"), list):
        normalized["processed_transcripts"] = normalized["processed_transcripts"][-500:]
    return normalized


def load_state() -> dict:
    ensure_dirs()
    return _normalize_state(load_json(STATE_FILE, default=DEFAULT_STATE))


def save_state(state: dict):
    ensure_dirs()
    save_json_atomic(STATE_FILE, _normalize_state(state))


# ────────────────────────────── Session consent 관리 ──────────────────────────────


def load_consent_session() -> dict:
    """세션 consent 파일 로드. TTL 만료 시 자동 무효화."""
    ensure_dirs()
    if not CONSENT_FILE.exists():
        return _new_session_consent()

    data = load_yaml(CONSENT_FILE)
    if not data or "session_id" not in data:
        return _new_session_consent()

    # TTL 확인
    cfg = load_config()
    ttl_hours = cfg["circuit_breaker"].get("consent", {}).get("session_ttl_hours", 24)
    try:
        session_start = datetime.fromisoformat(data["session_id"])
        if datetime.now() - session_start > timedelta(hours=ttl_hours):
            return _new_session_consent()
    except ValueError:
        return _new_session_consent()

    return data


def _new_session_consent(ttl_hours: int | None = None) -> dict:
    if ttl_hours is None:
        cfg = load_config()
        ttl_hours = cfg["circuit_breaker"].get("consent", {}).get("session_ttl_hours", 24)
    return {
        "session_id": datetime.now().isoformat(timespec="seconds"),
        "ttl_hours": ttl_hours,
        "decisions": {},
    }


def save_consent_session(data: dict):
    with file_lock(CONSENT_FILE, timeout=5.0):
        save_yaml_atomic(CONSENT_FILE, data)


def trigger_policy(cfg: dict, trigger_type: str) -> dict:
    """특정 트리거의 consent 정책 반환 (기본값 fallback 포함)."""
    consent_cfg = cfg["circuit_breaker"].get("consent", {})
    per_trigger = consent_cfg.get("per_trigger", {})
    default_mode = consent_cfg.get("default_mode", TIER_ALWAYS_ASK)

    policy = per_trigger.get(trigger_type, {})
    return {
        "mode": policy.get("mode", default_mode),
        "default_action": policy.get("default_action"),
        "never_auto_allow": policy.get("never_auto_allow", False),
    }


# ────────────────────────────── 과거 기록 조회 (Memory 연동) ──────────────────────────────


def _get_past_decisions(trigger_type: str, limit: int = 5) -> list[dict]:
    """decisions.md와 아카이브에서 같은 trigger_type의 과거 기록을 조회.

    Memory가 없거나 비어있으면 빈 리스트 반환 (조용히).
    최신순 정렬, 최대 limit개 반환.
    """
    import re

    decisions_files: list[Path] = []
    main = Path(".claude/memory/decisions.md")
    if main.exists():
        decisions_files.append(main)
    archive_dir = Path(".claude/memory/_archive")
    if archive_dir.exists():
        decisions_files.extend(archive_dir.glob("decisions-archive-*.md"))

    if not decisions_files:
        return []

    results: list[dict] = []
    for f in decisions_files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        # "## YYYY-MM-DD" 경계로 블록 분할
        blocks = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", text)
        for block in blocks:
            block = block.lstrip()
            date_match = re.match(r"## (\d{4}-\d{2}-\d{2})", block)
            if not date_match:
                continue
            if "[circuit_breaker]" not in block:
                continue
            # 트리거 일치 확인
            trigger_match = re.search(r"트리거 '([^']+)'", block)
            if not trigger_match or trigger_match.group(1) != trigger_type:
                continue
            # action 추출
            action_match = re.search(r"'([^']+)' 선택", block)
            if not action_match:
                continue
            # 재사용 횟수가 기록되어 있으면 추출 (옵션)
            applied_match = re.search(r"applied_count:\s*(\d+)", block)
            results.append({
                "date": date_match.group(1),
                "action": action_match.group(1),
                "applied_count": int(applied_match.group(1)) if applied_match else None,
            })

    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:limit]


def _summarize_past(past: list[dict]) -> dict:
    """과거 기록 요약 — 총 건수, action별 빈도, 최다 선택."""
    if not past:
        return {"total": 0, "by_action": {}, "most_common_action": None, "most_common_count": 0}
    from collections import Counter
    counts = Counter(d["action"] for d in past)
    most_common = counts.most_common(1)[0]
    return {
        "total": len(past),
        "by_action": dict(counts),
        "most_common_action": most_common[0],
        "most_common_count": most_common[1],
    }


# ────────────────────────────── record ──────────────────────────────


def cmd_record(args):
    """iteration 결과 기록 + 자동 트리거 검사.

    hardened:
      - breaker_state.json 갱신을 원자적 JSON RMW로 수행
      - verified_pass는 record 시점 자기 보고를 신뢰하지 않음
      - --tokens / --command 는 레거시 override로만 유지
    """
    ensure_dirs()
    item_id, iteration, status = args.item_id, int(args.iteration), args.status

    with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
        state = _normalize_state(state)
        if item_id not in state["items"]:
            state["items"][item_id] = {"iterations": [], "consecutive_fails": 0}

        entry = {
            "iteration": iteration,
            "status": status,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "major": int(args.major or 0),
            "evidence": list(args.evidence or []),
            "verified_pass": False,
            "self_reported_verified_pass": bool(args.verified_pass),
        }
        state["items"][item_id]["iterations"].append(entry)
        if status == "FAIL":
            state["items"][item_id]["consecutive_fails"] += 1
        else:
            state["items"][item_id]["consecutive_fails"] = 0

        if args.tokens:
            tokens = int(args.tokens)
            state["total_tokens"] = state.get("total_tokens", 0) + tokens
            ts = state.setdefault("token_sources", {})
            ts["manual_override"] = ts.get("manual_override", 0) + tokens

        if args.command:
            cmds = state.setdefault("command_counts", {})
            cmds[args.command] = cmds.get(args.command, 0) + 1

        if isinstance(state.get("processed_transcripts"), list):
            state["processed_transcripts"] = state["processed_transcripts"][-500:]

    state = load_state()
    print(f"✅ 기록: {item_id} #{iteration} → {status}" + (f" (+{args.tokens} tokens)" if args.tokens else "") + (f" [cmd={args.command}]" if args.command else "") + (" [self-reported verified ignored]" if args.verified_pass else ""))

    triggered = detect_triggers(state, load_config())
    item_triggers = [t for t in triggered if t.get("item") == item_id or "item" not in t]
    if item_triggers:
        print("🚨 트리거 발생:")
        for t in item_triggers:
            print(f"   → {t['type']}" + (f" (item: {t['item']})" if "item" in t else ""))
        print("\n→ 'consult' 명령으로 결정을 받으세요:")
        for t in item_triggers:
            item_arg = t.get("item", "")
            print(f"   python {sys.argv[0]} consult {t['type']} {item_arg}")


# ────────────────────────────── track-activity (v2.4.4) ──────────────────────────────


def cmd_track_activity(args):
    """PostToolUse hook이 호출. stdin JSON에서 tool I/O 크기 추출해 자동 집계.

    hardened:
      - breaker_state 갱신을 JSON RMW로 원자화
      - token_sources.tool_io_estimate 에 provenance 분리 저장
    """
    ensure_dirs()
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, Exception):
        return

    tool_input = event.get("tool_input", {}) or {}
    tool_response = event.get("tool_response", {}) or {}

    def _size(obj) -> int:
        if isinstance(obj, str):
            return len(obj)
        if isinstance(obj, (dict, list)):
            try:
                return len(json.dumps(obj, ensure_ascii=False))
            except Exception:
                return 0
        return len(str(obj)) if obj else 0

    input_chars = _size(tool_input)
    output_chars = _size(tool_response)
    total_chars = input_chars + output_chars
    estimated_tokens = max(1, total_chars // 4)

    with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
        state = _normalize_state(state)
        state["total_tokens"] = state.get("total_tokens", 0) + estimated_tokens
        ts = state.setdefault("token_sources", {})
        ts["tool_io_estimate"] = ts.get("tool_io_estimate", 0) + estimated_tokens
        state.setdefault("activity", {})
        state["activity"]["total_chars"] = state["activity"].get("total_chars", 0) + total_chars
        state["activity"]["tool_calls"] = state["activity"].get("tool_calls", 0) + 1

    payload = {"status": "ok", "estimated_tokens": estimated_tokens, "chars": total_chars, "tool": event.get("tool_name", "?")}
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False))
    else:
        sys.stderr.write(f"[cb track-activity] +{estimated_tokens}t (tool={event.get('tool_name','?')}, chars={total_chars})\n")


def cmd_track_subagent_command(args):
    """SubagentStop hook transcript를 파싱해 codex:* 명령 사용을 자동 집계한다.

    hardened:
      - transcript_path 부재/읽기 실패를 조용히 삼키지 않고 JSON status로 반환
      - breaker_state 갱신을 JSON RMW로 원자화
      - command_counts(actual) 와 command_mentions(언급) 분리
      - transcript 길이를 기반으로 subagent token estimate 누적
    """
    ensure_dirs()
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    transcript_path = event.get("transcript_path")
    if not transcript_path:
        with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
            state = _normalize_state(state)
            tracking = state.setdefault("tracking", {})
            tracking["skipped_missing_transcript"] = tracking.get("skipped_missing_transcript", 0) + 1
        out = {"status": "skipped_missing_transcript"}
        if getattr(args, "format", "text") == "json":
            print(json.dumps(out, ensure_ascii=False))
        return

    transcript = Path(transcript_path)
    try:
        text = transcript.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
            state = _normalize_state(state)
            tracking = state.setdefault("tracking", {})
            tracking["skipped_unreadable_transcript"] = tracking.get("skipped_unreadable_transcript", 0) + 1
        out = {"status": "skipped_unreadable_transcript", "path": str(transcript)}
        if getattr(args, "format", "text") == "json":
            print(json.dumps(out, ensure_ascii=False))
        return

    # v2.4.5-hardened 하이브리드: 두 가지 actual 신호를 인식
    # (1) 공식 플러그인 슬래시: "$ /codex:adversarial-review" 등 프롬프트 라인
    #     (openai/codex-plugin-cc 가 /codex:review, /codex:adversarial-review,
    #      /codex:rescue, /codex:status, /codex:result, /codex:cancel 제공)
    # (2) 하네스 커스텀 래퍼: "node scripts/codex_call.mjs cross-pair-challenge"
    #     (공식 플러그인에 없는 하네스 고유 프롬프트 전용)
    # (3) codex exec 직접 호출: "codex exec ..."
    mention_cmds = re.findall(r"(?:/)?(codex:(?:adversarial-review|review|rescue|status|result|cancel))\b", text)

    actual_cmds_slash = re.findall(
        r"^(?:>\s*|\$\s*|command:\s*|tool_input:.*?)(?:/)?(codex:(?:adversarial-review|review|rescue|status|result|cancel))\b",
        text, re.MULTILINE
    )
    # 하네스 커스텀 래퍼 호출 감지 — 공식 플러그인에 없는 프롬프트만
    # cross-pair-challenge는 페어 간 명시적 도전으로 하네스 고유 기능
    harness_wrapper_names = re.findall(
        r"codex_call\.(?:mjs|sh)\s+(cross-pair-challenge)\b",
        text
    )
    actual_cmds_wrapper = [f"codex:{name}" for name in harness_wrapper_names]
    # codex exec 직접 호출 — 프롬프트 이름을 추출할 수 없으면 'exec-direct'로 기록
    exec_direct_count = len(re.findall(r"\bcodex\s+exec\b", text))

    actual_cmds = actual_cmds_slash + actual_cmds_wrapper
    # (의도적으로 과거 fallback 정규식 제거 — mention/actual 구분 무너뜨렸음)

    estimated_tokens = max(1, len(text) // 4)

    with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
        state = _normalize_state(state)
        processed = state.setdefault("processed_transcripts", [])
        if transcript_path in processed:
            out = {"status": "duplicate_transcript", "path": transcript_path}
            if getattr(args, "format", "text") == "json":
                print(json.dumps(out, ensure_ascii=False))
            return
        counts = state.setdefault("command_counts", {})
        mentions = state.setdefault("command_mentions", {})
        for cmd in mention_cmds: mentions[cmd] = mentions.get(cmd, 0) + 1
        for cmd in actual_cmds: counts[cmd] = counts.get(cmd, 0) + 1
        if exec_direct_count > 0:
            counts["codex:exec-direct"] = counts.get("codex:exec-direct", 0) + exec_direct_count
        state["total_tokens"] = state.get("total_tokens", 0) + estimated_tokens
        ts = state.setdefault("token_sources", {})
        ts["subagent_transcript_estimate"] = ts.get("subagent_transcript_estimate", 0) + estimated_tokens
        processed.append(transcript_path)
        state["processed_transcripts"] = processed[-500:]
        rescue_count = counts.get("codex:rescue", 0)
        rescue_mentions = mentions.get("codex:rescue", 0)

    cfg = load_config()["circuit_breaker"]
    rescue_warn = cfg.get("codex_rescue_warning_at", 2)
    rescue_hard = cfg.get("codex_rescue_per_session", 3)
    if rescue_count >= rescue_warn:
        sys.stderr.write(f"[cb track-subagent-command] codex:rescue actual {rescue_count}/{rescue_hard}회 누적 (mentions={rescue_mentions})\n")

    out = {"status": "ok", "path": transcript_path, "estimated_tokens": estimated_tokens, "command_counts_delta": {cmd: actual_cmds.count(cmd) for cmd in sorted(set(actual_cmds))}, "command_mentions_delta": {cmd: mention_cmds.count(cmd) for cmd in sorted(set(mention_cmds))}}
    if getattr(args, "format", "text") == "json":
        print(json.dumps(out, ensure_ascii=False))


# ────────────────────────────── detect_triggers (내부) ──────────────────────────────


def detect_triggers(state: dict, cfg: dict) -> list[dict]:
    """트리거 조건 검사.

    hardened:
      - convergence_detected는 verified_pass=True 인 iteration만 사용
      - max_iterations 도달 시 convergence 신호를 동시에 올리지 않음
      - token/command tracking degraded 상태를 함께 노출
    """
    state = _normalize_state(state)
    cb = cfg["circuit_breaker"]
    triggers = []
    max_iter = cb.get("max_iterations", 5)
    conv_threshold = cb.get("convergence_threshold", 2)

    for item_id, item_data in state.get("items", {}).items():
        fails = item_data.get("consecutive_fails", 0)
        iterations = item_data.get("iterations", [])
        at_limit = len(iterations) >= max_iter
        if fails >= 3:
            triggers.append({"type": "3_consecutive_fails", "item": item_id})
        if at_limit:
            triggers.append({"type": "exceeded_max_iterations", "item": item_id})
        if (not at_limit) and len(iterations) >= conv_threshold:
            recent = iterations[-conv_threshold:]
            if all(it.get("status") == "PASS" and it.get("verified_pass") for it in recent):
                triggers.append({"type": "convergence_detected", "item": item_id, "consecutive_passes": conv_threshold})

    tokens = state.get("total_tokens", 0)
    if tokens > cb.get("token_budget_hard_limit", 100000):
        triggers.append({"type": "token_budget_exceeded", "tokens": tokens})
    elif tokens > cb.get("token_budget_warning", 50000):
        triggers.append({"type": "token_budget_warning", "tokens": tokens})

    rescue_hard = cb.get("codex_rescue_per_session", 3)
    rescue_warn = cb.get("codex_rescue_warning_at", 2)
    rescue_count = state.get("command_counts", {}).get("codex:rescue", 0)
    rescue_mentions = state.get("command_mentions", {}).get("codex:rescue", 0)
    if rescue_count >= rescue_hard:
        triggers.append({"type": "codex_rescue_overuse", "count": rescue_count, "limit": rescue_hard, "mentions": rescue_mentions})
    elif rescue_count >= rescue_warn:
        sys.stderr.write(f"ℹ️  (구 플러그인) codex:rescue actual {rescue_count}/{rescue_hard}회 사용됨 (mentions={rescue_mentions}). 가급적 codex exec 적대검토(CLI)로 전환.\n")

    tracking = state.get("tracking", {})
    if tracking.get("skipped_missing_transcript", 0) or tracking.get("skipped_unreadable_transcript", 0):
        triggers.append({"type": "tracking_degraded", "skipped_missing_transcript": tracking.get("skipped_missing_transcript", 0), "skipped_unreadable_transcript": tracking.get("skipped_unreadable_transcript", 0)})

    seen = set()
    unique = []
    for t in triggers:
        key = (t["type"], t.get("item"))
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


# ────────────────────────────── approve-pass ──────────────────────────────


def cmd_approve_pass(args):
    """record된 PASS iteration을 evidence 기반 verified_pass로 승격한다."""
    item_id = args.item_id
    iteration = int(args.iteration)
    evidence = list(args.evidence or [])
    approved_by = (args.approved_by or "").strip()
    if not approved_by:
        sys.stderr.write("❌ --approved-by 가 필요합니다.\n") ; sys.exit(1)
    if not evidence:
        sys.stderr.write("❌ 최소 1개의 --evidence 가 필요합니다.\n") ; sys.exit(1)
    for ev in evidence:
        if ev.startswith("artifact:") or ev.startswith("test:"):
            path = Path(ev.split(":", 1)[1])
            if not path.exists():
                sys.stderr.write(f"❌ evidence 경로 없음: {path}\n") ; sys.exit(1)
    updated = False
    with read_modify_write_json(STATE_FILE, default=DEFAULT_STATE, timeout=10.0) as state:
        state = _normalize_state(state)
        item = state.get("items", {}).get(item_id)
        if not item:
            sys.stderr.write(f"❌ item 없음: {item_id}\n") ; sys.exit(1)
        for it in item.get("iterations", []):
            if int(it.get("iteration", -1)) == iteration:
                if it.get("status") != "PASS":
                    sys.stderr.write("❌ PASS iteration만 승인할 수 있습니다.\n") ; sys.exit(1)
                if int(it.get("major", 0)) != 0:
                    sys.stderr.write("❌ unresolved major > 0 인 iteration은 승인할 수 없습니다.\n") ; sys.exit(1)
                it["verified_pass"] = True
                it["evidence"] = evidence
                it["approved_by"] = approved_by
                it["approved_at"] = datetime.now().isoformat(timespec="seconds")
                updated = True
                break
    if not updated:
        sys.stderr.write(f"❌ iteration 없음: {item_id} #{iteration}\n") ; sys.exit(1)
    out = {"status": "approved", "item": item_id, "iteration": iteration, "approved_by": approved_by, "evidence": evidence}
    if getattr(args, "format", "text") == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"✅ verified PASS 승인: {item_id} #{iteration} by {approved_by}")

# ────────────────────────────── check ──────────────────────────────


def cmd_check(args):
    """현재 트리거 상태 확인."""
    state = load_state()
    cfg = load_config()
    triggered = detect_triggers(state, cfg)

    if args.format == "json":
        print(json.dumps({"triggered": triggered}, ensure_ascii=False, indent=2))
        return

    if not triggered:
        print("✅ 정상 — 트리거된 조건 없음")
        return
    print("🚨 현재 트리거된 조건:")
    for t in triggered:
        detail = f" (item: {t['item']})" if "item" in t else f" (tokens: {t.get('tokens')})"
        print(f"  → {t['type']}{detail}")


# ────────────────────────────── consult (핵심 신규) ──────────────────────────────


def cmd_consult(args):
    """Consent 정책에 따라 트리거 처리 결정을 반환."""
    trigger_type = args.trigger_type
    item_id = args.item or ""

    if trigger_type not in TRIGGERS:
        _out({"error": f"지원 안 되는 trigger: {trigger_type}",
              "supported": TRIGGERS}, args.format)
        sys.exit(1)

    cfg = load_config()
    policy = trigger_policy(cfg, trigger_type)
    mode = policy["mode"]
    default_action = policy["default_action"]

    # 세션 consent 로드
    session = load_consent_session()
    session_key = f"{trigger_type}:{item_id}" if item_id else trigger_type

    # ── 분기 1: auto-allow ──
    if mode == TIER_AUTO_ALLOW:
        if policy["never_auto_allow"]:
            # 안전장치 — auto-allow 무력화
            _out({
                "error": f"'{trigger_type}'는 never_auto_allow 설정. always-ask로 처리.",
            }, args.format, exit_code=2)
            mode = TIER_ALWAYS_ASK  # fallback
        else:
            if not default_action:
                _out({"error": "auto-allow인데 default_action 미설정"}, args.format, exit_code=1)
                sys.exit(1)
            _out({
                "action": default_action,
                "reason": "auto-allow",
                "trigger": trigger_type,
                "source": "config.default",
            }, args.format)
            return

    # ── 분기 2: session-allow + 캐시 히트 ──
    if mode == TIER_SESSION_ALLOW:
        cached = session["decisions"].get(session_key)
        if cached:
            cached["applied_count"] = cached.get("applied_count", 1) + 1
            save_consent_session(session)
            _out({
                "action": cached["chosen_action"],
                "reason": "session-allow cached",
                "trigger": trigger_type,
                "cached_at": cached.get("granted_at"),
                "applied_count": cached["applied_count"],
                "source": "session.cache",
            }, args.format)
            return

    # ── 분기 3: 사용자 입력 필요 (always-ask 또는 session-allow 첫 만남) ──
    # 과거 동일 trigger 기록을 Memory에서 자동 조회 (신규 기능)
    past = _get_past_decisions(trigger_type, limit=5)
    past_summary = _summarize_past(past)

    # TTY 감지로 대화형/비대화형 분기
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    if args.format == "json" or not is_tty:
        # 비대화형: 에이전트가 사용자에게 직접 물어봐야 함을 알림
        _out({
            "status": "user_input_required",
            "trigger": trigger_type,
            "item": item_id,
            "mode": mode,
            "reason": "first_encounter" if mode == TIER_SESSION_ALLOW else "always_ask",
            "options": [
                {"key": k, "description": v} for k, v in ACTIONS.items()
            ],
            "past_decisions": past,
            "past_summary": past_summary,
            "hint": f"사용자 선택을 받아 다음 명령으로 기록: "
                    f"python {sys.argv[0]} consult {trigger_type} {item_id} "
                    f"--user-choice <action_key>",
        }, args.format, exit_code=0)
        return

    # 대화형: 터미널에서 직접 프롬프트 (과거 기록도 표시)
    chosen = _interactive_prompt(trigger_type, item_id, mode, past, past_summary)
    _record_decision(session, session_key, trigger_type, chosen, mode, cfg)
    _out({
        "action": chosen,
        "reason": f"{mode} first_encounter" if mode == TIER_SESSION_ALLOW else mode,
        "trigger": trigger_type,
        "source": "user_input",
    }, args.format)


def _interactive_prompt(trigger_type: str, item_id: str, mode: str,
                        past: list[dict] | None = None,
                        past_summary: dict | None = None) -> str:
    """대화형 터미널에서 사용자 선택 받기 (과거 기록 표시 포함)."""
    past = past or []
    past_summary = past_summary or {}
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🚨 Circuit Breaker — {trigger_type}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if item_id:
        print(f"아이템: {item_id}")
    print(f"Consent 모드: {mode}"
          + (" (새 세션 — 선택 시 세션 동안 자동 적용)" if mode == TIER_SESSION_ALLOW else ""))

    # 과거 기록 표시 (신규)
    if past:
        print(f"\n📚 과거 '{trigger_type}' 기록 ({past_summary.get('total', 0)}건):")
        for p in past:
            count_str = f" (재사용 {p['applied_count']}회)" if p.get("applied_count") else ""
            print(f"   • {p['date']} — {p['action']}{count_str}")
        if past_summary.get("most_common_count", 0) > 1:
            print(f"   주로 선택한 것: {past_summary['most_common_action']} "
                  f"({past_summary['most_common_count']}/{past_summary['total']}회)")

    print()
    keys = list(ACTIONS.keys())
    past_actions = {p["action"] for p in past}
    for i, (key, desc) in enumerate(ACTIONS.items(), 1):
        # 과거에 선택한 적 있으면 마커
        marker = " ← 과거 선택" if key in past_actions else ""
        # 최다 선택이면 강조
        if key == past_summary.get("most_common_action") and past_summary.get("most_common_count", 0) > 1:
            marker = " ← 주로 선택"
        print(f"  [{i}] {key}{marker}")
        print(f"       {desc}")
    print()
    while True:
        choice = input(f"선택 (1-{len(keys)} 또는 action key): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            return keys[int(choice) - 1]
        if choice in keys:
            return choice
        print(f"  ❌ 1-{len(keys)} 또는 action key 중 선택")


def _record_decision(session: dict, key: str, trigger_type: str,
                     action: str, mode: str, cfg: dict):
    """세션 consent에 결정 저장 + memory 통합 (Q4)."""
    if mode == TIER_SESSION_ALLOW:
        session["decisions"][key] = {
            "mode": mode,
            "trigger_type": trigger_type,
            "chosen_action": action,
            "granted_at": datetime.now().isoformat(timespec="seconds"),
            "applied_count": 1,
        }
        save_consent_session(session)
        # Q4: session-allow 첫 만남만 memory에 기록
        _record_to_memory(trigger_type, action, key)
    # always-ask는 세션에 저장하지 않음


def _record_to_memory(trigger_type: str, action: str, key: str):
    """Circuit breaker 결정을 memory_sync의 결정사항에 기록."""
    if not MEMORY_SCRIPT.exists():
        return  # memory_sync.py 없으면 조용히 스킵
    msg = (f"[circuit_breaker] 트리거 '{trigger_type}' (키: {key})에 대해 "
           f"session 동안 '{action}' 선택. "
           f"TTL 내 재발생 시 자동 적용.")
    try:
        subprocess.run(
            [sys.executable, str(MEMORY_SCRIPT), "add", "decision", msg],
            capture_output=True, timeout=10, check=False,
        )
    except Exception:
        pass  # memory 기록 실패는 circuit breaker 흐름을 방해하지 않음


def cmd_consult_user_choice(args):
    """비대화형 모드에서 사용자 선택을 받은 후 저장 (에이전트 호출용)."""
    trigger_type = args.trigger_type
    item_id = args.item or ""
    user_choice = args.user_choice

    if user_choice not in ACTIONS:
        _out({"error": f"잘못된 action: {user_choice}",
              "valid": list(ACTIONS.keys())}, args.format, exit_code=1)
        sys.exit(1)

    cfg = load_config()
    policy = trigger_policy(cfg, trigger_type)
    mode = policy["mode"]
    session = load_consent_session()
    session_key = f"{trigger_type}:{item_id}" if item_id else trigger_type

    _record_decision(session, session_key, trigger_type, user_choice, mode, cfg)
    _out({
        "action": user_choice,
        "reason": f"{mode} user_input (non-interactive)",
        "trigger": trigger_type,
        "source": "user_input_recorded",
    }, args.format)


# ────────────────────────────── configure ──────────────────────────────


def cmd_configure(args):
    """특정 트리거의 consent tier 변경."""
    if args.trigger not in TRIGGERS:
        sys.stderr.write(f"❌ 지원 안 되는 trigger: {args.trigger}\n"
                         f"   지원: {TRIGGERS}\n")
        sys.exit(1)
    if args.mode not in VALID_TIERS:
        sys.stderr.write(f"❌ 잘못된 mode: {args.mode}\n"
                         f"   지원: {VALID_TIERS}\n")
        sys.exit(1)

    cfg = load_config()
    per_trigger = cfg["circuit_breaker"].setdefault("consent", {}).setdefault("per_trigger", {})
    entry = per_trigger.setdefault(args.trigger, {})

    # never_auto_allow 체크
    if args.mode == TIER_AUTO_ALLOW and entry.get("never_auto_allow"):
        sys.stderr.write(f"❌ '{args.trigger}'는 never_auto_allow 설정. auto-allow로 변경 불가.\n")
        sys.exit(1)

    entry["mode"] = args.mode
    if args.default_action:
        if args.default_action not in ACTIONS:
            sys.stderr.write(f"❌ 잘못된 default_action. 지원: {list(ACTIONS.keys())}\n")
            sys.exit(1)
        entry["default_action"] = args.default_action

    save_config(cfg)
    print(f"✅ {args.trigger} → mode: {args.mode}"
          + (f", default_action: {args.default_action}" if args.default_action else ""))


# ────────────────────────────── session-status ──────────────────────────────


def cmd_session_status(args):
    """현재 세션의 consent 결정 이력 출력."""
    session = load_consent_session()
    decisions = session.get("decisions", {})

    if args.format == "json":
        print(json.dumps(session, ensure_ascii=False, indent=2))
        return

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📋 Session Consent 상태")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"세션 시작:    {session.get('session_id', '-')}")
    print(f"TTL:          {session.get('ttl_hours', 24)}시간")
    print(f"저장된 결정:  {len(decisions)}개\n")

    if not decisions:
        print("  (세션 내 결정 없음)")
        return

    for key, d in decisions.items():
        print(f"  • {key}")
        print(f"      action: {d['chosen_action']}")
        print(f"      granted: {d['granted_at']}")
        print(f"      applied: {d.get('applied_count', 1)}회")
        print()


# ────────────────────────────── reset-session ──────────────────────────────


def cmd_reset_session(args):
    """세션 consent 메모리 초기화."""
    if CONSENT_FILE.exists():
        with file_lock(CONSENT_FILE, timeout=5.0):
            new_session = _new_session_consent()
            save_yaml_atomic(CONSENT_FILE, new_session)
        print(f"✅ Session consent 초기화됨 (새 세션 ID: {new_session['session_id']})")
    else:
        print("ℹ️  저장된 세션 consent 없음")


# ────────────────────────────── escalate (deprecated) ──────────────────────────────


def cmd_escalate(args):
    """v1 호환: stderr에 경고 메시지 출력 + consult 안내."""
    state = load_state()
    if args.item_id not in state.get("items", {}):
        sys.stderr.write(f"❌ 아이템 없음: {args.item_id}\n")
        return
    sys.stderr.write(
        "⚠️  'escalate' 명령은 deprecated. 대신 아래 사용:\n"
        f"   python {sys.argv[0]} consult <trigger_type> {args.item_id}\n"
    )


# ────────────────────────────── 유틸: 출력 형식 ──────────────────────────────


def _out(data: dict, fmt: str, exit_code: int = 0):
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if "error" in data:
            sys.stderr.write(f"❌ {data['error']}\n")
        elif "status" in data and data["status"] == "user_input_required":
            print("🚨 사용자 입력 필요:")
            print(f"   trigger: {data['trigger']}")
            print(f"   item:    {data.get('item', '-')}")
            print(f"   reason:  {data['reason']}")

            # 과거 기록 요약 (신규)
            past = data.get("past_decisions", [])
            summary = data.get("past_summary", {})
            if past:
                print(f"   📚 과거 기록 ({summary.get('total', 0)}건):")
                for p in past[:5]:
                    print(f"     • {p['date']} — {p['action']}")
                if summary.get("most_common_count", 0) > 1:
                    print(f"     주로: {summary['most_common_action']} "
                          f"({summary['most_common_count']}회)")

            print(f"   options:")
            for opt in data["options"]:
                # 과거 선택에 표시
                past_actions = {p["action"] for p in past}
                marker = " ← 과거" if opt["key"] in past_actions else ""
                print(f"     {opt['key']}{marker} — {opt['description']}")
            print(f"\n   {data['hint']}")
        elif "action" in data:
            print(f"✅ 결정: {data['action']}")
            print(f"   근거: {data['reason']}")
            if "applied_count" in data:
                print(f"   (세션 내 재사용: {data['applied_count']}회)")


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Circuit Breaker v2 — 3-tier consent system",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # record
    rec = sub.add_parser("record", help="iteration 결과 기록")
    rec.add_argument("item_id")
    rec.add_argument("iteration")
    rec.add_argument("status", choices=["PASS", "FAIL"])
    rec.add_argument("--tokens", type=int, help="이번 iteration 토큰 사용량 (레거시 — 자발적 보고)")
    rec.add_argument("--command",
                     help="이번 iteration에서 호출한 특수 명령 (예: codex:rescue). "
                          "호출 수 추적 — 상태 기반 제한 판단에 사용.")
    rec.add_argument("--major", type=int, default=0, help="해결되지 않은 Major 이슈 수")
    rec.add_argument("--evidence", action="append", default=[],
                     help="PASS 근거 (예: test:pytest, artifact:PLAN.md). 여러 번 지정 가능")
    rec.add_argument("--verified-pass", action="store_true",
                     help="증거 기반 PASS로 강제 표기. 지정 없으면 major=0 && evidence 존재 시 자동 참")

    # v2.4.4: track-activity — PostToolUse hook이 호출, tool I/O 크기를 자동 집계
    ta = sub.add_parser("track-activity",
                        help="Tool 활동량 자동 집계 (hook이 호출). "
                             "stdin JSON에서 tool_input·tool_response 크기 추출.")
    ta.add_argument("--format", choices=["text", "json"], default="text")

    tsc = sub.add_parser("track-subagent-command",
                         help="SubagentStop transcript를 파싱해 codex:* 명령 사용을 자동 집계")
    tsc.add_argument("--format", choices=["text", "json"], default="text")

    ap = sub.add_parser("approve-pass", help="PASS iteration을 evidence 기반 verified_pass로 승인")
    ap.add_argument("item_id")
    ap.add_argument("iteration")
    ap.add_argument("--approved-by", required=True)
    ap.add_argument("--evidence", action="append", default=[])
    ap.add_argument("--format", choices=["text", "json"], default="text")

    # check
    ch = sub.add_parser("check", help="현재 트리거 상태 검사")
    ch.add_argument("--format", choices=["text", "json"], default="text")

    # consult (핵심 신규)
    co = sub.add_parser("consult", help="consent 정책대로 결정 반환")
    co.add_argument("trigger_type", choices=TRIGGERS)
    co.add_argument("item", nargs="?", default="")
    co.add_argument("--format", choices=["text", "json"], default="text")
    co.add_argument("--user-choice", choices=list(ACTIONS.keys()),
                    help="비대화형 모드에서 사용자 선택을 바로 전달 (에이전트용)")

    # configure
    cf = sub.add_parser("configure", help="트리거별 consent tier 변경")
    cf.add_argument("--trigger", required=True, choices=TRIGGERS)
    cf.add_argument("--mode", required=True, choices=VALID_TIERS)
    cf.add_argument("--default-action", dest="default_action",
                    choices=list(ACTIONS.keys()))

    # session-status
    ss = sub.add_parser("session-status", help="세션 consent 결정 이력")
    ss.add_argument("--format", choices=["text", "json"], default="text")

    # reset-session
    sub.add_parser("reset-session", help="세션 consent 초기화")

    # escalate (deprecated)
    esc = sub.add_parser("escalate", help="(deprecated) consult 사용 권장")
    esc.add_argument("item_id")

    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "record":
        cmd_record(args)
    elif args.cmd == "track-subagent-command":
        cmd_track_subagent_command(args)
    elif args.cmd == "approve-pass":
        cmd_approve_pass(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "consult":
        if args.user_choice:
            cmd_consult_user_choice(args)
        else:
            cmd_consult(args)
    elif args.cmd == "configure":
        cmd_configure(args)
    elif args.cmd == "session-status":
        cmd_session_status(args)
    elif args.cmd == "reset-session":
        cmd_reset_session(args)
    elif args.cmd == "escalate":
        cmd_escalate(args)
    elif args.cmd == "track-activity":
        cmd_track_activity(args)


if __name__ == "__main__":
    main()
