#!/usr/bin/env python3
"""human_proxy.py — Human Proxy Agent (HPA) for the harness.

AutoGen UserProxyAgent 패턴을 하네스에 이식.
다른 에이전트(c-/x-/leader/debater 등)가 인간 결정이 필요한 시점에
이 에이전트에게 메시지를 보내면, mode 정책에 따라 자동 응답하거나
실제 사용자에게 묻는다.

3 모드 (AutoGen 호환):
    ALWAYS    - 매 호출마다 인간에게 묻는다
    TERMINATE - max_auto_reply 도달 또는 termination 메시지일 때만 묻는다
    NEVER     - 절대 묻지 않고 자동 응답만 한다

Storage layout (per-project):
    .claude/runtime/
        hpa_pending/<req_id>.yaml      대기 중인 요청
        hpa_responses/<req_id>.yaml    완료된 응답
        hpa_state.json                  세션 카운터·configuration
        hpa_log.jsonl                   append-only audit log

CLI usage (다른 에이전트가 호출):
    python scripts/human_proxy.py ask \\
        --sender x-sar \\
        --message "InSAR 위상 언래핑 vs MCF — 어느 쪽?" \\
        --options InSAR 위상 언래핑 MCF abort \\
        --mode TERMINATE \\
        --timeout 300

CLI usage (사용자/대시보드가 응답):
    python scripts/human_proxy.py respond <req_id> --choice InSAR 위상 언래핑
    python scripts/human_proxy.py list-pending
    python scripts/human_proxy.py status

동시성:
    - 모든 상태 파일은 harness_common 의 file_lock + atomic_write 사용
    - req_id 는 timestamp + random 16-bit 로 충돌 방지
    - 여러 워크트리/터미널 병렬 호출 안전
"""

from __future__ import annotations
import argparse
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# 공용 인프라 (반드시 같은 디렉토리에 있어야 함)
try:
    from harness_common import (
        file_lock, atomic_write, save_yaml_atomic, load_yaml,
        save_json_atomic, load_json, read_modify_write_json,
        append_line_atomic, now_iso,
    )
except ImportError:
    sys.stderr.write("❌ harness_common.py 가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────────

VALID_MODES = ("ALWAYS", "TERMINATE", "NEVER")
DEFAULT_MAX_AUTO_REPLY = 5
DEFAULT_TIMEOUT_SEC = 300            # 응답 대기 5분
POLL_INTERVAL_SEC = 0.5
TERMINATE_KEYWORDS = (
    "TERMINATE", "STOP", "ABORT", "CRITICAL",
    "max_iterations", "user_input_required",
)


# ──────────────────────────────────────────────────────────────────
# 디렉토리 헬퍼
# ──────────────────────────────────────────────────────────────────

def get_project_root() -> Path:
    """프로젝트 루트 결정 (HARNESS_PROJECT > cwd)."""
    env = os.environ.get("HARNESS_PROJECT")
    if env:
        p = Path(env).resolve()
        if (p / ".claude").exists():
            return p
    cwd = Path.cwd()
    if (cwd / ".claude").exists():
        return cwd
    # 부모로 올라가며 탐색 (서브에이전트가 cwd 다를 수 있음)
    for parent in cwd.parents[:3]:
        if (parent / ".claude").exists():
            return parent
    # 최종 폴백: cwd 에 .claude 만들기
    (cwd / ".claude").mkdir(exist_ok=True)
    return cwd


def get_runtime_dirs(project_root: Path | None = None) -> dict[str, Path]:
    """HPA 가 쓰는 모든 경로 반환 (자동 생성)."""
    root = project_root or get_project_root()
    runtime = root / ".claude" / "runtime"
    pending = runtime / "hpa_pending"
    responses = runtime / "hpa_responses"
    for d in (pending, responses):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "project_root": root,
        "runtime": runtime,
        "pending": pending,
        "responses": responses,
        "state": runtime / "hpa_state.json",
        "log": runtime / "hpa_log.jsonl",
    }


