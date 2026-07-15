#!/usr/bin/env python3
"""tool_use_audit.py — 경량 도구사용 증거 원장 (Evidence Ledger).

목적: 부재·위치·상태 단정을 기계 검증할 수 있도록, **읽기/검색 도구 사용 사실**을
      `.claude/runtime/tool-use.jsonl` 에 한 줄씩 기록한다. **내용 본문은 저장하지 않는다**
      (path/pattern/query/cwd/turn 등 메타만 — privacy + 경량).

설계:
- 기존 capture_worker.py(Bash/Write/Edit 내용 캡처)와 별개·병렬. capture_worker 를 수정하지 않음.
- PostToolUse 훅이 stdin 으로 넘기는 이벤트 JSON 에서 메타만 뽑아 append.
- Read/Grep/Glob/Bash/LS + Serena·MCP read/search 계열을 기록(이게 detector 의 증거원).
- absence_claim_guard.py 가 `query --turn <id>` 로 이 원장을 조회해 단정의 전제를 검증.

사용:
  echo '<PostToolUse event json>' | python3 tool_use_audit.py record
  python3 tool_use_audit.py query --turn <turn_id> [--cwd <dir>]   # 해당 턴 증거 JSON
  python3 tool_use_audit.py query --since-current                  # _current_turn.txt 기준
"""
from __future__ import annotations
import json, os, re, sys, argparse
from datetime import datetime, timezone
from pathlib import Path

MAX_LEDGER_LINES = 5000   # rotation cap (Codex MAJOR V6 — unbounded growth 방지)

THIS = Path(__file__).resolve()
# CLAUDE_DIR = 프로젝트 .claude (harness_common 우선, 폴백 cwd/.claude)
try:
    sys.path.insert(0, str(THIS.parent))
    from harness_common import CLAUDE_DIR  # type: ignore
except Exception:
    CLAUDE_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude"

RUNTIME = Path(CLAUDE_DIR) / "runtime"
LEDGER = RUNTIME / "tool-use.jsonl"
CURRENT_TURN = RUNTIME / "_current_turn.txt"

# 읽기/검색/실행 계열 — 기록 대상(증거가 되는 도구).
READ_SEARCH_TOOLS = {"Read", "Grep", "Glob", "LS", "ls", "Bash", "NotebookRead"}
# Serena/MCP read·search 계열은 이름이 가변 → prefix·substring 으로 판정.
MCP_READ_HINTS = ("find_symbol", "search", "read_file", "get_symbols", "find_referenc",
                  "find_decl", "find_impl", "list_dir", "get_diagnostics", "read_memory",
                  "snippet_search", "get_file_contents")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify(tool: str) -> str | None:
    """기록 종류 반환(아니면 None=기록 안 함)."""
    if tool in {"Read", "NotebookRead"}:
        return "read"
    if tool in {"Grep"}:
        return "search"
    if tool in {"Glob"}:
        return "glob"
    if tool in {"LS", "ls"}:
        return "list"
    if tool == "Bash":
        return "exec"
    low = tool.lower()
    if low.startswith("mcp__") or "serena" in low:
        if any(h in low for h in MCP_READ_HINTS):
            return "mcp-read"
        return "mcp-other"
    if any(h in low for h in MCP_READ_HINTS):
        return "mcp-read"
    return None


def extract_target(tool: str, ti: dict, kind: str) -> dict:
    """도구 입력에서 검증에 쓸 메타만 추출(내용 본문 제외)."""
    d: dict = {}
    if kind == "read":
        d["path"] = str(ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or "")
    elif kind == "search":
        d["pattern"] = str(ti.get("pattern") or "")[:200]
        if ti.get("path"):
            d["path"] = str(ti.get("path"))
        if ti.get("glob"):
            d["glob"] = str(ti.get("glob"))
    elif kind == "glob":
        d["glob"] = str(ti.get("pattern") or ti.get("glob") or "")
        if ti.get("path"):
            d["path"] = str(ti.get("path"))
    elif kind == "list":
        d["path"] = str(ti.get("path") or "")
    elif kind == "exec":
        # ⚠️ raw command 저장 금지(secret 유출 위험 — Codex BLOCK V4). verb + path 토큰만(본문 미저장).
        #   secret(Bearer/AKIA/sk-…/KEY=…)은 path 형태가 아니라 이 추출에 안 걸림.
        cmd = str(ti.get("command") or "")
        first = cmd.strip().split(maxsplit=1)[0] if cmd.strip() else ""
        d["verb"] = first[:30]
        d["paths"] = [t[:80] for t in re.findall(r"[\w.~/-]*/[\w.~/-]+|\b[\w-]+\.\w{1,5}\b", cmd)][:6]
    elif kind in ("mcp-read", "mcp-other"):
        for k in ("name_path", "query", "pattern", "relative_path", "substring_pattern", "path"):
            if ti.get(k):
                d[k] = str(ti.get(k))[:200]
    return d


