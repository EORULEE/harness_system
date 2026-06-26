#!/usr/bin/env python3
"""Thin wrapper — vendored build_graph.py(byte-exact)를 vault/wiki에 대해 결정적 모드로 실행.
EXTRACTED(wikilink) 엣지만 생성(infer=False) → litellm 불필요. 벤더 원본은 수정하지 않고
모듈 경로 상수만 monkeypatch한다.

Usage: python3 run_graph.py [--open]
환경변수 WIKI_ROOT로 위키 경로 override 가능(기본 <project>/vault/wiki).
"""
import os, sys, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]                      # <project root>
WIKI = Path(os.environ.get("WIKI_ROOT", ROOT / "vault" / "wiki")).resolve()
GRAPHDIR = WIKI / "graph"
VENDOR = ROOT / ".claude/skills/_wiki-core/vendors/llm-wiki-agent/tools/build_graph.py"

GRAPHDIR.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("vendored_build_graph", VENDOR)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 경로 재지정 (벤더 원본 불변)
m.REPO_ROOT = WIKI.parent
m.WIKI_DIR = WIKI
m.GRAPH_DIR = GRAPHDIR
m.GRAPH_JSON = GRAPHDIR / "graph.json"
m.GRAPH_HTML = GRAPHDIR / "graph.html"
m.CACHE_FILE = GRAPHDIR / ".cache.json"
m.INFERRED_EDGES_FILE = GRAPHDIR / ".inferred_edges.jsonl"
m.LOG_FILE = WIKI / "log.md"
m.SCHEMA_FILE = ROOT / ".claude/skills/_wiki-core/wiki-rules.md"

# [의도적 일탈 #3 — VENDOR.md] 위키링크 경로/별칭/앵커 위키링크 해석 보강.
# 벤더 build_extracted_edges는 bare [[stem]]만 매칭 → [[path/file|alias#anchor]] 미해석.
# 벤더 파일은 불변 유지하고 함수만 monkeypatch(byte-exact 원본 보존).
def _enhanced_extracted_edges(pages):
    stem_map = {p.stem.lower(): m.page_id(p) for p in pages}
    path_map = {m.page_id(p).lower(): m.page_id(p) for p in pages}
    edges, seen = [], set()
    for p in pages:
        content = m.read_file(p)
        src = m.page_id(p)
        for link in m.extract_wikilinks(content):
            t = link.split("|")[0].split("#")[0].strip().lower()
            target = path_map.get(t) or stem_map.get(t)
            if target and target != src and (src, target) not in seen:
                seen.add((src, target))
                edges.append({
                    "id": m.edge_id(src, target, "EXTRACTED"),
                    "from": src, "to": target, "type": "EXTRACTED",
                    "color": m.EDGE_COLORS["EXTRACTED"], "confidence": 1.0,
                })
    return edges
m.build_extracted_edges = _enhanced_extracted_edges

# 결정적: EXTRACTED 엣지만 (litellm 경로 미진입)
m.build_graph(infer=False, open_browser=False)   # open은 인라인 후 처리

# [의도적 일탈 #4 — VENDOR.md] graph.html의 vis-network CDN → 벤더 인라인(self-contained·외부요청 0)
CDN_TAG = '<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
VIS_JS = ROOT / ".claude/skills/_wiki-core/vendors/vis-network/vis-network.min.js"
html_path = GRAPHDIR / "graph.html"
if html_path.exists() and VIS_JS.exists():
    html = html_path.read_text(encoding="utf-8")
    if CDN_TAG in html:
        html = html.replace(CDN_TAG, "<script>\n" + VIS_JS.read_text(encoding="utf-8") + "\n</script>")
        html_path.write_text(html, encoding="utf-8")
        print("vis-network 인라인 완료 (self-contained, 외부요청 0)")

if "--open" in sys.argv and html_path.exists():
    import webbrowser
    webbrowser.open(html_path.as_uri())
print(f"graph.json / graph.html → {GRAPHDIR}")
