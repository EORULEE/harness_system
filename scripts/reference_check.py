#!/usr/bin/env python3
"""reference_check.py — 답변 안 외부 사실 인용 → references/INDEX.md 와 매칭

Stop hook (advisory) 으로 통합. 답변에 markdown 링크 [제목](URL) 또는 인용 패턴
발견 시, 프로젝트 references/ 또는 글로벌 references/ 의 INDEX.md 와 매칭.

매칭 안 되는 새 인용 (외부 URL) 시 advisory 경고:
  ⚠️  새 인용 N건 — references/<topic>.md 에 영구 저장 권장

사용:
  echo "$ASSISTANT_TEXT" | python3 reference_check.py
  python3 reference_check.py --text-file response.txt
"""

from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path

# Markdown 링크 패턴: [제목](URL)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

# 보조 인용 패턴 (URL 만)
URL_RE = re.compile(r"https?://[^\s\)\]]+")

# 출처 카테고리 (글로벌 CLAUDE.md feedback_references 규율)
CATEGORY_DOMAINS = {
    1: ["arxiv.org", "doi.org", "ieee.org", "nature.com", "science.org",
        "agu.org", "egu.org", "mdpi.com", "elsevier.com", "springer.com"],
    2: ["nasa.gov", "esa.int", "usgs.gov", "amap.no", "ipcc.ch", "kigam.re.kr"],
    3: ["iso.org", "iers.org", "ogc.org", "rfc-editor.org"],
    4: ["microsoft.github.io", "docs.python.org", "readthedocs.io",
        "code.claude.com", "openai.com/docs", "anthropic.com/docs"],
    5: ["medium.com", "stackoverflow.com", "github.com/discussions",
        "dev.to", ".blog", "forum."],  # 보조 (메인 인용 금지)
}


def classify_url(url: str) -> int:
    for cat, domains in CATEGORY_DOMAINS.items():
        for d in domains:
            if d in url:
                return cat
    return 0  # 미분류


def find_references_dir(cwd: Path) -> Path | None:
    """프로젝트 .claude/references/ 또는 글로벌 references/ 찾기."""
    # 1. 프로젝트
    project_refs = cwd / ".claude" / "references"
    if project_refs.exists():
        return project_refs

    # 2. 글로벌 (cwd-hash 기반)
    home = Path(os.environ.get("HOME", os.path.expanduser("~")))
    cwd_hash = str(cwd).replace("/", "-").replace("\\", "-").replace(":", "-").replace("_", "-")
    cwd_hash = cwd_hash.lstrip("-")
    global_refs = home / ".claude" / "projects" / cwd_hash / "references"
    if global_refs.exists():
        return global_refs

    return None


def load_indexed_topics(refs_dir: Path) -> set[str]:
    """INDEX.md 에서 등록된 topic-slug 집합 추출."""
    index_file = refs_dir / "INDEX.md"
    if not index_file.exists():
        return set()
    text = index_file.read_text(encoding="utf-8")
    # 패턴: [topic-slug](file.md) — 설명
    topics = set()
    for m in re.finditer(r"\[([\w-]+)\]\(([\w-]+)\.md\)", text):
        topics.add(m.group(1))
    return topics


def check_response(text: str, refs_dir: Path | None) -> dict:
    """답변 분석 + 참고문헌 매칭."""
    md_links = MD_LINK_RE.findall(text)  # [(title, url), ...]
    bare_urls = [u for u in URL_RE.findall(text)
                 if not any(u in (link[1]) for link in md_links)]

    classified = []
    for title, url in md_links:
        classified.append({
            "title": title,
            "url": url,
            "category": classify_url(url),
            "format": "markdown_link",
        })
    for url in bare_urls:
        classified.append({
            "title": "(no title)",
            "url": url,
            "category": classify_url(url),
            "format": "bare_url",
        })

    indexed = load_indexed_topics(refs_dir) if refs_dir else set()

    # 새 인용 (INDEX 와 매칭 안 되는 도메인)
    # 단순 휴리스틱: 도메인 단어가 INDEX 의 topic-slug 에 있나?
    new_citations = []
    for c in classified:
        domain = re.sub(r"^https?://(www\.)?", "", c["url"]).split("/")[0]
        domain_root = domain.split(".")[-2] if "." in domain else domain
        is_indexed = any(domain_root in t.lower() for t in indexed)
        if not is_indexed:
            new_citations.append(c)

    cat_summary = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 0: 0}
    for c in classified:
        cat_summary[c["category"]] += 1

    return {
        "total_citations": len(classified),
        "indexed_topics": len(indexed),
        "new_citations": new_citations,
        "category_summary": cat_summary,
        "warnings": [],
        "advisory": None,
    }


def render_advisory(result: dict) -> str:
    if result["total_citations"] == 0:
        return ""  # 외부 사실 인용 없음 — advisory 없음

    lines = []
    new_n = len(result["new_citations"])
    if new_n > 0:
        lines.append(f"⚠️  reference_check (advisory): 새 인용 {new_n} 건 발견")
        for c in result["new_citations"][:5]:
            cat_str = f"카테고리 {c['category']}" if c["category"] else "미분류"
            lines.append(f"   - [{cat_str}] {c['title']}: {c['url']}")
        if new_n > 5:
            lines.append(f"   ... +{new_n - 5} 건 더")
        lines.append("   → references/<topic-slug>.md 에 영구 저장 + INDEX.md 등록 권장")

    # 카테고리 5 (블로그·포럼) 메인 인용 경고
    if result["category_summary"][5] > 0:
        lines.append(
            f"⚠️  reference_check: 카테고리 5 (블로그·포럼·SO) {result['category_summary'][5]} 건 — "
            "메인 인용 금지. 학술 주장이면 카테고리 1 (논문) 으로 교체 필요"
        )

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", help="답변 텍스트 파일 (없으면 stdin)")
    ap.add_argument("--cwd", default=".", help="프로젝트 cwd (default .)")
    ap.add_argument("--format", default="text", choices=["text", "json"])
    args = ap.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    cwd = Path(args.cwd).resolve()
    refs_dir = find_references_dir(cwd)
    result = check_response(text, refs_dir)

    if args.format == "json":
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        advisory = render_advisory(result)
        if advisory:
            print(advisory, file=sys.stderr)

    # exit 0 — advisory only (절대 차단 X)
    sys.exit(0)


if __name__ == "__main__":
    main()