# ──────────────────────────────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────────────────────────────

@dataclass
class HpaRequest:
    """HPA 호출 요청."""
    id: str
    sender: str                    # 호출한 에이전트 (예: "x-sar")
    message: str                   # 사용자에게 보일 질문
    options: list[str]             # 선택지 (없으면 free-text)
    mode: str                      # ALWAYS / TERMINATE / NEVER
    worktree_id: str
    created_at: str
    context: dict[str, Any]        # 추가 메타 (max_auto_reply 등)
    status: str = "pending"        # pending / answered / timeout / auto

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HpaResponse:
    """사용자(또는 자동 정책) 응답."""
    request_id: str
    choice: str                    # 선택한 옵션 또는 free-text
    decided_by: str                # "user" / "auto_never" / "auto_terminate" / "timeout"
    answered_at: str
    elapsed_sec: float
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────
# 핵심 클래스
# ──────────────────────────────────────────────────────────────────

class HumanProxyAgent:
    """AutoGen UserProxyAgent 호환 + 하네스 통합 영속 모드."""

    def __init__(
        self,
        name: str = "h-user",
        human_input_mode: str = "TERMINATE",
        max_consecutive_auto_reply: int = DEFAULT_MAX_AUTO_REPLY,
        is_termination_msg=None,
        project_root: Path | None = None,
        worktree_id: str | None = None,
    ):
        if human_input_mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {human_input_mode!r}")

        self.name = name
        self.mode = human_input_mode
        self.max_auto = max_consecutive_auto_reply
        self.is_terminate = is_termination_msg or self._default_is_terminate
        self.worktree_id = worktree_id or os.environ.get("HARNESS_WORKTREE_ID", "main")
        self.dirs = get_runtime_dirs(project_root)

    @staticmethod
    def _default_is_terminate(message: str) -> bool:
        upper = message.upper()
        return any(kw in upper for kw in TERMINATE_KEYWORDS)

    # ─── 카운터 (file-locked) ─────────────────────────────────

    def _get_state(self) -> dict:
        return load_json(self.dirs["state"], default={
            "auto_reply_count": {},     # worktree_id → count
            "total_calls": 0,
            "by_mode": {"ALWAYS": 0, "TERMINATE": 0, "NEVER": 0},
        })

    def _bump_auto_count(self) -> int:
        """이 워크트리의 auto_reply 카운터 증가 후 반환."""
        with read_modify_write_json(self.dirs["state"], default=self._get_state()) as state:
            counts = state.setdefault("auto_reply_count", {})
            counts[self.worktree_id] = counts.get(self.worktree_id, 0) + 1
            new_count = counts[self.worktree_id]
        return new_count

    def _reset_auto_count(self):
        with read_modify_write_json(self.dirs["state"], default=self._get_state()) as state:
            state.setdefault("auto_reply_count", {})[self.worktree_id] = 0

    def _increment_total(self, mode: str):
        with read_modify_write_json(self.dirs["state"], default=self._get_state()) as state:
            state["total_calls"] = state.get("total_calls", 0) + 1
            by = state.setdefault("by_mode", {})
            by[mode] = by.get(mode, 0) + 1

    # ─── audit log ────────────────────────────────────────────

    def _log(self, event: str, data: dict):
        entry = {
            "ts": now_iso(),
            "event": event,
            "agent": self.name,
            "worktree": self.worktree_id,
            **data,
        }
        append_line_atomic(self.dirs["log"], json.dumps(entry, ensure_ascii=False))

    # ─── 핵심 API ─────────────────────────────────────────────

    def receive(
        self,
        message: str,
        sender: str = "unknown",
        options: list[str] | None = None,
        context: dict | None = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ) -> HpaResponse:
        """다른 에이전트가 호출하는 진입점.

        AutoGen 의 receive() 와 동등. mode 에 따라 분기:
          NEVER     → 즉시 자동 응답
          TERMINATE → terminate 조건 또는 max_auto 초과 시만 인간
          ALWAYS    → 무조건 인간
        """
        self._increment_total(self.mode)
        options = options or []
        context = context or {}

        # NEVER: 자동 응답
        if self.mode == "NEVER":
            return self._auto_respond(message, sender, options, context,
                                       reason="mode=NEVER")

        # TERMINATE: 조건 검사
        if self.mode == "TERMINATE":
            if not self.is_terminate(message):
                count = self._bump_auto_count()
                if count <= self.max_auto:
                    return self._auto_respond(message, sender, options, context,
                                               reason=f"auto_reply {count}/{self.max_auto}")
                # max 초과 — 강제 인간
                self._reset_auto_count()
                return self._ask_human(message, sender, options, context, timeout,
                                        reason="max_auto_reply exceeded")
            # terminate 조건 만남
            return self._ask_human(message, sender, options, context, timeout,
                                    reason="terminate condition")

        # ALWAYS: 무조건 인간
        return self._ask_human(message, sender, options, context, timeout,
                                reason="mode=ALWAYS")

    # ─── 인간 호출 ────────────────────────────────────────────

    def _ask_human(
        self,
        message: str,
        sender: str,
        options: list[str],
        context: dict,
        timeout: float,
        reason: str,
    ) -> HpaResponse:
        """pending 파일 생성 → 응답 대기 → 결과 반환."""
        req_id = self._new_request_id()
        request = HpaRequest(
            id=req_id, sender=sender, message=message, options=options,
            mode=self.mode, worktree_id=self.worktree_id,
            created_at=now_iso(), context=context, status="pending",
        )
        save_yaml_atomic(self.dirs["pending"] / f"{req_id}.yaml", request.to_dict())
        self._log("ask", {"request_id": req_id, "sender": sender,
                          "message_preview": message[:120], "reason": reason})

        # 1) stdin 직접 호출 (CLI 모드, TTY 가 있을 때)
        # 2) 그렇지 않으면 응답 파일 polling
        if sys.stdin.isatty() and os.environ.get("HPA_INTERACTIVE", "1") == "1":
            return self._stdin_prompt(request, timeout)
        return self._poll_response(req_id, timeout)

    def _stdin_prompt(self, request: HpaRequest, timeout: float) -> HpaResponse:
        """터미널이 있으면 직접 묻고 즉시 응답 처리."""
        sys.stderr.write(f"\n━━━ 👤 Human Proxy — {request.id} ━━━\n")
        sys.stderr.write(f"From: {request.sender}\n")
        sys.stderr.write(f"Message: {request.message}\n")
        if request.options:
            sys.stderr.write("Options:\n")
            for i, opt in enumerate(request.options, 1):
                sys.stderr.write(f"  [{i}] {opt}\n")
        sys.stderr.write("Your choice: ")
        sys.stderr.flush()

        start = time.time()
        try:
            answer = input().strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        # 숫자 입력은 옵션 인덱스로 변환
        if answer.isdigit() and request.options:
            idx = int(answer) - 1
            if 0 <= idx < len(request.options):
                answer = request.options[idx]

        elapsed = time.time() - start
        response = HpaResponse(
            request_id=request.id, choice=answer or "(empty)",
            decided_by="user", answered_at=now_iso(),
            elapsed_sec=round(elapsed, 2), reason="stdin",
        )
        self._finalize(request, response)
        return response

    def _poll_response(self, req_id: str, timeout: float) -> HpaResponse:
        """응답 파일이 나타날 때까지 polling (대시보드/외부 응답 모드)."""
        start = time.time()
        response_path = self.dirs["responses"] / f"{req_id}.yaml"
        pending_path = self.dirs["pending"] / f"{req_id}.yaml"
        while time.time() - start < timeout:
            if response_path.exists():
                data = load_yaml(response_path) or {}
                if data:
                    response = HpaResponse(**{
                        k: data.get(k) for k in HpaResponse.__dataclass_fields__
                    })
                    self._log("answered", {"request_id": req_id,
                                            "decided_by": response.decided_by,
                                            "elapsed_sec": response.elapsed_sec})
                    # 응답 받았으면 pending 정리 (외부에서 cmd_respond 가 했더라도 안전)
                    if pending_path.exists():
                        try:
                            pending_path.unlink()
                        except OSError:
                            pass
                    return response
            time.sleep(POLL_INTERVAL_SEC)

        # 타임아웃
        response = HpaResponse(
            request_id=req_id, choice="(timeout)",
            decided_by="timeout", answered_at=now_iso(),
            elapsed_sec=timeout, reason=f"no response in {timeout}s",
        )
        self._log("timeout", {"request_id": req_id})
        # pending 정리
        pending = self.dirs["pending"] / f"{req_id}.yaml"
        if pending.exists():
            try:
                pending.unlink()
            except OSError:
                pass
        return response

    def _auto_respond(
        self,
        message: str,
        sender: str,
        options: list[str],
        context: dict,
        reason: str,
    ) -> HpaResponse:
        """자동 정책 응답. 옵션 있으면 첫 번째, 없으면 'auto-allowed'."""
        choice = options[0] if options else "auto-allowed"
        response = HpaResponse(
            request_id=self._new_request_id(),
            choice=choice,
            decided_by=f"auto_{self.mode.lower()}",
            answered_at=now_iso(),
            elapsed_sec=0.0,
            reason=reason,
        )
        self._log("auto", {"sender": sender, "choice": choice,
                            "reason": reason,
                            "message_preview": message[:120]})
        return response

    @staticmethod
    def _new_request_id() -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        rand = secrets.token_hex(2)  # 16-bit
        return f"hpa-{ts}-{rand}"

    def _finalize(self, request: HpaRequest, response: HpaResponse):
        """pending → responses 이동 + 로깅."""
        save_yaml_atomic(
            self.dirs["responses"] / f"{request.id}.yaml",
            response.to_dict(),
        )
        pending = self.dirs["pending"] / f"{request.id}.yaml"
        if pending.exists():
            try:
                pending.unlink()
            except OSError:
                pass
        self._log("finalized", {
            "request_id": request.id, "choice": response.choice,
            "decided_by": response.decided_by,
            "elapsed_sec": response.elapsed_sec,
        })


