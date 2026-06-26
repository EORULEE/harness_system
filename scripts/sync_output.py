#!/usr/bin/env python3
"""
sync_output.py — .claude/ 내부 상태 → _output/ 표준 폴더 자동 동기화

용도:
  - 세션 종료 시 (stop hook) 자동 호출
  - 수동: python3 scripts/sync_output.py sync
  - 초기화: python3 scripts/sync_output.py init

_output/ 구조:
  _output/
  ├── reports/           ← HTML 보고서
  ├── memory/            ← decisions.md, domain-facts.md, experiments.md, context-bundle.md
  ├── traces/            ← trace 요약 (INDEX.md + 개별 .md)
  ├── references/        ← 외부 문헌 검색 결과
  ├── logs/              ← session_log.jsonl, tool-call-log.jsonl
  ├── campaigns/         ← 캠페인별 최종 산출물 (RESEARCH.md, PLAN.md, artifacts/)
  └── README.md

의존성: 없음 (stdlib only)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("_output")

SUBDIRS = [
    "reports",
    "memory",
    "traces",
    "references",
    "logs",
    "campaigns",
]

MEMORY_SRC = Path(".claude/memory")
TRACES_SRC = MEMORY_SRC / "traces"
REFERENCES_SRC = Path(".claude/references")
RUNTIME_SRC = Path(".claude/runtime")
CAMPAIGNS_SRC = Path(".claude/campaigns")


def init_structure():
    """_output/ 표준 디렉토리 생성 + README.md 작성."""
    for sub in SUBDIRS:
        (OUTPUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    readme = OUTPUT_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# _output/ — 하네스 산출물 표준 폴더\n\n"
            "이 폴더는 `.claude/` 내부 엔진 상태에서 **사용자 열람용 산출물**만 자동 동기화합니다.\n\n"
            "| 폴더 | 내용 | 원본 위치 |\n"
            "|------|------|-----------|\n"
            "| `reports/` | HTML 보고서 | `reports/` (html-report-workflow) |\n"
            "| `memory/` | 의사결정·도메인 지식·실험 기록 | `.claude/memory/` |\n"
            "| `traces/` | trace 요약 | `.claude/memory/traces/` |\n"
            "| `references/` | 외부 문헌 검색 결과 | `.claude/references/` |\n"
            "| `logs/` | 세션 로그·도구 호출 기록 | `.claude/runtime/` |\n"
            "| `campaigns/` | 캠페인 산출물 | `.claude/campaigns/` |\n\n"
            "**자동 동기화**: 세션 종료 시 `sync_output.py` 가 자동 실행됩니다.\n\n"
            f"*생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n",
            encoding="utf-8",
        )
    print(f"✅ _output/ 구조 초기화 완료 ({len(SUBDIRS)} 폴더)")


def _copy_if_newer(src: Path, dst: Path) -> bool:
    """src가 dst보다 새로우면 복사. 반환: 복사 여부."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and src.stat().st_mtime <= dst.stat().st_mtime:
        return False
    shutil.copy2(src, dst)
    return True


def _copy_dir_selective(src_dir: Path, dst_dir: Path, pattern: str = "*.md", recursive: bool = False) -> int:
    """src_dir에서 pattern에 맞는 파일만 dst_dir로 복사. 반환: 복사 건수."""
    if not src_dir.exists():
        return 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    glob_fn = src_dir.rglob if recursive else src_dir.glob
    for f in glob_fn(pattern):
        if not f.is_file():
            continue
        if f.name.startswith("_") and f.name not in ("_context.md",):
            continue
        rel = f.relative_to(src_dir)
        if _copy_if_newer(f, dst_dir / rel):
            count += 1
    return count


def sync_memory() -> int:
    """decisions.md, domain-facts.md, experiments_table.md, _context.md → _output/memory/"""
    dst = OUTPUT_DIR / "memory"
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    targets = [
        (MEMORY_SRC / "decisions.md", dst / "decisions.md"),
        (MEMORY_SRC / "domain-facts.md", dst / "domain-facts.md"),
        (MEMORY_SRC / "experiments_table.md", dst / "experiments.md"),
        (MEMORY_SRC / "_context.md", dst / "context-bundle.md"),
        (MEMORY_SRC / "codebase-map.md", dst / "codebase-map.md"),
    ]
    for src, d in targets:
        if _copy_if_newer(src, d):
            count += 1
    return count


def sync_traces() -> int:
    """traces/ 폴더의 .md 파일들 → _output/traces/"""
    return _copy_dir_selective(TRACES_SRC, OUTPUT_DIR / "traces", "*.md")


