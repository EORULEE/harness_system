#!/usr/bin/env python3
"""
capture_worker.py — PostToolUse 이벤트 자동 캡처 (Step 3)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Claude Code의 PostToolUse 훅이 발화하면:
  1. hooks/post-tool-use.sh 가 stdin JSON을 capture_queue에 쓰기만 함 (빠름)
  2. 이 워커가 큐를 처리하며 중요도 판별
  3. "중요한" 이벤트만 active trace에 자동 append

사용자가 Step 1/2에서 수동으로 trace를 관리하던 부담을 제거.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
중요도 판별 정책 ("조용함" 수준 — Q3 결정)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
자동 기록:
  - Bash 명령 실행 실패 (exit code != 0, stderr 포함)
  - Bash 명령 실행 성공 (test / build / 중요 명령)
  - Write/Edit: 중요 파일 (*.md, RESEARCH.md, PLAN.md, CLAUDE.md)
  - Bash stdout/stderr에 에러 키워드 포함

스킵:
  - Read, Grep, Glob (읽기 전용)
  - 일반 코드 편집 (.py 편집만으로는 기록 안 함)
  - 성공한 짧은 명령 (ls, pwd, cd 등)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
명령
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  enqueue            stdin JSON을 큐에 적재 (훅에서 직접 호출)
  process            큐의 모든 이벤트 처리 (워커)
  process-watch      큐를 N초마다 폴링 처리 (daemon-like)
  stats              처리 이력 통계
  flush              큐 비우기 (테스트용)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, atomic_write, read_modify_write,
        save_yaml_atomic, load_yaml, HAS_YAML, now_iso,
    )
except ImportError as e:
    sys.stderr.write(f"❌ 의존성: {e}\n")
    sys.exit(1)

# 시크릿 마스킹 — session_logger 와 동일 로직 공유. PostToolUse 이벤트(명령·출력)에
# 섞인 자격증명이 큐·_capture_archive·trace 에 평문으로 남지 않도록 enqueue 시 마스킹.
try:
    from secret_masking import mask_secrets
except Exception:  # pragma: no cover
    def mask_secrets(text):
        return text


# ────────────────────────────── 경로 ──────────────────────────────

RUNTIME_DIR = Path(".claude/runtime")
CAPTURE_QUEUE = RUNTIME_DIR / "capture_queue"
CAPTURE_LOG = RUNTIME_DIR / "capture_log.yaml"
CAPTURE_ARCHIVE = RUNTIME_DIR / "_capture_archive"


# ────────────────────────────── 중요도 판별 규칙 ──────────────────────────────


ERROR_KEYWORDS = [
    "error:", "error ", "ERROR:", "ERROR ", "Error:",
    "exception", "Exception", "EXCEPTION",
    "traceback", "Traceback", "TRACEBACK",
    "segfault", "segmentation fault",
    "failed", "failure", "FAILED", "FAILURE",
    "fatal", "Fatal", "FATAL",
    "cannot", "Cannot", "could not",
    "permission denied", "command not found",
    "assertion", "Assertion",
]

IMPORTANT_FILENAMES = {
    "RESEARCH.md", "PLAN.md", "CLAUDE.md", "README.md",
    "VERIFY.md", "DECISIONS.md",
}

IMPORTANT_EXTENSIONS = {".md"}

TEST_COMMAND_PATTERNS = [
    r"\bpytest\b", r"\bnpm\s+test\b", r"\bcargo\s+test\b",
    r"\bgo\s+test\b", r"\bunittest\b", r"\bmake\s+test\b",
]

BUILD_COMMAND_PATTERNS = [
    r"\bmake\b", r"\bnpm\s+run\s+build\b",
    r"\bcargo\s+build\b", r"\bgo\s+build\b",
    r"\bpython\s+setup\.py\b",
]

# 노이즈 기준 (스킵)
NOISE_BASH_PATTERNS = [
    r"^\s*ls\b", r"^\s*pwd\b", r"^\s*cd\b",
    r"^\s*echo\b", r"^\s*cat\b", r"^\s*which\b",
]


def classify_event(event: dict) -> dict:
    """PostToolUse 이벤트를 분류.

    Returns {
        "should_capture": bool,
        "kind": str,         # error / resolved / tried / result / note / skip
        "title": str,        # 한 줄 제목
        "content": str,      # trace에 append할 내용
        "reason": str,       # 판단 이유 (디버깅)
    }
    """
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    tool_response = event.get("tool_response", {}) or {}

    # ── Read/Grep/Glob: 항상 스킵 ──
    if tool in {"Read", "Grep", "Glob", "ls", "LS"}:
        return {"should_capture": False, "reason": "read-only tool"}

    # ── Bash ──
    if tool == "Bash":
        command = tool_input.get("command", "")
        stdout = tool_response.get("stdout", "") if isinstance(tool_response, dict) else ""
        stderr = tool_response.get("stderr", "") if isinstance(tool_response, dict) else ""
        exit_code = tool_response.get("exit_code", 0) if isinstance(tool_response, dict) else 0

        # 노이즈 명령은 스킵 (성공한 경우)
        if exit_code == 0:
            for pat in NOISE_BASH_PATTERNS:
                if re.search(pat, command):
                    return {"should_capture": False, "reason": "noise command"}

        # 실패 → 항상 기록
        if exit_code != 0:
            snippet = (stderr or stdout)[:500]
            return {
                "should_capture": True,
                "kind": "error",
                "title": f"bash 실패: {command[:60]}",
                "content": (
                    f"**명령**: `{command[:200]}`\n\n"
                    f"**exit code**: {exit_code}\n\n"
                    f"**stderr/stdout**:\n```\n{snippet}\n```"
                ),
                "reason": f"non-zero exit: {exit_code}",
            }

        # stderr/stdout에 에러 키워드 있으면 기록 (exit 0이어도)
        combined = stdout + "\n" + stderr
        for kw in ERROR_KEYWORDS:
            if kw in combined:
                return {
                    "should_capture": True,
                    "kind": "error",
                    "title": f"경고: {command[:60]}",
                    "content": (
                        f"**명령**: `{command[:200]}`\n\n"
                        f"**출력 (에러 키워드 감지)**:\n```\n{combined[:500]}\n```"
                    ),
                    "reason": f"error keyword '{kw}' in output",
                }

        # 테스트 명령 → 결과 기록
        for pat in TEST_COMMAND_PATTERNS:
            if re.search(pat, command):
                return {
                    "should_capture": True,
                    "kind": "result",
                    "title": f"테스트 실행: {command[:60]}",
                    "content": (
                        f"**명령**: `{command[:200]}`\n\n"
                        f"**결과** (exit {exit_code}):\n```\n{stdout[:500]}\n```"
                    ),
                    "reason": "test command",
                }

        # 빌드 명령 → 결과 기록
        for pat in BUILD_COMMAND_PATTERNS:
            if re.search(pat, command):
                return {
                    "should_capture": True,
                    "kind": "result",
                    "title": f"빌드: {command[:60]}",
                    "content": (
                        f"**명령**: `{command[:200]}`\n\n"
                        f"**결과** (exit {exit_code})"
                    ),
                    "reason": "build command",
                }

        # 그 외 일반 bash 성공은 스킵
        return {"should_capture": False, "reason": "plain bash success"}

    # ── Write / Edit / MultiEdit ──
    if tool in {"Write", "Edit", "MultiEdit"}:
        file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
        if not file_path:
            return {"should_capture": False, "reason": "no file path"}
        basename = Path(file_path).name
        ext = Path(file_path).suffix

        # 중요 파일 이름
        if basename in IMPORTANT_FILENAMES:
            return {
                "should_capture": True,
                "kind": "note",
                "title": f"{basename} 수정",
                "content": (
                    f"**파일**: `{file_path}`\n\n"
                    f"**도구**: {tool}\n"
                ),
                "reason": f"important filename: {basename}",
            }

        # 확장자 (.md) 수정
        if ext in IMPORTANT_EXTENSIONS:
            return {
                "should_capture": True,
                "kind": "note",
                "title": f"문서 수정: {basename}",
                "content": (
                    f"**파일**: `{file_path}`\n\n"
                    f"**도구**: {tool}\n"
                ),
                "reason": f"important extension: {ext}",
            }

        # 일반 코드 편집은 스킵
        return {"should_capture": False, "reason": "plain code edit"}

    # 기타 tool: 스킵
    return {"should_capture": False, "reason": f"unhandled tool: {tool}"}


# ────────────────────────────── 큐 조작 ──────────────────────────────


def ensure_runtime():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_QUEUE.mkdir(exist_ok=True)
    CAPTURE_ARCHIVE.mkdir(exist_ok=True)


def enqueue_event(event: dict):
    """이벤트 JSON을 큐에 파일로 저장.

    파일명: {timestamp}-{counter}.json  (순서 보장)
    """
    ensure_runtime()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 중복 방지 suffix
    path = CAPTURE_QUEUE / f"{ts}.json"
    tries = 0
    while path.exists() and tries < 100:
        tries += 1
        path = CAPTURE_QUEUE / f"{ts}-{tries}.json"
    # 시크릿 마스킹 후 저장 — 큐 파일은 그대로 _capture_archive 로 rename 되고
    # classify_event 도 이 마스킹된 내용을 읽으므로 trace append 까지 일괄 redaction.
    atomic_write(path, mask_secrets(json.dumps(event, ensure_ascii=False)))


def process_queue(limit: int | None = None) -> dict:
    """큐의 모든 (또는 limit 만큼) 이벤트 처리.

    Returns {"processed": n, "captured": m, "archived": n}
    """
    ensure_runtime()
    if not CAPTURE_QUEUE.exists():
        return {"processed": 0, "captured": 0, "archived": 0}

    pending = sorted(CAPTURE_QUEUE.glob("*.json"))
    if limit:
        pending = pending[:limit]

    processed = 0
    captured = 0
    for qfile in pending:
        try:
            event = json.loads(qfile.read_text(encoding="utf-8"))
        except Exception as e:
            sys.stderr.write(f"⚠️  큐 파일 파싱 실패 {qfile}: {e}\n")
            qfile.unlink()  # 깨진 것은 버림
            continue

        # 분류
        classification = classify_event(event)

        # 기록해야 하면 trace append
        did_capture = False
        if classification.get("should_capture"):
            did_capture = _capture_to_trace(event, classification)
            if did_capture:
                captured += 1

        # 아카이브
        archive_name = qfile.name
        archive_path = CAPTURE_ARCHIVE / archive_name
        try:
            qfile.rename(archive_path)
        except Exception:
            qfile.unlink()

        # 로그
        _log_processing({
            "timestamp": now_iso(),
            "file": qfile.name,
            "tool": event.get("tool_name"),
            "should_capture": classification.get("should_capture", False),
            "kind": classification.get("kind", ""),
            "reason": classification.get("reason", ""),
            "captured": did_capture,
        })

        processed += 1

    # 아카이브 정리 (최근 1000개만)
    try:
        archives = sorted(CAPTURE_ARCHIVE.glob("*.json"))
        if len(archives) > 1000:
            for old in archives[:len(archives) - 800]:
                old.unlink()
    except Exception:
        pass

    return {"processed": processed, "captured": captured,
            "archived": processed}


def _capture_to_trace(event: dict, cls: dict) -> bool:
    """active trace에 trace_manager.append 호출."""
    # active trace 존재 확인
    active_file = Path(".claude/memory/_active_trace.txt")
    if not active_file.exists():
        # active trace 없으면 무시 (Step 3이어도 trace 없으면 기록 안 함)
        return False
    try:
        active_id = active_file.read_text(encoding="utf-8").strip()
        if not active_id:
            return False
    except Exception:
        return False

    trace_file = Path(".claude/memory/traces") / f"{active_id}.md"
    if not trace_file.exists():
        return False

    # trace_manager와 같은 포맷으로 append
    # (import해서 쓰는 대신 직접 append — 훅 실행이 빠르게 끝나야 함)
    kind = cls["kind"]
    icon_map = {
        "note": "📝", "tried": "🧪", "error": "❌",
        "resolved": "✅", "hypothesis": "💡", "result": "📊",
    }
    icon = icon_map.get(kind, "•")
    timestamp = datetime.now().strftime("%H:%M")
    header = f"## {timestamp} {icon} {cls['title']} _(auto)_"
    block = f"\n{header}\n\n{cls['content']}\n"

    try:
        from harness_common import append_line_atomic
        append_line_atomic(trace_file, block)
    except Exception as e:
        sys.stderr.write(f"⚠️  trace append 실패: {e}\n")
        return False

    # 섹션 임베딩 색인 (best-effort)
    try:
        import embeddings_store
        section_id = f"{active_id}::{datetime.now().strftime('%H%M%S-auto')}"
        embeddings_store.index_document(
            "trace_sections", section_id,
            f"{cls['title']}: {cls['content'][:500]}"
        )
    except Exception:
        pass

    # 인덱스의 section_count 갱신
    try:
        idx_file = Path(".claude/memory/_traces_index.yaml")
        with read_modify_write(idx_file) as idx:
            if active_id in idx.get("traces", {}):
                idx["traces"][active_id]["section_count"] = \
                    idx["traces"][active_id].get("section_count", 0) + 1
                idx["traces"][active_id]["last_append"] = now_iso()
                idx["traces"][active_id]["auto_captures"] = \
                    idx["traces"][active_id].get("auto_captures", 0) + 1
    except Exception:
        pass

    return True


def _log_processing(entry: dict):
    """처리 로그 기록 (rolling 500)."""
    try:
        with read_modify_write(CAPTURE_LOG) as data:
            data.setdefault("entries", []).append(entry)
            if len(data["entries"]) > 500:
                data["entries"] = data["entries"][-400:]
    except Exception:
        pass


# ────────────────────────────── 명령 함수 ──────────────────────────────


def cmd_enqueue(args):
    """stdin에서 JSON 받아서 큐에 적재."""
    try:
        raw = sys.stdin.read()
    except Exception as e:
        sys.stderr.write(f"⚠️  stdin 읽기 실패: {e}\n")
        sys.exit(1)

    if not raw.strip():
        sys.stderr.write("⚠️  stdin 비어있음\n")
        sys.exit(0)

    try:
        event = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"⚠️  JSON 파싱 실패: {e}\n")
        sys.exit(0)

    enqueue_event(event)
    # 훅은 빠르게 종료해야 함. 출력 없이 exit 0


def cmd_process(args):
    result = process_queue(limit=args.limit)
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return
    print(f"처리: {result['processed']}, "
          f"캡처: {result['captured']}, "
          f"아카이브: {result['archived']}")


def cmd_process_watch(args):
    """큐를 주기적으로 폴링."""
    print(f"🔄 watch 모드 시작 (간격 {args.interval}초, Ctrl+C로 종료)")
    try:
        while True:
            result = process_queue(limit=args.limit)
            if result["processed"] > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"processed={result['processed']} "
                      f"captured={result['captured']}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n중단됨")


def cmd_stats(args):
    ensure_runtime()
    log = load_yaml(CAPTURE_LOG) or {}
    entries = log.get("entries", [])
    queue_size = len(list(CAPTURE_QUEUE.glob("*.json"))) \
        if CAPTURE_QUEUE.exists() else 0

    # 통계
    total = len(entries)
    captured = sum(1 for e in entries if e.get("captured"))
    by_tool = {}
    by_kind = {}
    for e in entries:
        tool = e.get("tool", "?")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        kind = e.get("kind") or "(skipped)"
        by_kind[kind] = by_kind.get(kind, 0) + 1

    if args.format == "json":
        print(json.dumps({
            "total_processed": total,
            "total_captured": captured,
            "queue_size": queue_size,
            "by_tool": by_tool,
            "by_kind": by_kind,
            "recent": entries[-10:],
        }, ensure_ascii=False, indent=2))
        return

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 Capture Worker 통계")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"처리 이력:  {total}건")
    print(f"캡처됨:     {captured}건 ({100*captured//max(total,1)}%)")
    print(f"대기 큐:    {queue_size}건")
    print()
    print("tool별 분포:")
    for t, c in sorted(by_tool.items(), key=lambda x: -x[1]):
        print(f"   {t:15s} {c:4d}")
    print()
    print("kind별 분포:")
    for k, c in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"   {k:15s} {c:4d}")


def cmd_flush(args):
    ensure_runtime()
    files = list(CAPTURE_QUEUE.glob("*.json"))
    for f in files:
        f.unlink()
    print(f"✅ 큐 비움 ({len(files)}건 삭제)")


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(description="Capture Worker — PostToolUse 자동 캡처")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("enqueue", help="stdin JSON을 큐에 적재 (훅에서 호출)")

    pp = sub.add_parser("process", help="큐의 이벤트 처리")
    pp.add_argument("--limit", type=int, default=None)
    pp.add_argument("--format", choices=["text", "json"], default="text")

    wp = sub.add_parser("process-watch", help="주기적 폴링")
    wp.add_argument("--interval", type=float, default=5.0)
    wp.add_argument("--limit", type=int, default=None)

    sp = sub.add_parser("stats", help="처리 이력")
    sp.add_argument("--format", choices=["text", "json"], default="text")

    sub.add_parser("flush", help="큐 비우기")
    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        "enqueue": cmd_enqueue,
        "process": cmd_process,
        "process-watch": cmd_process_watch,
        "stats": cmd_stats,
        "flush": cmd_flush,
    }
    fn = dispatch.get(args.cmd)
    if not fn:
        sys.stderr.write(f"❌ 명령 없음: {args.cmd}\n")
        sys.exit(1)
    fn(args)


if __name__ == "__main__":
    main()