# ──────────────────────────────────────────────────────────────────
# CLI 인터페이스
# ──────────────────────────────────────────────────────────────────

def cmd_ask(args):
    """다른 에이전트가 사용자에게 묻는 진입점."""
    hpa = HumanProxyAgent(
        name=args.name,
        human_input_mode=args.mode,
        max_consecutive_auto_reply=args.max_auto_reply,
    )
    response = hpa.receive(
        message=args.message,
        sender=args.sender,
        options=args.options or [],
        timeout=args.timeout,
    )
    # stdout 에 결과 (다른 스크립트 가 파싱)
    print(json.dumps(response.to_dict(), ensure_ascii=False))


def cmd_respond(args):
    """대시보드/사용자가 pending 요청에 응답."""
    dirs = get_runtime_dirs()
    pending_path = dirs["pending"] / f"{args.request_id}.yaml"
    if not pending_path.exists():
        sys.stderr.write(f"❌ pending 요청 없음: {args.request_id}\n")
        sys.exit(1)
    request = load_yaml(pending_path) or {}
    if not request:
        sys.stderr.write("❌ pending 파일 깨짐\n")
        sys.exit(1)

    # v2.7.2: now_iso() 는 datetime.now() 기반 (로컬 naive). datetime.utcnow() 와 비교 시
    # KST(+9) 환경에서 9시간 차이로 음수 발생. 둘 다 datetime.now() 로 통일 + max(0) 가드.
    created_str = request["created_at"].replace("Z", "").rstrip("+00:00")
    try:
        created_dt = datetime.fromisoformat(created_str)
        elapsed = max(0.0, (datetime.now() - created_dt).total_seconds())
    except (ValueError, TypeError):
        elapsed = 0.0

    response = HpaResponse(
        request_id=args.request_id,
        choice=args.choice,
        decided_by="user",
        answered_at=now_iso(),
        elapsed_sec=round(elapsed, 2),
        reason=args.reason or "external_response",
    )
    save_yaml_atomic(dirs["responses"] / f"{args.request_id}.yaml", response.to_dict())
    pending_path.unlink()
    append_line_atomic(dirs["log"], json.dumps({
        "ts": now_iso(), "event": "external_respond",
        "request_id": args.request_id, "choice": args.choice,
    }, ensure_ascii=False))
    # v2.7.2: Windows CP949 콘솔에서 한국어 stdout 깨짐 방지
    out = json.dumps(response.to_dict(), ensure_ascii=False)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(out + "\n")
    sys.stdout.flush()


