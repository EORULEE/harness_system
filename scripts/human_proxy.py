#!/usr/bin/env python3
"""human_proxy.py — Human Proxy Agent (HPA) for the harness.

AutoGen UserProxyAgent 패턴을 하네스에 이식.
다른 에이전트(c-/x-/leader/debater 등)가 인간 결정이 필요한 시점에
이 에이전트에게 메시지를 보내면, mode 정책에 따라 자동 응답하거나
실제 사용자에게 묻는다.

3 모드 (AutoGen 호환) — ⚠️ 안전 override: **고위험(위험목록 매치·미분류)은 모드와 무관하게
항상 사람 강제**(NEVER 에서도). 아래는 저위험 결정에만 적용된다:
    ALWAYS    - 매 호출마다 인간에게 묻는다
    TERMINATE - max_auto_reply 도달 또는 termination 메시지일 때만 묻는다
    NEVER     - (저위험만) 자동 응답. 고위험은 여전히 사람.

저위험 auto-reply(2026-07-09 개선):
    도메인 페르소나(personas.yaml 역할 × _domain-profiles 도메인) 조합 프롬프트를 emit →
    오케스트레이터(Claude)가 전문 답변 + codex 검증 → `persona-answer` CLI 로 확정.
    ⚠️ codex 실제 실행은 **오케스트레이터 책임**(스크립트는 stdlib·LLM/codex 미호출).
    스크립트는 codex-verdict != pass 시 **사람 에스컬레이션을 강제**(가짜 채택 차단, enforcement point).
    도메인 부재 + 명시 risk=low = 기존 options[0] fallback(하위호환).

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

AskUserQuestion 다리 (Claude 대화에서 고위험 승인 UX):
    스크립트는 AskUserQuestion(Claude 도구)을 직접 못 부른다 → 오케스트레이터(Claude)가 절차로 배선:
      ① python scripts/human_proxy.py bridge      # pending 을 AskUserQuestion-ready 로 출력
      ② Claude: 각 pending 을 AskUserQuestion 으로 사용자에게(options 그대로 제시)
      ③ python scripts/human_proxy.py respond <id> --choice <사용자 답>   # 되먹임
    → 고위험(fail-closed)·persona codex 실패 승격 결정이 대화 중 매끄러운 승인 팝업으로 뜬다.

동시성:
    - 모든 상태 파일은 harness_common 의 file_lock + atomic_write 사용
    - req_id 는 timestamp + random 16-bit 로 충돌 방지
    - 여러 워크트리/터미널 병렬 호출 안전
"""

from __future__ import annotations
import argparse
import json
import os
import re
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

try:
    from secret_masking import mask_secrets
except Exception:
    def mask_secrets(t): return t


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

# ── 고위험 패턴 (사람 강제, auto-approve 절대 금지) ──────────────────────
# 정본 = _loop-core/loop-permission-policy.md 의 human-gated 목록(헌법 §5 계열)의 코드-미러.
# 매치 시 어떤 모드(NEVER 포함)에서도 사람 에스컬레이션(fail-closed). 새 정본 아님 — 미러이며
# 정책 변경 시 여기와 정책 문서를 함께 갱신한다(HPA_RISK_MIRROR 태그로 추적).
# 단어경계(\b)로 오매치 방지(예: "constraint" 안의 "train"). 안전측 = 넓게 잡되 정밀.
HIGH_RISK_PATTERNS = [
    r"배포|\bdeploy\b|\brelease\b|\bpromote\b|승격|\bship\b|\bprod\b|production",  # 배포·승격
    r"삭제|\bdelete\b|\brm\b|\bremove\b|\bdrop\b|덮어쓰|\boverwrite\b|\btruncate\b|\bwipe\b|초기화",  # 파괴적
    r"\bpush\b|\bmerge\b|\brebase\b|force[- ]?push|--no-verify|\bsync\b",  # git·동기화 외부반영
    r"업로드|\bupload\b|공개\b|\bpublish\b|외부\s*전송|\bshare\b|전송\b|제출|\bsubmit\b",  # 외부 전송/공개/제출
    r"유료|\bpaid\b|api[\s_-]*key|과금|\bbilling\b|gemini\s*write|codex\s*exec",  # 유료/외부 호출
    r"mode\s*c\b|모드\s*c\b|실험\s*실행|experiment\s*run|학습\s*실행|\btrain\b",  # Mode C/학습
    r"design\s*sync|\bpublished\b|claude\s*design.*(sync|publish)",  # Design sync
    r"approve\s+(deploy|release|delete|push|merge)",             # 명시적 파괴 승인
]
_HIGH_RISK_RE = re.compile("|".join(HIGH_RISK_PATTERNS), re.I)

