#!/usr/bin/env python3
"""schema_lint — vault/wiki 페이지를 page-schema.yaml 규칙에 대해 결정적 검증.
프론트매터 필수 필드(타입별) + 내부 broken wikilink(경로식) 검사. LLM 0.

Usage: python3 schema_lint.py            # 리포트 + exit 0/1
       WIKI_ROOT=... python3 schema_lint.py
종료코드: 위반 0 → 0, 위반 있으면 → 1.
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WIKI = Path(os.environ.get("WIKI_ROOT", ROOT / "vault" / "wiki")).resolve()

# page-schema.yaml 미러 (정본=page-schema.yaml; 변경 시 동기)
COMMON = ["title", "type", "tags", "last_updated"]
BY_TYPE = {
    "source":  ["source_file", "sha256", "trust", "trust_boundary", "date"],
    "entity":  ["sources", "as_of"],
    "concept": ["sources", "as_of"],
    "synthesis": ["sources", "as_of"],
    "domain":  ["sources", "as_of"],
    "method":  ["sources", "as_of"],
    "dataset": ["sources", "as_of"],
    "sensor":  ["sources", "as_of"],
    "metric":  ["sources", "as_of"],
}
META = {"index.md", "log.md", "ingest_log.md", "lint-report.md", "health-report.md", "contradictions.md"}
WIKI_SUBDIRS = ("sources/", "entities/", "concepts/", "syntheses/",
                "domains/", "methods/", "datasets/", "sensors/", "metrics/")


def pages():
    return [p for p in WIKI.rglob("*.md") if p.name not in META]


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def main():
    all_ids = set()
    for p in pages():
        rel = p.relative_to(WIKI).as_posix()[:-3]      # page_id (no .md)
        all_ids.add(rel.lower())
        all_ids.add(p.stem.lower())
    violations = []
    for p in pages():
        rel = p.relative_to(WIKI).as_posix()
        t = p.read_text(encoding="utf-8")
        fm = frontmatter(t)
        # 프론트매터 필수
        for f in COMMON:
            if f not in fm or not fm[f]:
                violations.append(f"{rel}: 필수 필드 누락 '{f}'")
        typ = (fm.get("type") or "").strip('"\'')
        # domain-overview 등 별형 허용: 접두 매칭
        base = typ.split("-")[0]
        req = BY_TYPE.get(typ) or BY_TYPE.get(base) or []
        for f in req:
            if f not in fm:
                violations.append(f"{rel}: type={typ} 필수 필드 누락 '{f}'")
        # source 신뢰경계·sha 존재(거버넌스)
        if typ == "source":
            if "untrusted" not in t.lower() and "trust_boundary" not in fm:
                violations.append(f"{rel}: source인데 trust_boundary 신뢰경계 명문 없음")
        # 내부 broken wikilink (경로식만 — 외부 human note 제외)
        for link in set(re.findall(r"\[\[([^\]]+)\]\]", t)):
            tgt = link.split("|")[0].split("#")[0].strip().lower()
            if tgt.startswith(WIKI_SUBDIRS):           # 위키 내부 경로식
                if tgt not in all_ids and tgt.split("/")[-1] not in all_ids:
                    violations.append(f"{rel}: broken 내부 링크 [[{link}]]")
    if violations:
        print(f"SCHEMA LINT: {len(violations)} 위반")
        for v in violations:
            print("  ✗", v)
        return 1
    print(f"SCHEMA LINT: PASS ({len(pages())} 페이지, 위반 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