def cmd_list_pending(args):
    """대기 중인 요청 목록 (대시보드 용)."""
    dirs = get_runtime_dirs()
    pending = []
    for f in sorted(dirs["pending"].glob("*.yaml")):
        data = load_yaml(f) or {}
        pending.append(data)
    print(json.dumps({"pending": pending, "count": len(pending)},
                     ensure_ascii=False, indent=2))


def cmd_status(args):
    """현재 상태 (카운터, 모드별 호출, 워크트리)."""
    dirs = get_runtime_dirs()
    state = load_json(dirs["state"], default={})
    pending_count = len(list(dirs["pending"].glob("*.yaml")))
    responses_count = len(list(dirs["responses"].glob("*.yaml")))
    print(json.dumps({
        "project_root": str(dirs["project_root"]),
        "state": state,
        "pending": pending_count,
        "completed": responses_count,
    }, ensure_ascii=False, indent=2))


def cmd_clear_pending(args):
    """타임아웃된 pending 정리 (관리자 명령)."""
    dirs = get_runtime_dirs()
    cutoff = time.time() - args.older_than_sec
    removed = 0
    for f in dirs["pending"].glob("*.yaml"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    print(f"✅ {removed} 개 stale pending 제거")


def main():
    p = argparse.ArgumentParser(
        description="Human Proxy Agent — AutoGen 호환 인간 결정 위임"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # ask
    ask = sub.add_parser("ask", help="사용자에게 결정 위임")
    ask.add_argument("--name", default="h-user")
    ask.add_argument("--sender", required=True)
    ask.add_argument("--message", required=True)
    ask.add_argument("--options", nargs="*", help="선택지 (공백 구분)")
    ask.add_argument("--mode", choices=VALID_MODES, default="TERMINATE")
    ask.add_argument("--max-auto-reply", type=int, default=DEFAULT_MAX_AUTO_REPLY)
    ask.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC)
    ask.set_defaults(func=cmd_ask)

    # respond
    resp = sub.add_parser("respond", help="대시보드/사용자가 응답")
    resp.add_argument("request_id")
    resp.add_argument("--choice", required=True)
    resp.add_argument("--reason", default="")
    resp.set_defaults(func=cmd_respond)

    # list-pending
    lp = sub.add_parser("list-pending", help="대기 중인 요청 목록")
    lp.set_defaults(func=cmd_list_pending)

    # status
    st = sub.add_parser("status", help="HPA 상태 요약")
    st.set_defaults(func=cmd_status)

    # clear
    cl = sub.add_parser("clear-pending", help="stale pending 정리")
    cl.add_argument("--older-than-sec", type=int, default=3600)
    cl.set_defaults(func=cmd_clear_pending)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