# 페르소나 조합 소스(재사용 — 새 페르소나 체계 0). personas.yaml × _domain-profiles/<domain>.
PERSONA_ROLES_REL = ".claude/skills/_paper-review-core/personas.yaml"
DOMAIN_PROFILES_REL = ".claude/skills/_domain-profiles"


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

    # ─── 위험 분류 (fail-closed) ──────────────────────────────
    @staticmethod
    def _classify_risk(message: str, options: list[str], context: dict) -> str:
        """'high'(사람 강제) / 'low'(페르소나 auto 적격). **fail-closed**: 고위험 패턴 매치 OR
        저위험 신호 부재 = high. 저위험 적격 = 명시 risk=low 또는 domain 제공(도메인 결정)에 한함.
        고위험은 어떤 모드에서도 auto-approve 안 됨. 위험목록 정본=loop-permission-policy 미러."""
        if context.get("force_human") or str(context.get("risk", "")).lower() == "high":
            return "high"
        blob = " ".join([message or "", " ".join(options or []),
                         str(context.get("action", "")), str(context.get("target", ""))])
        if _HIGH_RISK_RE.search(blob):
            return "high"
        # 고위험 패턴은 아님. 그러나 auto 적격은 '명시적 저위험 신호' 필요(fail-closed):
        #   risk=low(호출측 단언) 또는 domain 제공(도메인 결정). 신호 없으면 = 미분류 = high.
        if str(context.get("risk", "")).lower() == "low" or context.get("domain"):
            return "low"
        return "high"

    # ─── 페르소나 조합 (personas.yaml × _domain-profiles 재사용) ──
    def _resolve_persona(self, context: dict) -> dict | None:
        """context.domain 으로 도메인 프로파일 로드(+역할). 없으면 None(→ options[0] fallback).
        프로젝트 로컬 우선, 없으면 글로벌. 무코드 확장(도메인 프로파일만 있으면 동작)."""
        domain = context.get("domain")
        if not domain or not re.fullmatch(r"[A-Za-z0-9._-]+", str(domain)):
            return None
        root = self.dirs["project_root"]
        cands = [root / DOMAIN_PROFILES_REL / domain / "domain.yaml",
                 Path.home() / ".claude/skills/_domain-profiles" / domain / "domain.yaml"]
        prof = next((load_yaml(c) for c in cands if c.is_file()), None)
        if not prof:
            return None
        role = context.get("role", "decision-proxy")
        return {
            "domain": domain,
            "persona_seed": prof.get("persona_seed", ""),
            "terminology": prof.get("terminology", []),
            "role": role,
            "role_stance": self._load_role_stance(role),   # personas.yaml 역할(있으면)
        }

    def _load_role_stance(self, role: str) -> dict | None:
        """personas.yaml 에서 역할 stance 로드(있으면). '역할×도메인' 조합의 역할 절반.
        role 이 personas.yaml 에 없으면 None(기본 decision-proxy stance 사용)."""
        for base in (self.dirs["project_root"] / PERSONA_ROLES_REL,
                     Path.home() / ".claude/skills/_paper-review-core/personas.yaml"):
            if base.is_file():
                data = load_yaml(base) or {}
                p = (data.get("personas") or {}).get(role)
                if isinstance(p, dict):
                    return {"stance": p.get("stance", ""), "goal": p.get("goal", ""),
                            "non_goals": p.get("non_goals", "")}
        return None

    def _build_persona_prompt(self, message: str, options: list[str], persona: dict) -> str:
        """오케스트레이터(Claude)가 전문 답변할 결정 프롬프트 조립(stdlib 문자열).
        collusion-strip: 도메인=배경사실·정확도용, 정체성/관대 금지."""
        opt = "\n".join(f"  - {o}" for o in options) if options else "  (free-text)"
        terms = ", ".join(str(t) for t in (persona.get("terminology") or [])[:12])
        rs = persona.get("role_stance") or {}
        role_line = (f"[역할] {persona.get('role')} — {rs.get('stance','')}"
                     if rs else f"[역할] {persona.get('role')} — 사용자 대리 저위험 결정(근거 명시).")
        return (
            "# HPA 저위험 결정 — 사용자 대리 전문 판단 요청\n"
            "# collusion-strip: 아래 도메인은 배경 사실이며 정확한 판단에만 쓴다"
            "(관대·정체성 금지). 확신 없으면 'ESCALATE_HUMAN' 반환.\n"
            f"{role_line}\n"
            f"[도메인 배경] {persona.get('domain')}: {str(persona.get('persona_seed',''))[:600]}\n"
            f"[핵심 용어] {terms}\n"
            f"[결정] {message}\n[선택지]\n{opt}\n"
            "→ 최선의 선택지(또는 free-text) + 1줄 근거. 불확실/고위험 냄새면 ESCALATE_HUMAN."
        )

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

        # ★ 안전 불변식(AC2): 고위험은 어떤 모드(NEVER 포함)에서도 사람 강제.
        #   auto 경로(_auto_respond/_persona_pending)는 고위험에 코드-도달 불가(fail-closed).
        if self._classify_risk(message, options, context) == "high":
            self._log("high_risk_escalate", {"sender": sender,
                      "message_preview": mask_secrets(message)[:120], "mode": self.mode})
            return self._ask_human(message, sender, options, context, timeout,
                                    reason=f"high-risk fail-closed (mode={self.mode})")

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
                          "message_preview": mask_secrets(message)[:120], "reason": reason})

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
        """저위험 자동 응답. 도메인 페르소나 있으면 전문 답변 경로(오케스트레이터+codex),
        없으면 하위호환 fallback(options[0])."""
        persona = self._resolve_persona(context)
        if persona is not None:
            return self._persona_pending(message, sender, options, context, persona, reason)
        # 하위호환(AC7): 페르소나/도메인 부재 → 기존 기계적 기본값(저위험 한정)
        choice = options[0] if options else "auto-allowed"
        response = HpaResponse(
            request_id=self._new_request_id(),
            choice=choice,
            decided_by=f"auto_{self.mode.lower()}_fallback",
            answered_at=now_iso(),
            elapsed_sec=0.0,
            reason=f"{reason}; no-persona fallback",
        )
        self._log("auto_fallback", {"sender": sender, "choice": choice,
                            "reason": reason, "message_preview": mask_secrets(message)[:120]})
        return response

    def _persona_pending(self, message, sender, options, context, persona, reason):
        """저위험+도메인: 결정 프롬프트 패키지 emit. 오케스트레이터(Claude)가 조합 페르소나로
        전문 답변 → codex 검증 → `persona-answer` CLI 로 확정. 스크립트는 LLM 미호출(stdlib)."""
        req_id = self._new_request_id()
        prompt = self._build_persona_prompt(message, options, persona)
        pp_dir = self.dirs["runtime"] / "hpa_persona_pending"
        pp_dir.mkdir(parents=True, exist_ok=True)
        # runtime 파일에 결정 컨텍스트 영속 → 저장 전 secret 마스킹(codex #9).
        save_yaml_atomic(pp_dir / f"{req_id}.yaml", {
            "id": req_id, "sender": sender,
            "message": mask_secrets(message), "options": [mask_secrets(str(o)) for o in options],
            "mode": self.mode, "domain": persona["domain"], "role": persona["role"],
            "persona_prompt": mask_secrets(prompt), "created_at": now_iso(),
            "requires": "orchestrator persona answer + codex verify → 'persona-answer' CLI",
        })
        self._log("persona_pending", {"request_id": req_id, "sender": sender,
                  "domain": persona["domain"], "reason": reason})
        return HpaResponse(
            request_id=req_id, choice="(persona_pending)",
            decided_by="auto_persona_pending", answered_at=now_iso(),
            elapsed_sec=0.0,
            reason=f"low-risk persona({persona['domain']}); {reason}",
        )

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
    ctx = {}
    if getattr(args, "domain", ""):
        ctx["domain"] = args.domain
    if getattr(args, "risk", ""):
        ctx["risk"] = args.risk
    if getattr(args, "role", ""):
        ctx["role"] = args.role
    response = hpa.receive(
        message=args.message,
        sender=args.sender,
        options=args.options or [],
        context=ctx,
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


def cmd_persona_answer(args):
    """오케스트레이터(Claude)가 저위험 persona_pending 에 codex-검증된 전문 답변 확정.
    codex-verdict != pass 또는 ESCALATE_HUMAN → 사람 에스컬레이션(가짜 채택 금지, AC5)."""
    dirs = get_runtime_dirs()
    pp_path = dirs["runtime"] / "hpa_persona_pending" / f"{args.request_id}.yaml"
    if not pp_path.exists():
        sys.stderr.write(f"❌ persona_pending 없음: {args.request_id}\n"); sys.exit(1)
    pkg = load_yaml(pp_path) or {}
    verdict = (args.codex_verdict or "").lower()
    escalate = (verdict != "pass") or (args.choice.strip().upper() == "ESCALATE_HUMAN")
    if escalate:
        # 사람 에스컬레이션: 일반 pending 생성 → 사람이 respond
        save_yaml_atomic(dirs["pending"] / f"{args.request_id}.yaml", {
            "id": args.request_id, "sender": pkg.get("sender", "persona"),
            "message": pkg.get("message", ""), "options": pkg.get("options", []),
            "mode": pkg.get("mode", "TERMINATE"), "worktree_id": "main",
            "created_at": now_iso(), "status": "pending",
            "context": {"escalated_from": "persona", "codex_verdict": verdict,
                        "persona_choice": args.choice},
        })
        pp_path.unlink()
        append_line_atomic(dirs["log"], json.dumps({
            "ts": now_iso(), "event": "persona_escalate", "request_id": args.request_id,
            "codex_verdict": verdict, "reason": "codex not pass or ESCALATE_HUMAN"},
            ensure_ascii=False))
        print(json.dumps({"status": "escalated_human", "request_id": args.request_id,
                          "codex_verdict": verdict}, ensure_ascii=False))
        return
    # codex pass → 최종 확정(provenance 기록)
    response = HpaResponse(
        request_id=args.request_id, choice=args.choice, decided_by="auto_persona",
        answered_at=now_iso(), elapsed_sec=0.0,
        reason=f"persona({pkg.get('domain')}) + codex={verdict}")
    save_yaml_atomic(dirs["responses"] / f"{args.request_id}.yaml", response.to_dict())
    pp_path.unlink()
    append_line_atomic(dirs["log"], json.dumps({
        "ts": now_iso(), "event": "persona_answer", "request_id": args.request_id,
        "domain": pkg.get("domain"), "choice": args.choice, "codex_verdict": verdict},
        ensure_ascii=False))
    print(json.dumps(response.to_dict(), ensure_ascii=False))


def cmd_bridge(args):
    """AskUserQuestion 다리 — pending 결정을 오케스트레이터(Claude)가 AskUserQuestion 으로
    띄우기 좋은 최소형(id·message·options·sender)으로 출력. 흐름:
      ① `human_proxy.py bridge` → pending 배열
      ② Claude: 각 항목을 AskUserQuestion 으로 사용자에게 (options 그대로)
      ③ Claude: 사용자 답 → `human_proxy.py respond <id> --choice <답>` 되먹임
    스크립트는 AskUserQuestion 을 직접 못 부른다(Claude 도구) — 절차 배선이 다리다."""
    dirs = get_runtime_dirs()
    items = []
    for f in sorted(dirs["pending"].glob("*.yaml")):
        d = load_yaml(f) or {}
        if not d:
            continue
        ctx = d.get("context", {}) or {}
        items.append({
            "id": d.get("id"),
            "sender": d.get("sender"),
            "message": d.get("message"),
            "options": d.get("options") or [],
            "escalated_from": ctx.get("escalated_from", ""),   # 'persona'=codex 실패 승격
            "hint": "AskUserQuestion 으로 사용자에게 → respond <id> --choice <답>",
        })
    print(json.dumps({"pending_for_askuser": items, "count": len(items)},
                     ensure_ascii=False, indent=2))


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
    ask.add_argument("--domain", default="", help="저위험 페르소나 도메인(_domain-profiles/<name>)")
    ask.add_argument("--risk", choices=["low", "high", ""], default="", help="위험 힌트(high=사람 강제)")
    ask.add_argument("--role", default="decision-proxy")
    ask.set_defaults(func=cmd_ask)

    # respond
    resp = sub.add_parser("respond", help="대시보드/사용자가 응답")
    resp.add_argument("request_id")
    resp.add_argument("--choice", required=True)
    resp.add_argument("--reason", default="")
    resp.set_defaults(func=cmd_respond)

    # persona-answer (오케스트레이터가 codex-검증 페르소나 답변 확정)
    pa = sub.add_parser("persona-answer", help="저위험 페르소나 답변 확정(codex 검증 후)")
    pa.add_argument("request_id")
    pa.add_argument("--choice", required=True)
    pa.add_argument("--codex-verdict", required=True,
                    choices=["pass", "fail", "unavailable"])
    pa.set_defaults(func=cmd_persona_answer)

    # bridge (AskUserQuestion 다리 — 오케스트레이터가 pending 을 승인 팝업으로)
    br = sub.add_parser("bridge", help="pending 을 AskUserQuestion-ready 최소형으로 출력")
    br.set_defaults(func=cmd_bridge)

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