def cmd_record() -> int:
    try:
        raw = sys.stdin.read()
        ev = json.loads(raw or "{}")
    except Exception:
        return 0  # fail-open: 절대 턴 차단 안 함
    tool = ev.get("tool_name") or ev.get("tool") or ""
    if not tool:
        return 0
    kind = classify(tool)
    if kind is None or kind == "mcp-other":
        return 0  # write/edit/mcp-write 등은 기록 안 함(증거 아님)
    ti = ev.get("tool_input") or {}
    cwd = ev.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    turn = ""
    try:
        if CURRENT_TURN.exists():
            turn = CURRENT_TURN.read_text(encoding="utf-8").strip()[:80]
    except Exception:
        pass
    rec = {"ts": _now(), "turn": turn, "tool": tool, "kind": kind,
           "cwd": str(cwd), "target": extract_target(tool, ti, kind)}
    # v1.1 provenance(additive — 설계 implementation_design_v1.1.md §3-1): controller 가 준
    # session/prompt/tool_use id 를 있으면 결속(자체 turn 은 폴백으로 유지). 내용 본문은 계속 미저장.
    for src, dst in (("session_id", "session_id"), ("prompt_id", "prompt_id"),
                     ("tool_use_id", "tool_use_id"), ("duration_ms", "duration_ms")):
        v = ev.get(src)
        if v is not None:
            rec[dst] = v if isinstance(v, (int, float)) else str(v)[:80]
    tr = ev.get("tool_response")
    if isinstance(tr, dict) and ("is_error" in tr or "error" in tr):
        rec["success"] = not (tr.get("is_error") or tr.get("error"))
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # v1.1: 병렬 PostToolUse 대비 writer lock
            except Exception:
                pass
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _rotate()
    except Exception as e:
        # fail-open(턴 차단 금지)이되 침묵 금지(Codex MINOR V5): 진단 카운터만 남김.
        try:
            (RUNTIME / "tool-use.audit-errors").open("a", encoding="utf-8").write(f"{_now()} {type(e).__name__}\n")
        except Exception:
            pass
        return 0
    return 0


def _rotate() -> None:
    """ledger 가 MAX_LEDGER_LINES 초과면 최근분만 유지(Codex MAJOR V6 — unbounded growth 방지).
    v1.1: read-truncate-write 를 flock 아래에서 수행(병렬 append 유실 방지 — codex 리뷰 M11)."""
    try:
        with open(LEDGER, "r+", encoding="utf-8") as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            lines = f.read().splitlines()
            if len(lines) > MAX_LEDGER_LINES:
                f.seek(0); f.truncate()
                f.write("\n".join(lines[-MAX_LEDGER_LINES:]) + "\n")
    except Exception:
        pass


def load_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def cmd_query(args) -> int:
    turn = args.turn
    if args.since_current and not turn:
        try:
            turn = CURRENT_TURN.read_text(encoding="utf-8").strip()
        except Exception:
            turn = ""
    recs = load_ledger()
    window_turns = []
    if getattr(args, "recent", 0):
        # D. cross-turn — 최근 N개 distinct turn 의 이벤트 + window turn-id 목록(detector --turns 용).
        seen = []
        for r in recs:
            tn = r.get("turn", "")
            if tn and tn not in seen:
                seen.append(tn)
        window_turns = seen[-args.recent:]
        recs = [r for r in recs if r.get("turn") in set(window_turns)]
    elif turn:
        recs = [r for r in recs if r.get("turn") == turn]
        window_turns = [turn] if turn else []
    print(json.dumps({"turn": turn, "window_turns": window_turns,
                      "count": len(recs), "events": recs}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("record")
    q = sub.add_parser("query")
    q.add_argument("--turn", default="")
    q.add_argument("--cwd", default="")
    q.add_argument("--since-current", action="store_true")
    q.add_argument("--recent", type=int, default=0, help="최근 N개 turn 의 이벤트 반환(cross-turn window)")
    args = ap.parse_args()
    if args.cmd == "record":
        return cmd_record()
    if args.cmd == "query":
        return cmd_query(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
