#!/usr/bin/env python3
"""hallucination_guard.py — 답변 안 file path / function 인용 → 실제 존재 검증

Stop hook (advisory) 으로 통합. 답변에 file path 또는 function() 인용 시 실제 존재 grep 검증.

검증 대상:
- file path: `scripts/foo.py`, `hooks/bar.mjs`, `참고자료/...` 등
- 코드 인용: `function_name()`, `Class.method()` (현재 advisory only)
- 절대 path: `/mnt/...`, `D:\...`, `~/.claude/...`

미존재 시 advisory 경고:
  ⚠️  hallucination_guard: 미존재 파일·함수 N건
  - scripts/missing.py — 실제 없음

사용:
  echo "$ASSISTANT_TEXT" | python3 hallucination_guard.py --cwd /path/to/project
"""

from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# File path 패턴 — 일반적 형식
# - 상대: scripts/foo.py, .claude/agents/c-lead.md
# - 절대 (Linux): <PATH>/..., /home/user/...
# - 절대 (Windows): D:\..., C:/..., D:/...
FILE_PATTERNS = [
    # backtick 안 path: `scripts/foo.py`
    re.compile(r"`([\w가-힣\-_./\\]+\.\w{1,5})`"),
    # 코드 fence 안 path 도 잡음
    re.compile(r"`([\w가-힣\-_./\\]+/[\w가-힣\-_.]+)`"),
    # plain text 의 path (.py, .md, .json, .mjs, .yaml, .yml, .txt, .sh, .ps1, .html, .css)
    re.compile(r"\b([\w가-힣\-_./\\]+\.(?:py|md|json|mjs|yaml|yml|txt|sh|ps1|html|css|tsx|jsx|ts|js))\b"),
]

# 절대 Linux/WSL path
ABS_LINUX_RE = re.compile(r"(?:^|\s)(/(?:mnt|home|usr|opt|tmp|var|etc)/[\w가-힣\-_./]+)")
# 절대 Windows path
ABS_WIN_RE = re.compile(r"\b([A-Za-z]:[\\/][\w가-힣\-_.\\/]+)")

# Function 패턴 (advisory only — 검증 어려움)
FUNC_RE = re.compile(r"\b(\w+\.)?(\w+)\(\)")

# 무시 패턴 (예시·일반론·placeholder)
IGNORE_PATTERNS = [
    re.compile(r"^<.*>$"),  # <placeholder>
    re.compile(r"\.\.\."),   # ... (생략)
    re.compile(r"^\$"),       # $variable
    re.compile(r"^/path/to/"),  # /path/to/example
    re.compile(r"^example/"),
    re.compile(r"^foo|bar|baz"),  # 예시 변수명
]


def is_ignorable(path: str) -> bool:
    for p in IGNORE_PATTERNS:
        if p.search(path):
            return True
    if path.count(".") > 5:  # 너무 많은 dot — URL·버전 등
        return False
    if len(path) < 3:
        return True
    return False


def normalize_path(path: str, cwd: Path) -> Path | None:
    """path 를 cwd 기준 절대 path 로 변환."""
    p = path.strip().rstrip(".,;:)")
    if not p:
        return None

    # Windows path → WSL path 변환 (D:\foo → <PATH>/foo)
    win_match = re.match(r"^([A-Za-z]):[\\/](.*)", p)
    if win_match:
        drive = win_match.group(1).lower()
        rest = win_match.group(2).replace("\\", "/")
        p = f"/mnt/{drive}/{rest}"

    # 절대 path
    if p.startswith("/") or p.startswith("~"):
        path_obj = Path(p).expanduser() if p.startswith("~") else Path(p)
    else:
        # 상대 path → cwd 기준
        path_obj = cwd / p

    return path_obj


def check_file_existence(path_str: str, cwd: Path) -> dict:
    """단일 path 검증."""
    if is_ignorable(path_str):
        return {"path": path_str, "status": "ignored"}

    path_obj = normalize_path(path_str, cwd)
    if path_obj is None:
        return {"path": path_str, "status": "ignored"}

    try:
        if path_obj.exists():
            return {"path": path_str, "status": "exists", "resolved": str(path_obj)}
        else:
            return {"path": path_str, "status": "missing", "resolved": str(path_obj)}
    except (OSError, ValueError):
        return {"path": path_str, "status": "ignored"}


def extract_paths(text: str) -> list[str]:
    """답변에서 file path 후보 추출 (중복 제거)."""
    paths = set()

    # 1. backtick·plain text file path (확장자 기반)
    for pattern in FILE_PATTERNS:
        for m in pattern.findall(text):
            paths.add(m if isinstance(m, str) else m[0])

    # 2. 절대 Linux/WSL
    for m in ABS_LINUX_RE.findall(text):
        paths.add(m.strip())

    # 3. 절대 Windows
    for m in ABS_WIN_RE.findall(text):
        paths.add(m.strip())

    return list(paths)


def render_advisory(missing: list[dict], total: int) -> str:
    if not missing:
        return ""
    lines = [f"⚠️  hallucination_guard (advisory): 미존재 path {len(missing)}/{total} 건"]
    for m in missing[:8]:
        lines.append(f"   - {m['path']}")
        if m.get("resolved") and m["resolved"] != m["path"]:
            lines.append(f"     (resolved: {m['resolved']})")
    if len(missing) > 8:
        lines.append(f"   ... +{len(missing) - 8} 건 더")
    lines.append("   → 실제 존재 확인 후 답변 수정 권장. 가짜 path 인용 금지.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", help="답변 텍스트 (없으면 stdin)")
    ap.add_argument("--cwd", default=".", help="프로젝트 cwd")
    ap.add_argument("--format", default="text", choices=["text", "json"])
    ap.add_argument("--strict", action="store_true",
                    help="미존재 발견 시 exit 2 (차단 — 기본 advisory)")
    args = ap.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    cwd = Path(args.cwd).resolve()
    candidate_paths = extract_paths(text)

    results = [check_file_existence(p, cwd) for p in candidate_paths]
    missing = [r for r in results if r["status"] == "missing"]
    exists = [r for r in results if r["status"] == "exists"]
    ignored = [r for r in results if r["status"] == "ignored"]

    summary = {
        "total_extracted": len(candidate_paths),
        "exists": len(exists),
        "missing": len(missing),
        "ignored": len(ignored),
        "missing_details": missing,
    }

    if args.format == "json":
        import json
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        advisory = render_advisory(missing, len(candidate_paths))
        if advisory:
            print(advisory, file=sys.stderr)

    # exit code
    if args.strict and missing:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
