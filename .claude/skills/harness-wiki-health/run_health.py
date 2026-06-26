#!/usr/bin/env python3
"""Thin wrapper — vendored health.py(byte-exact)를 vault/wiki에 대해 실행.
벤더 원본은 수정하지 않고 모듈 경로 상수만 monkeypatch한다.

Usage: python3 run_health.py [--json] [--save]
환경변수 WIKI_ROOT로 위키 경로 override 가능(기본 <project>/vault/wiki).
"""
import os, sys, json, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]                      # <project root>
WIKI = Path(os.environ.get("WIKI_ROOT", ROOT / "vault" / "wiki")).resolve()
VENDOR = ROOT / ".claude/skills/_wiki-core/vendors/llm-wiki-agent/tools/health.py"

spec = importlib.util.spec_from_file_location("vendored_health", VENDOR)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 경로 재지정 (벤더 원본 불변, 호출 시점 globals 해석)
m.REPO_ROOT = WIKI.parent
m.WIKI_DIR = WIKI
m.INDEX_FILE = WIKI / "index.md"
m.LOG_FILE = WIKI / "log.md"

results = m.run_health()
if "--json" in sys.argv:
    print(json.dumps(results, indent=2, ensure_ascii=False))
else:
    report = m.format_report(results)
    print(report)
    if "--save" in sys.argv:
        (WIKI / "health-report.md").write_text(report, encoding="utf-8")
        print(f"\nSaved: {WIKI / 'health-report.md'}")
