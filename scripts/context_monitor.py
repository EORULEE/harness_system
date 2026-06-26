#!/usr/bin/env python3
"""
context_monitor.py — 세션 transcript 기반 실측 컨텍스트 사용량

기존 방식(Claude 추정) 대신 transcript JSONL의 마지막 assistant 메시지 usage를
직접 읽어 실제 컨텍스트 사용량을 계산한다.

컨텍스트 사용량 = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
(이 합이 현재 모델에 올라간 입력 컨텍스트 크기)

사용법:
  python3 scripts/context_monitor.py                          # 현재 cwd 세션 자동 탐색
  python3 scripts/context_monitor.py --transcript <path>      # 명시
  python3 scripts/context_monitor.py --window 1000000         # 1M 윈도우 (기본)
  python3 scripts/context_monitor.py --format json            # JSON 출력

stop hook stdin 으로 transcript_path 가 오면 그것을 우선 사용.

의존성: 없음 (stdlib)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 기본 컨텍스트 윈도우 (1M). 환경변수 CONTEXT_WINDOW 로 override 가능.
DEFAULT_WINDOW = 1_000_000
WARN_THRESHOLD = 0.70
CRITICAL_THRESHOLD = 0.80


def _find_latest_transcript() -> Path | None:
    """현재 cwd 기반 ~/.claude/projects/<hash>/ 에서 최신 .jsonl 탐색."""
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return None

    cwd = str(Path.cwd().resolve())
    # cwd-hash 규칙: /, \, :, _ → -
    hash_name = cwd.replace("/", "-").replace("\\", "-").replace(":", "-").replace("_", "-")

    candidates = []
    # 정확 매칭 우선
    exact = claude_projects / hash_name
    if exact.is_dir():
        candidates.append(exact)
    # fallback: 모든 프로젝트 디렉토리
    if not candidates:
        candidates = [d for d in claude_projects.iterdir() if d.is_dir()]

    latest_file = None
    latest_mtime = -1.0
    for d in candidates:
        for jsonl in d.glob("*.jsonl"):
            if jsonl.name.endswith(".bak") or jsonl.name.endswith(".bak2"):
                continue
            mt = jsonl.stat().st_mtime
            if mt > latest_mtime:
                latest_mtime = mt
                latest_file = jsonl
    return latest_file


def _read_last_usage(transcript: Path) -> dict | None:
    """transcript의 마지막 assistant 메시지 usage 반환."""
    last_usage = None
    try:
        with transcript.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                if msg.get("role") == "assistant" and isinstance(msg.get("usage"), dict):
                    last_usage = msg["usage"]
    except OSError:
        return None
    return last_usage


def compute_context(usage: dict) -> int:
    """현재 컨텍스트 토큰 = input + cache_creation + cache_read."""
    return (
        int(usage.get("input_tokens", 0))
        + int(usage.get("cache_creation_input_tokens", 0))
        + int(usage.get("cache_read_input_tokens", 0))
    )


def _read_transcript_from_stdin() -> str | None:
    """stop hook stdin payload 에서 transcript_path 추출 (있으면)."""
    if sys.stdin.isatty():
        return None
    try:
        data = sys.stdin.read()
        if not data.strip():
            return None
        payload = json.loads(data)
        return payload.get("transcript_path")
    except (json.JSONDecodeError, OSError):
        return None


def main():
    parser = argparse.ArgumentParser(description="실측 컨텍스트 사용량 모니터")
    parser.add_argument("--transcript", help="transcript JSONL 경로 (생략 시 자동 탐색)")
    parser.add_argument("--window", type=int, default=None, help=f"컨텍스트 윈도우 (기본 {DEFAULT_WINDOW})")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--from-stdin", action="store_true", help="stdin payload에서 transcript_path 읽기")
    args = parser.parse_args()

    import os
    window = args.window or int(os.environ.get("CONTEXT_WINDOW", DEFAULT_WINDOW))

    # transcript 경로 결정: 인자 > stdin > 자동탐색
    transcript_path = args.transcript
    if not transcript_path and args.from_stdin:
        transcript_path = _read_transcript_from_stdin()
    if not transcript_path:
        found = _find_latest_transcript()
        transcript_path = str(found) if found else None

    if not transcript_path or not Path(transcript_path).exists():
        result = {"error": "transcript 미발견", "transcript": transcript_path}
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("⚠️ transcript를 찾지 못했습니다. --transcript로 경로를 지정하세요.")
        sys.exit(1)

    usage = _read_last_usage(Path(transcript_path))
    if not usage:
        result = {"error": "usage 미발견", "transcript": transcript_path}
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("⚠️ transcript에 assistant usage가 없습니다 (세션 초기).")
        sys.exit(1)

    tokens = compute_context(usage)
    pct = tokens / window if window > 0 else 0.0

    level = "ok"
    if pct >= CRITICAL_THRESHOLD:
        level = "critical"
    elif pct >= WARN_THRESHOLD:
        level = "warning"

    result = {
        "tokens": tokens,
        "window": window,
        "pct": round(pct * 100, 1),
        "level": level,
        "breakdown": {
            "input": int(usage.get("input_tokens", 0)),
            "cache_creation": int(usage.get("cache_creation_input_tokens", 0)),
            "cache_read": int(usage.get("cache_read_input_tokens", 0)),
            "output": int(usage.get("output_tokens", 0)),
        },
        "transcript": transcript_path,
    }

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # text 출력
    icon = {"ok": "📊", "warning": "⚠️", "critical": "🚨"}[level]
    print(f"{icon} Context 사용량(실측): {result['pct']}%  ({tokens:,} / {window:,} 토큰)")
    bd = result["breakdown"]
    print(f"   input {bd['input']:,} + cache_creation {bd['cache_creation']:,} + cache_read {bd['cache_read']:,}")
    if level == "warning":
        print("   ⚠️ 70% 도달 — checkpoint 저장 후 새 세션 권장")
    elif level == "critical":
        print("   🚨 80% 초과 — 강제 저장 권장 (overflow 위험)")


if __name__ == "__main__":
    main()