def sync_references() -> int:
    """references/ (로컬 또는 글로벌) → _output/references/"""
    count = _copy_dir_selective(REFERENCES_SRC, OUTPUT_DIR / "references", "*.md")
    global_refs = _find_global_references()
    if global_refs and global_refs.exists():
        count += _copy_dir_selective(global_refs, OUTPUT_DIR / "references", "*.md")
    return count


def _find_global_references() -> Path | None:
    """~/.claude/projects/{cwd-hash}/references/ 경로 탐색."""
    claude_home = Path.home() / ".claude" / "projects"
    if not claude_home.exists():
        return None
    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)
    for variant in [cwd_str.replace("/", "-").replace("\\", "-").replace("_", "-")]:
        if variant.startswith("-"):
            candidate = claude_home / variant / "references"
        else:
            candidate = claude_home / f"-{variant}" / "references"
        if candidate.exists():
            return candidate
    for d in claude_home.iterdir():
        refs = d / "references"
        if refs.exists() and refs.is_dir():
            return refs
    return None


def sync_logs() -> int:
    """session_log.jsonl, tool-call-log.jsonl → _output/logs/"""
    dst = OUTPUT_DIR / "logs"
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    if _copy_if_newer(RUNTIME_SRC / "session_log.jsonl", dst / "session_log.jsonl"):
        count += 1
    tool_log = Path.home() / ".claude" / "tool-call-log.jsonl"
    if _copy_if_newer(tool_log, dst / "tool-call-log.jsonl"):
        count += 1
    return count


def sync_campaigns() -> int:
    """각 캠페인의 artifacts/, progress.md, RESEARCH.md, PLAN.md → _output/campaigns/"""
    if not CAMPAIGNS_SRC.exists():
        return 0
    dst_base = OUTPUT_DIR / "campaigns"
    dst_base.mkdir(parents=True, exist_ok=True)
    count = 0

    for camp_dir in CAMPAIGNS_SRC.iterdir():
        if not camp_dir.is_dir() or camp_dir.name.startswith("_"):
            continue

        camp_name = camp_dir.name
        dst_camp = dst_base / camp_name

        if _copy_if_newer(camp_dir / "progress.md", dst_camp / "progress.md"):
            count += 1

        artifacts = camp_dir / "artifacts"
        if artifacts.exists():
            count += _copy_dir_selective(artifacts, dst_camp / "artifacts", "*")

    return count


def sync_reports() -> int:
    """프로젝트 루트의 reports/ → _output/reports/ (이전 경로 호환)."""
    old_reports = Path("reports")
    if not old_reports.exists():
        return 0
    dst = OUTPUT_DIR / "reports"
    count = 0
    for item in old_reports.iterdir():
        if item.is_dir():
            count += _copy_dir_selective(item, dst / item.name, "*", recursive=True)
        elif item.is_file():
            if _copy_if_newer(item, dst / item.name):
                count += 1
    return count


def sync_all() -> dict[str, int]:
    """모든 카테고리 동기화. 반환: {category: copied_count}."""
    init_structure()
    results = {
        "memory": sync_memory(),
        "traces": sync_traces(),
        "references": sync_references(),
        "logs": sync_logs(),
        "campaigns": sync_campaigns(),
        "reports": sync_reports(),
    }
    return results


def print_summary(results: dict[str, int]):
    total = sum(results.values())
    if total == 0:
        print("_output/ 이미 최신 상태 (변경 없음)")
        return
    print(f"📦 _output/ 동기화 완료 — {total}건 갱신:")
    for cat, n in results.items():
        if n > 0:
            print(f"  {cat}: {n}건")


def main():
    parser = argparse.ArgumentParser(description="_output/ 표준 폴더 동기화")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="_output/ 구조만 초기화")
    sub.add_parser("sync", help="전체 동기화 (기본)")
    sub.add_parser("status", help="현재 _output/ 상태 출력")

    args = parser.parse_args()
    cmd = args.command or "sync"

    if cmd == "init":
        init_structure()
    elif cmd == "sync":
        results = sync_all()
        print_summary(results)
    elif cmd == "status":
        if not OUTPUT_DIR.exists():
            print("_output/ 없음 — 'sync_output.py init' 로 생성하세요")
            sys.exit(1)
        for sub_name in SUBDIRS:
            p = OUTPUT_DIR / sub_name
            if p.exists():
                files = list(p.rglob("*"))
                file_count = len([f for f in files if f.is_file()])
                print(f"  {sub_name}/: {file_count} 파일")
            else:
                print(f"  {sub_name}/: (없음)")


if __name__ == "__main__":
    main()
