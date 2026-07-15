#!/usr/bin/env python3
"""vgate_common.py — verification-gate v1.1 공용 인프라 (설계=implementation_design_v1.1.md).

원칙(교차검토 확정):
- report-only 우선. 어떤 함수도 예외로 턴을 깨지 않는다(fail-open + 진단 카운터).
- 동시성: 모든 append 는 fcntl.flock (Stop/PostToolUse 훅 병렬 실행이 문서 사실).
- receipt/finding 에 gate 버전 fingerprint 포함(평가 freeze 식별).
- 내용 본문 최소화: bounded raw 는 measure receipt 의 구조화 필드에만(원장 privacy 규약 유지).
"""
from __future__ import annotations
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

try:  # Windows(notebook) 이식: fcntl 은 Unix 전용 — 부재 시 no-op 잠금(단일세션 전제, codex F8)
    import fcntl
    def _lock(f): fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    def _unlock(f): fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except ImportError:
    def _lock(f): pass
    def _unlock(f): pass

THIS = Path(__file__).resolve()
try:
    sys.path.insert(0, str(THIS.parent))
    from harness_common import CLAUDE_DIR  # type: ignore
except Exception:
    CLAUDE_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude"

RUNTIME = Path(CLAUDE_DIR) / "runtime"
VGATE_DIR = RUNTIME / "vgate"
RECEIPTS = VGATE_DIR / "receipts.jsonl"        # measure.py 관측 receipt
DECISIONS = VGATE_DIR / "decisions.jsonl"      # decision_receipt.py 선언
METHODS = VGATE_DIR / "methods.jsonl"          # BLOCKED_UNDER_TESTED_METHODS 선등록 method set
FINDINGS = VGATE_DIR / "findings.jsonl"        # orchestrator report-only findings
STOP_STATE = VGATE_DIR / "stop_state.json"     # retry fingerprint/attempts
BASELINE_DIR = VGATE_DIR / "baseline"          # P−1 detector-독립 표본
AUDIT_QUEUE = VGATE_DIR / "audit-queue"        # 감사 대상 패키지
AUDIT_LABELS = VGATE_DIR / "audit-labels.jsonl"
ERRLOG = VGATE_DIR / "vgate-errors.log"

MAX_LINES = 5000          # rotation cap (tool_use_audit 와 동일 정책)
RAW_BOUND = 2000          # bounded raw output 문자 수

# gate 버전 fingerprint 대상(이 목록의 파일 내용 변경 = 새 gate 버전).
_FP_FILES = ("vgate_common.py", "measure.py", "decision_receipt.py",
             "vgate_orchestrator.py", "vgate_audit.py")
GATE_FILES_FOR_SELFMOD = _FP_FILES + ("stop-vgate-orchestrator.mjs", "pre-tool-vgate-tripwire.mjs")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bounded(s: str, n: int = RAW_BOUND) -> str:
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[:n] + f"...[+{len(s)-n}ch]"


def gate_fingerprint() -> str:
    """vgate 소스 파일들의 결합 sha256 앞 12자 — 평가 freeze 식별자."""
    h = hashlib.sha256()
    for name in _FP_FILES:
        p = THIS.parent / name
        try:
            h.update(name.encode() + b"\x00" + p.read_bytes() + b"\x00")
        except Exception:
            h.update(name.encode() + b"\x00MISSING\x00")
    return h.hexdigest()[:12]


def make_id(prefix: str, payload: dict) -> str:
    j = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f"{prefix}:{hashlib.sha256(j.encode()).hexdigest()[:12]}"


def _diag(msg: str) -> None:
    try:
        VGATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRLOG, "a", encoding="utf-8") as f:
            f.write(f"{now()} {msg}\n")
    except Exception:
        pass


def flock_append(path: Path, rec: dict) -> bool:
    """flock 직렬화 append. 실패해도 예외 전파 안 함(fail-open) — bool 반환."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            _lock(f)
            try:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            finally:
                _unlock(f)
        _rotate(path)
        return True
    except Exception as e:
        _diag(f"flock_append {path.name} {type(e).__name__}")
        return False


def _rotate(path: Path) -> None:
    try:
        with open(path, "r+", encoding="utf-8") as f:
            _lock(f)
            try:
                lines = f.read().splitlines()
                if len(lines) > MAX_LINES:
                    f.seek(0); f.truncate()
                    f.write("\n".join(lines[-MAX_LINES:]) + "\n")
            finally:
                _unlock(f)
    except Exception:
        pass


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def read_stdin_json() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}
