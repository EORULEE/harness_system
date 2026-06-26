#!/usr/bin/env python3
"""import_legacy_memory.py — 레거시 작업 흔적을 .claude/memory/traces/ 로 자동 import

Raw extract only — LLM 해석/요약 없음 → hallucination 없음.

자동으로 잡는 것:
  1. CLAUDE*.md (CLAUDE_old, CLAUDE_new, CLAUDE_seoulrd_old 등) → traces/legacy_constitution.md
  2. *.ipynb → traces/notebook_<name>.md (markdown cells + last output, 최대 N개)
  3. *.py 모듈 폴더 (LARS, src, lib) → traces/code_<dirname>.md (파일명 + LOC + 첫 docstring)
  4. *.hwp / *.hwpx (이름에 final/최종/v[숫자] 포함 우선) → traces/hwp_*.md
     - .hwpx: python-hwpx 로 전체 본문(markdown) 추출
     - .hwp:  olefile PrvText 미리보기만 (전체 본문은 .hwpx 변환 권장)
  5. *.docx (final 우선) → traces/proposal_*.md
  5b. *.pdf (텍스트 레이어, pypdf) → traces/pdf_*.md  (2026-06-12 추가)
  5c. *.pptx (슬라이드 텍스트, zipfile+xml 무의존) → traces/pptx_*.md  (2026-06-12 추가)
  6. nl_parameter_test/, _workspace/, compare_*.py 같은 sweep 흔적 → traces/param_sweep.md
  7. *.h5 / *.pkl / *.pt / *.ckpt 모델 → traces/models.md (inventory only — content 안 dump)
  8. CLAUDE_*.md 의 도메인 절 추출 → memory/domain-facts.md stub

Secret 자동 redact:
  - model.cfg, *.env, secrets/, credentials/, *.key, *.pem 무시
  - API key 패턴 발견 시 [REDACTED]

사용:
  python scripts/import_legacy_memory.py [--root .] [--max-ipynb 10] [--dry-run]
"""

from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# 보안: 절대 dump 안 할 패턴
SECRET_PATTERNS = {"model.cfg", "secrets.json", "credentials.json", ".env"}
SECRET_DIRS = {".git", "node_modules", "__pycache__", "build_venv", "venv", ".venv",
               "build", "dist", "secrets", "credentials"}
SECRET_REGEX = re.compile(
    r'(api[_-]?key|secret[_-]?key|password|passwd|token)\s*[=:]\s*["\']?([A-Za-z0-9+/=_-]{8,})',
    re.IGNORECASE)

# 도메인 키워드 (사용자 헌법에서 추출)
DOMAIN_KEYWORDS = {
    "프로젝트": "project", "수행기관": "institution", "핵심 기술": "core_tech",
    "핵심 코드": "core_code", "에이전트": "agents", "기술 스택": "tech_stack",
    "지원 센서": "sensors",
}


def redact_secrets(text: str) -> str:
    return SECRET_REGEX.sub(r'\1=[REDACTED]', text)


def _safe_name(s: str, max_len: int = 60) -> str:
    s = s.strip(". /\\")
    if not s or s == ".":
        s = "root"
    s = re.sub(r'[\\/:*?"<>|\s.]+', '_', s)
    s = s.strip("_")
    return s[:max_len] or "root"


# ────────────────────────────────────────────────
# 1. CLAUDE*.md 통합
# ────────────────────────────────────────────────

def import_legacy_constitution(root: Path, traces: Path) -> bool:
    candidates = []
    for pattern in ["CLAUDE_old.md", "CLAUDE_new.md", "CLAUDE_seoulrd_old.md",
                    "CLAUDE_*.md", "CLAUDE.md.bak"]:
        for p in root.glob(pattern):
            # 현재 활성 CLAUDE.md 는 스킵
            if p.name == "CLAUDE.md":
                continue
            candidates.append(p)

    if not candidates:
        print("  ℹ️  레거시 CLAUDE*.md 없음 — skip")
        return False

    out = traces / "legacy_constitution.md"
    parts = [f"---\nsource: {[c.name for c in candidates]}\ntype: legacy_user_constitution\n---\n",
             f"# legacy_constitution — 사용자 본인 헌법 모음\n"]
    for c in candidates:
        try:
            text = c.read_text(encoding="utf-8")
        except Exception as e:
            text = f"[읽기 실패: {e}]"
        parts.append(f"\n\n## ── {c.name} ({len(text)} chars) ──\n\n{redact_secrets(text)}")

    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  ✅ legacy_constitution.md ({sum(c.stat().st_size for c in candidates)} bytes 통합)")
    return True


# ────────────────────────────────────────────────
# 2. .ipynb 추출 (markdown + last output)
# ────────────────────────────────────────────────

def import_notebooks(root: Path, traces: Path, max_count: int = 10) -> int:
    notebooks = []
    for p in root.rglob("*.ipynb"):
        if any(d in p.parts for d in SECRET_DIRS):
            continue
        if ".ipynb_checkpoints" in p.parts:
            continue
        notebooks.append(p)

    notebooks = notebooks[:max_count]
    if not notebooks:
        print("  ℹ️  ipynb 없음 — skip")
        return 0

    count = 0
    for nb_path in notebooks:
        try:
            nb = json.loads(nb_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️  {nb_path.name} 읽기 실패: {e}")
            continue

        cells = nb.get("cells", [])
        md_count = sum(1 for c in cells if c.get("cell_type") == "markdown")
        code_count = sum(1 for c in cells if c.get("cell_type") == "code")

        parts = [
            f"---\nsource: {nb_path.relative_to(root)}\ntype: notebook_extract\ncells: md={md_count} code={code_count}\n---\n",
            f"# notebook — {nb_path.stem}\n",
            f"\n경로: `{nb_path.relative_to(root)}`",
            f"\n총 셀: markdown {md_count}, code {code_count}\n",
        ]

        # markdown 셀 모두 추출
        parts.append("\n## Markdown 셀 (모두)\n")
        md_idx = 0
        for c in cells:
            if c.get("cell_type") != "markdown":
                continue
            md_idx += 1
            src = "".join(c.get("source", []))
            parts.append(f"\n### md cell #{md_idx}\n\n{src}\n")

        # 마지막 5개 code cell 의 source 와 output 추출
        parts.append("\n## 마지막 5 code cell\n")
        last_codes = [c for c in cells if c.get("cell_type") == "code"][-5:]
        for i, c in enumerate(last_codes, 1):
            src = "".join(c.get("source", []))
            outputs = c.get("outputs", [])
            out_texts = []
            for o in outputs:
                if "text" in o:
                    out_texts.append("".join(o["text"]) if isinstance(o["text"], list) else o["text"])
                elif "data" in o and "text/plain" in o["data"]:
                    out_texts.append("".join(o["data"]["text/plain"]) if isinstance(o["data"]["text/plain"], list) else o["data"]["text/plain"])
            out_combined = "\n".join(out_texts)[:2000]
            parts.append(f"\n### code cell (last-{len(last_codes)-i+1})\n\n```python\n{src}\n```\n")
            if out_combined:
                parts.append(f"\n출력:\n```\n{redact_secrets(out_combined)}\n```\n")

        out_file = traces / f"notebook_{_safe_name(nb_path.stem)}.md"
        out_file.write_text(redact_secrets("\n".join(parts)), encoding="utf-8")
        count += 1

    print(f"  ✅ notebook_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 3. .py 모듈 폴더 inventory
# ────────────────────────────────────────────────

def import_code_modules(root: Path, traces: Path) -> int:
    # 후보: src/, lib/, scripts/ (사용자), 그리고 .py 파일 5개 이상 있는 폴더
    py_dirs: dict[Path, list[Path]] = {}
    for p in root.rglob("*.py"):
        if any(d in p.parts for d in SECRET_DIRS):
            continue
        if any(d in p.parts for d in {"scripts", "hooks", "tests", "prompts"}):
            # v2.7 install 한 폴더는 skip
            continue
        py_dirs.setdefault(p.parent, []).append(p)

    # 5+ .py 가 있는 폴더만 (또는 메인 폴더)
    significant = {d: files for d, files in py_dirs.items() if len(files) >= 5}
    # root 직속도 추가 (5 미만이라도)
    if root in py_dirs and root not in significant:
        significant[root] = py_dirs[root]

    if not significant:
        print("  ℹ️  주요 .py 모듈 폴더 없음 — skip")
        return 0

    count = 0
    for d, files in significant.items():
        rel = d.relative_to(root) if d != root else Path(".")
        parts = [
            f"---\nsource: {rel}/\ntype: code_module_inventory\nmodule_count: {len(files)}\n---\n",
            f"# code_inventory — {rel}\n",
            "\n| 파일 | LOC | 첫 docstring/주석 |\n|---|---|---|",
        ]
        for f in sorted(files):
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                loc = len(lines)
                # 첫 docstring 또는 첫 # 주석
                doc = ""
                for line in lines[:30]:
                    s = line.strip()
                    if s.startswith('"""') or s.startswith("'''"):
                        doc = s.strip('"\'').strip()[:80]
                        break
                    if s.startswith("#") and not s.startswith("#!") and len(s) > 5:
                        doc = s.lstrip("# ").strip()[:80]
                        break
                doc = doc.replace("|", "\\|")
                parts.append(f"\n| `{f.name}` | {loc} | {doc} |")
            except Exception:
                parts.append(f"\n| `{f.name}` | (읽기 실패) | — |")

        safe = _safe_name(str(rel)) or "root"
        out_file = traces / f"code_{safe}.md"
        out_file.write_text("\n".join(parts), encoding="utf-8")
        count += 1

    print(f"  ✅ code_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 4. .hwp / .hwpx PrvText 추출
# ────────────────────────────────────────────────

def import_hwp_docs(root: Path, traces: Path) -> int:
    # rhwp(Node 브리지) 사전 체크 — .hwp/.hwpx 모두 rhwp로 처리
    if not shutil.which("node"):
        print("  ⚠️  node 미설치 — hwp skip (rhwp는 Node 런타임 필요)")
        return 0
    if not _find_hwp_bridge():
        print("  ⚠️  hooks/hwp_extract.mjs 미발견 — hwp skip")
        return 0

    # final / 최종 / 사용설명서 / v\d+ 우선
    priority = re.compile(r"(final|최종|매뉴얼|메뉴얼|설명서|가이드|v\d+)", re.IGNORECASE)
    candidates = []
    for ext in ["*.hwp", "*.hwpx"]:
        for p in root.rglob(ext):
            if any(d in p.parts for d in SECRET_DIRS):
                continue
            candidates.append(p)

    if not candidates:
        print("  ℹ️  hwp 없음 — skip")
        return 0

    # priority 우선, 그 외 max 5
    high = [c for c in candidates if priority.search(c.name)]
    low = [c for c in candidates if not priority.search(c.name)]
    targets = (high + low)[:5]

    count = 0
    for p in targets:
        # rhwp 단일 경로 — .hwp(바이너리) + .hwpx 모두 전체 본문 추출
        text, method = _extract_hwp_rhwp(p)

        parts = [
            f"---\nsource: {p.relative_to(root)}\ntype: hwp_extract\nextracted_via: {method}\n---\n",
            f"# {p.suffix.lstrip('.')} — {p.stem}\n",
            f"\n경로: `{p.relative_to(root)}`\n",
            f"\n## 추출 텍스트 ({method})\n\n{redact_secrets(text)}\n",
        ]
        out_file = traces / f"hwp_{_safe_name(p.stem)}.md"
        out_file.write_text("\n".join(parts), encoding="utf-8")
        count += 1

    print(f"  ✅ hwp_*.md × {count}")
    return count


def _find_hwp_bridge() -> Path | None:
    """hwp_extract.mjs(rhwp Node 브리지) 경로 탐색."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "hooks" / "hwp_extract.mjs",   # scripts/ → ../hooks/
        Path("hooks") / "hwp_extract.mjs",             # cwd 기준
        here / "hwp_extract.mjs",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _extract_hwp_rhwp(p: Path) -> tuple[str, str]:
    """rhwp(@rhwp/core WASM, Node 브리지)로 .hwp/.hwpx 전체 본문 추출.

    .hwp(바이너리)와 .hwpx 모두 지원 — rhwp 단일 경로.
    Node + hooks/hwp_extract.mjs + hooks/vendor/rhwp/ 필요.
    """
    import subprocess

    bridge = _find_hwp_bridge()
    if not bridge:
        return ("[hwp_extract.mjs 브리지 미발견 — hooks/ 확인]", "none")

    node = shutil.which("node")
    if not node:
        return ("[Node 미설치 — rhwp는 Node 런타임 필요]", "none")

    try:
        result = subprocess.run(
            [node, str(bridge), str(p)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()[:200]
            return (f"[rhwp 추출 실패: {err}]", "error")
        text = result.stdout
        return (text[:20000], "rhwp_wasm")
    except subprocess.TimeoutExpired:
        return ("[rhwp 추출 타임아웃 60s]", "error")
    except Exception as e:
        return (f"[rhwp 추출 예외: {e}]", "error")


# ────────────────────────────────────────────────
# 5. .docx 추출
# ────────────────────────────────────────────────

def import_docx_docs(root: Path, traces: Path) -> int:
    try:
        from docx import Document
    except ImportError:
        print("  ⚠️  python-docx 미설치 — docx skip")
        return 0

    priority = re.compile(r"(final|최종|매뉴얼|메뉴얼|설명서|가이드|v\d+)", re.IGNORECASE)
    candidates = [p for p in root.rglob("*.docx")
                  if not any(d in p.parts for d in SECRET_DIRS)]
    if not candidates:
        print("  ℹ️  docx 없음 — skip")
        return 0

    high = [c for c in candidates if priority.search(c.name)]
    low = [c for c in candidates if not priority.search(c.name)]
    targets = (high + low)[:5]

    count = 0
    for p in targets:
        try:
            doc = Document(str(p))
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()][:200]
            text = "\n".join(paragraphs)[:8000]
        except Exception as e:
            text = f"[추출 실패: {e}]"

        parts = [
            f"---\nsource: {p.relative_to(root)}\ntype: docx_extract\nextracted_via: python-docx\n---\n",
            f"# docx — {p.stem}\n",
            f"\n경로: `{p.relative_to(root)}`\n",
            f"\n## 본문 (최대 8000 chars)\n\n{redact_secrets(text)}\n",
        ]
        out_file = traces / f"docx_{_safe_name(p.stem)}.md"
        out_file.write_text("\n".join(parts), encoding="utf-8")
        count += 1

    print(f"  ✅ docx_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 5b. .pdf 추출 (2026-06-12 추가 — 강의자료/보고서 PDF, pypdf 텍스트 레이어)
# ────────────────────────────────────────────────

def import_pdf_docs(root: Path, traces: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("  ⚠️  pypdf 미설치 — pdf skip")
        return 0

    priority = re.compile(r"(final|최종|매뉴얼|설명서|가이드|보고서|강의|v\d+)", re.IGNORECASE)
    candidates = [p for p in root.rglob("*.pdf")
                  if not any(d in p.parts for d in SECRET_DIRS)]
    if not candidates:
        print("  ℹ️  pdf 없음 — skip")
        return 0

    high = [c for c in candidates if priority.search(c.name)]
    low = [c for c in candidates if not priority.search(c.name)]
    targets = (high + low)[:8]

    count = 0
    for p in targets:
        try:
            r = PdfReader(str(p))
            pages = len(r.pages)
            chunks = []
            for pg in r.pages[:30]:               # 최대 30페이지
                t = (pg.extract_text() or "").strip()
                if t:
                    chunks.append(t)
                if sum(len(c) for c in chunks) > 12000:
                    break
            text = "\n\n".join(chunks)[:12000]
            if not text.strip():
                text = "[텍스트 레이어 없음 — 스캔본 추정. 필요 시 PyMuPDF 렌더→Claude 비전으로 판독]"
        except Exception as e:
            pages = "?"
            text = f"[추출 실패: {e}]"

        parts = [
            f"---\nsource: {p.relative_to(root)}\ntype: pdf_extract\nextracted_via: pypdf\npages: {pages}\n---\n",
            f"# pdf — {p.stem}\n",
            f"\n경로: `{p.relative_to(root)}` · 페이지: {pages}\n",
            f"\n## 본문 텍스트 레이어 (최대 30p/12000 chars)\n\n{redact_secrets(text)}\n",
        ]
        out_file = traces / f"pdf_{_safe_name(p.stem)}.md"
        out_file.write_text("\n".join(parts), encoding="utf-8")
        count += 1

    print(f"  ✅ pdf_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 5c. .pptx 추출 (2026-06-12 추가 — zipfile+XML, 추가 의존성 없음)
# ────────────────────────────────────────────────

def import_pptx_docs(root: Path, traces: Path) -> int:
    import zipfile
    from xml.etree import ElementTree as ET

    priority = re.compile(r"(final|최종|강의|수업|발표|v\d+)", re.IGNORECASE)
    candidates = [p for p in root.rglob("*.pptx")
                  if not any(d in p.parts for d in SECRET_DIRS)
                  and not p.name.startswith("~$")]
    if not candidates:
        print("  ℹ️  pptx 없음 — skip")
        return 0

    high = [c for c in candidates if priority.search(c.name)]
    low = [c for c in candidates if not priority.search(c.name)]
    targets = (high + low)[:8]
    NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

    count = 0
    for p in targets:
        slides_out = []
        try:
            with zipfile.ZipFile(p) as z:
                slide_names = sorted(
                    [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                    key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))
                for n in slide_names[:60]:        # 최대 60슬라이드
                    try:
                        xml_root = ET.fromstring(z.read(n))
                        texts = [t.text for t in xml_root.iter(f"{NS}t") if t.text and t.text.strip()]
                        if texts:
                            num = re.search(r"slide(\d+)", n).group(1)
                            slides_out.append(f"### slide {num}\n" + "\n".join(texts))
                    except Exception:
                        continue
            text = "\n\n".join(slides_out)[:15000] or "[텍스트 없음 — 이미지 위주 슬라이드]"
            n_slides = len(slide_names)
        except Exception as e:
            text = f"[추출 실패: {e}]"
            n_slides = "?"

        parts = [
            f"---\nsource: {p.relative_to(root)}\ntype: pptx_extract\nextracted_via: zipfile+xml\nslides: {n_slides}\n---\n",
            f"# pptx — {p.stem}\n",
            f"\n경로: `{p.relative_to(root)}` · 슬라이드: {n_slides}\n",
            f"\n## 슬라이드 텍스트 (최대 60장/15000 chars)\n\n{redact_secrets(text)}\n",
        ]
        out_file = traces / f"pptx_{_safe_name(p.stem)}.md"
        out_file.write_text("\n".join(parts), encoding="utf-8")
        count += 1

    print(f"  ✅ pptx_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 6. 파라미터 sweep 흔적 (compare_*.py, nl_parameter_test/ 등)
# ────────────────────────────────────────────────

def import_param_sweep(root: Path, traces: Path) -> bool:
    sweep_files = []
    sweep_dirs = []

    # compare_*.py 패턴
    for p in root.rglob("compare_*.py"):
        if any(d in p.parts for d in SECRET_DIRS):
            continue
        sweep_files.append(p)

    # *parameter*, *sweep*, *experiment* 폴더
    for d in root.rglob("*"):
        if not d.is_dir():
            continue
        if any(p in d.parts for p in SECRET_DIRS):
            continue
        name = d.name.lower()
        if any(kw in name for kw in ["parameter_test", "param_test", "sweep", "experiment", "exp_"]):
            sweep_dirs.append(d)

    if not sweep_files and not sweep_dirs:
        print("  ℹ️  sweep 흔적 없음 — skip")
        return False

    parts = [
        f"---\ntype: param_sweep_inventory\n---\n",
        f"# param_sweep — 파라미터 비교 / sweep 흔적\n",
    ]

    if sweep_files:
        parts.append("\n## 비교 스크립트 (compare_*.py)\n\n| 파일 | LOC | 위치 |\n|---|---|---|")
        for f in sorted(sweep_files):
            try:
                loc = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                loc = "?"
            parts.append(f"\n| `{f.name}` | {loc} | `{f.relative_to(root).parent}/` |")

    if sweep_dirs:
        parts.append("\n\n## sweep 폴더\n\n| 폴더 | 내부 파일 수 | 위치 |\n|---|---|---|")
        for d in sorted(sweep_dirs):
            try:
                file_count = sum(1 for _ in d.iterdir() if _.is_file())
            except Exception:
                file_count = "?"
            parts.append(f"\n| `{d.name}/` | {file_count} | `{d.relative_to(root).parent}/` |")

    out = traces / "param_sweep.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  ✅ param_sweep.md ({len(sweep_files)} compare 스크립트, {len(sweep_dirs)} sweep 폴더)")
    return True


# ────────────────────────────────────────────────
# 7. 모델 weights inventory (binary 안 dump)
# ────────────────────────────────────────────────

def import_model_inventory(root: Path, traces: Path) -> bool:
    model_exts = ["*.h5", "*.pkl", "*.pt", "*.pth", "*.ckpt", "*.onnx", "*.pb", "*.tflite", "*.weights"]
    models = []
    for ext in model_exts:
        for p in root.rglob(ext):
            if any(d in p.parts for d in SECRET_DIRS):
                continue
            try:
                size_mb = p.stat().st_size / (1024 * 1024)
            except Exception:
                size_mb = 0
            models.append((p, size_mb))

    if not models:
        print("  ℹ️  모델 weights 없음 — skip")
        return False

    parts = [
        f"---\ntype: model_inventory\ncount: {len(models)}\n---\n",
        f"# models — 학습된 모델 weights inventory\n\n(content 안 dump — 파일 메타데이터만)\n",
        "\n| 파일 | 크기 (MB) | 위치 |\n|---|---|---|",
    ]
    for p, size in sorted(models, key=lambda x: -x[1])[:30]:
        parts.append(f"\n| `{p.name}` | {size:.2f} | `{p.relative_to(root).parent}/` |")

    out = traces / "models.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  ✅ models.md ({len(models)} 모델)")
    return True


# ────────────────────────────────────────────────
# 7b. *.md 분석 보고서 / 노트 추출 (CLAUDE*.md 제외)
# ────────────────────────────────────────────────

def import_md_notes(root: Path, traces: Path, max_count: int = 20) -> int:
    notes = []
    for p in root.rglob("*.md"):
        if any(d in p.parts for d in SECRET_DIRS):
            continue
        # CLAUDE 헌법은 legacy_constitution 으로 별도 처리됨
        if p.name.startswith("CLAUDE") or p.name == "MEMORY.md":
            continue
        # v2.7.3 자체 메모리/agents 는 제외
        if ".claude" in p.parts:
            continue
        notes.append(p)

    if not notes:
        print("  ℹ️  *.md 노트 없음 — skip")
        return 0

    count = 0
    for p in notes[:max_count]:
        try:
            text = p.read_text(encoding="utf-8")[:10000]
        except Exception:
            continue
        rel = p.relative_to(root)
        # 파일명 충돌 방지: 부모 폴더 + stem
        safe = _safe_name(f"{p.parent.name}_{p.stem}")
        out = traces / f"notes_{safe}.md"
        out.write_text(
            f"---\nsource: {rel}\ntype: user_notes\n---\n\n"
            f"# {p.stem}\n\n경로: `{rel}`\n\n"
            f"{redact_secrets(text)}\n",
            encoding="utf-8"
        )
        count += 1

    print(f"  ✅ notes_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 7c. *.json 결과 파일 (evaluation/ranking/results/metrics)
# ────────────────────────────────────────────────

def import_json_results(root: Path, traces: Path, max_count: int = 15) -> int:
    pattern = re.compile(r"(evaluation|ranking|result|metric|score|stat|sweep|benchmark)",
                         re.IGNORECASE)
    results = []
    for p in root.rglob("*.json"):
        if any(d in p.parts for d in SECRET_DIRS):
            continue
        if ".claude" in p.parts:
            continue
        if pattern.search(p.name):
            results.append(p)

    if not results:
        print("  ℹ️  결과 .json 없음 — skip")
        return 0

    count = 0
    for p in results[:max_count]:
        try:
            content = p.read_text(encoding="utf-8")[:8000]
        except Exception:
            continue
        rel = p.relative_to(root)
        safe = _safe_name(f"{p.parent.name}_{p.stem}")
        out = traces / f"results_{safe}.md"
        out.write_text(
            f"---\nsource: {rel}\ntype: result_json\n---\n\n"
            f"# {p.stem}\n\n경로: `{rel}`\n\n"
            f"```json\n{content}\n```\n",
            encoding="utf-8"
        )
        count += 1

    print(f"  ✅ results_*.md × {count}")
    return count


# ────────────────────────────────────────────────
# 7d. 파일명 패턴에서 파라미터 grid 자동 추출
#     (예: Namhan_20200404_iw1_t10_h1.tif → {iw:1, t:10, h:1})
# ────────────────────────────────────────────────

def detect_param_grid(root: Path, traces: Path) -> bool:
    # _<param_name>(short letters)<digits> 패턴 (한 파일 stem 안에 2개 이상)
    param_pat = re.compile(r"_([a-zA-Z]{1,5})(\d+(?:\.\d+)?)")

    grids: dict[str, dict[tuple, list[str]]] = {}

    for ext in ["*.tif", "*.png", "*.npy", "*.h5", "*.npz"]:
        for p in root.rglob(ext):
            if any(d in p.parts for d in SECRET_DIRS):
                continue
            if ".claude" in p.parts:
                continue
            if p.suffix == ".xml" or p.name.endswith(".aux.xml"):
                continue
            matches = param_pat.findall(p.stem)
            if len(matches) >= 2:
                # 정렬된 (param,value) 튜플을 key 로
                key = tuple(sorted(matches))
                base = str(p.parent.relative_to(root)) if p.parent != root else "."
                grids.setdefault(base, {}).setdefault(key, []).append(p.name)

    # 의미 있는 grid 만 (조합 ≥ 2)
    grids = {b: c for b, c in grids.items() if len(c) >= 2}
    if not grids:
        print("  ℹ️  파일명 grid 패턴 없음 — skip")
        return False

    parts = ["---\ntype: param_grid_auto_detected\n---\n",
             "# param_grid — 파일명 패턴에서 자동 추출한 파라미터 sweep grid\n",
             "\n> 예: `Namhan_..._t10_h1.tif` → {t: 10, h: 1}. "
             "여러 파일에 같은 파라미터 이름이 반복되면 grid 로 인식.\n"]

    for base, combinations in sorted(grids.items()):
        total_files = sum(len(f) for f in combinations.values())
        parts.append(f"\n## `{base}/` ({len(combinations)} 조합, {total_files} 파일)\n")

        # 파라미터별 값 범위
        param_values: dict[str, set] = {}
        for key in combinations:
            for p_name, v in key:
                param_values.setdefault(p_name, set()).add(v)

        parts.append("\n### 파라미터 범위\n")
        for n in sorted(param_values):
            vals_sorted = sorted(param_values[n], key=lambda x: float(x))
            parts.append(f"- `{n}`: {vals_sorted}")

        parts.append("\n### 조합 (최대 30)\n")
        for key, files in sorted(combinations.items())[:30]:
            param_str = ", ".join(f"{n}={v}" for n, v in key)
            example = files[0]
            extra = f" (+{len(files) - 1} 파일)" if len(files) > 1 else ""
            parts.append(f"- {param_str} → `{example}`{extra}")

    out = traces / "param_grid.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  ✅ param_grid.md ({len(grids)} 폴더, {sum(len(c) for c in grids.values())} 조합)")
    return True


# ────────────────────────────────────────────────
# 8. domain-facts.md / decisions.md / codebase-map.md stub
# ────────────────────────────────────────────────

def write_memory_stubs(root: Path, memory: Path, has_legacy: bool, has_models: bool, has_sweep: bool):
    # decisions.md — memory_sync 패턴: '## YYYY-MM-DD ' 시작 필수
    dec = memory / "decisions.md"
    dec_content = f"""# 🎯 최근 결정사항

## {_today()} — Legacy memory 자동 import (v2.7.3)

**결정**: `import_legacy_memory.py` 로 레거시 작업 흔적을 `.claude/memory/traces/` 에 raw extract.

**자동 추출 결과**:
- legacy_constitution: {'✅' if has_legacy else '❌'}
- model weights inventory: {'✅' if has_models else '❌'}
- param sweep 흔적: {'✅' if has_sweep else '❌'}

**이유**: 사용자 요청 — "기존 작업 보존, 새 v2.7.3 하네스가 참고".

**한계**: raw extract only (LLM 해석 없음, hallucination 없음). 사용자 검토 후 핵심만 본 파일에 누적.

## {_today()} — v2.7.3 install 완료

**결정**: install.sh + bootstrap 으로 v2.7.3 하네스 install. 사용자 자산 (CLAUDE_*.md, .claude/skills/, .claude/agents/) 보존, 새 c-/x- 18 페어 추가.

---

## 사용자 검토 후 추가될 후보

- [ ] 사용자 본인 실측 metric 값
- [ ] 모델 비교 결과 (어느 모델이 최종 채택?)
- [ ] 파라미터 sweep 결과 (어느 값이 최적?)
- [ ] 레거시 헌법의 도메인 specific 규칙을 v2.7.3 어떻게 통합할지
"""
    if dec.exists() and dec.stat().st_size > 100:
        # 이미 내용 있으면 append
        dec.write_text(dec.read_text(encoding="utf-8") + "\n\n" + dec_content, encoding="utf-8")
    else:
        dec.write_text(dec_content, encoding="utf-8")

    # domain-facts.md — 사용자 헌법의 markdown bullet/표/section 적극 추출
    df = memory / "domain-facts.md"
    facts_lines = ["# 📚 확정된 도메인 사실\n",
                   "> import_legacy_memory.py 자동 추출. 사용자 검토 후 정련 권장.\n"]

    # 후보: 활성 CLAUDE.md 가 아닌 모든 CLAUDE_*.md
    legacy_candidates = []
    for cand in ["CLAUDE_old.md", "CLAUDE_new.md"]:
        cp = root / cand
        if cp.exists():
            legacy_candidates.append(cp)
    for cp in root.glob("CLAUDE_*.md"):
        if cp not in legacy_candidates and cp.name != "CLAUDE.md":
            legacy_candidates.append(cp)

    # 추출 대상 섹션 키워드
    target_section_kws = [
        "프로젝트 개요", "핵심 코드", "에이전트 레지스트리", "핵심 규칙",
        "기술 스택", "지원 센서", "디스패치", "워크플로우",
        "프로젝트 정의", "데이터", "도메인", "정량 평가", "metric",
    ]
    bullet_pattern = re.compile(r"^\s*[-*]\s+\*\*([^*]+)\*\*\s*[:：]\s*(.+)$")
    table_pattern = re.compile(r"^\s*\|.+\|\s*$")

    for legacy_md in legacy_candidates[:2]:  # 최대 2개
        try:
            text = legacy_md.read_text(encoding="utf-8")
        except Exception:
            continue

        facts_lines.append(f"\n## 출처: `{legacy_md.name}`\n")

        in_target_section = False
        section_buffer = []
        for line in text.splitlines():
            stripped = line.strip()

            # 헤딩 감지
            if stripped.startswith("##"):
                if in_target_section and section_buffer:
                    facts_lines.append("\n".join(section_buffer).rstrip())
                    section_buffer = []
                heading_text = stripped.lstrip("#").strip()
                in_target_section = any(kw in heading_text for kw in target_section_kws)
                if in_target_section:
                    facts_lines.append(f"\n### {heading_text}\n")
                continue

            # bullet 추출 (모든 섹션에서, **key**: value 형태)
            m = bullet_pattern.match(line)
            if m:
                facts_lines.append(f"- **{m.group(1).strip()}**: {m.group(2).strip()}")
                continue

            # 타겟 섹션 안에서는 markdown 표 라인도 보존
            if in_target_section and table_pattern.match(line):
                section_buffer.append(line.rstrip())
                continue

            # 타겟 섹션 안에서는 일반 bullet 도 보존
            if in_target_section and stripped.startswith(("-", "*", "1.", "2.")):
                section_buffer.append(line.rstrip())

        if in_target_section and section_buffer:
            facts_lines.append("\n".join(section_buffer).rstrip())

    # 도메인 specific 정보가 헌법 외부 (hwp/docx 사용설명서) 에 있을 수 있음
    # traces/{hwp,docx}_*.md 의 본문 첫 500 chars 를 stub 으로 inject
    domain_doc_stubs = []
    traces_dir = memory / "traces"
    if traces_dir.exists():
        for trace in sorted(traces_dir.glob("*_*.md")):
            if not trace.name.startswith(("hwp_", "docx_")):
                continue
            try:
                t_content = trace.read_text(encoding="utf-8")
                # frontmatter 이후 본문에서 첫 500 chars
                body_start = t_content.find("\n## ")
                if body_start > 0:
                    body = t_content[body_start:body_start+1500]
                    # 첫 200 chars 만 (요약용)
                    excerpt = body.replace("\n", " ").strip()[:300]
                    domain_doc_stubs.append((trace.name, excerpt))
            except Exception:
                continue

    if domain_doc_stubs:
        facts_lines.append("\n## 도메인 문서 추출 stub (사용설명서·매뉴얼)\n")
        facts_lines.append("> 사용자 헌법에 도메인 정보 부족 시 hwp/docx 매뉴얼 첫 부분 자동 inject. 사용자 검토 후 핵심만 유지.\n")
        for name, excerpt in domain_doc_stubs[:3]:
            facts_lines.append(f"\n### `{name}`\n\n{excerpt}\n")

    facts_lines.append("\n## 자동 추출 자료 위치\n")
    facts_lines.append("- `.claude/memory/traces/` — archive (legacy_constitution, notebook, code, hwp/docx, param_sweep, models)")
    facts_lines.append("- `.claude/memory/experiments_table.md` — 한눈에 보기")
    facts_lines.append("- `.claude/memory/decisions.md` — 결정사항 (자동 주입 대상)")

    df.write_text("\n".join(facts_lines), encoding="utf-8")

    # experiments_table.md (자동 stub)
    et = memory / "experiments_table.md"
    et.write_text(f"""# 실험 매트릭스 (자동 stub)

> {Path(__file__).name} 자동 생성. 사용자 작업 진행하면서 실측값으로 채움.

## 파일 inventory

| 종류 | 위치 |
|---|---|
| traces (raw archive) | `.claude/memory/traces/` |
| 모델 weights | `.claude/memory/traces/models.md` |
| 비교 스크립트 | `.claude/memory/traces/param_sweep.md` |
| 노트북 추출 | `.claude/memory/traces/notebook_*.md` |
| 코드 inventory | `.claude/memory/traces/code_*.md` |
| 한국어 문서 | `.claude/memory/traces/{{hwp,docx}}_*.md` |

## 사용자 검토 후 채울 항목

| Metric | 목표 | 실측 | 출처 |
|---|---|---|---|
| (확인 필요) | (확인 필요) | ❓ | (확인 필요) |
""", encoding="utf-8")

    print(f"  ✅ memory stub 3 (decisions.md, domain-facts.md, experiments_table.md)")


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="프로젝트 루트 (default: cwd)")
    ap.add_argument("--max-ipynb", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"❌ 대상 폴더 없음: {root}")
        sys.exit(1)

    traces = root / ".claude" / "memory" / "traces"
    memory = root / ".claude" / "memory"

    if args.dry_run:
        print(f"🔍 (dry-run) 대상: {root}")
        print(f"  traces 위치: {traces}")
        sys.exit(0)

    traces.mkdir(parents=True, exist_ok=True)
    memory.mkdir(parents=True, exist_ok=True)

    print(f"━━━ Legacy memory import — {root.name} ━━━\n")
    print("[1/8] CLAUDE*.md (사용자 본인 헌법) ...")
    has_legacy = import_legacy_constitution(root, traces)
    print("[2/8] .ipynb (notebook 추출) ...")
    nb_count = import_notebooks(root, traces, max_count=args.max_ipynb)
    print("[3/8] .py 모듈 inventory ...")
    code_count = import_code_modules(root, traces)
    print("[4/8] .hwp/.hwpx (한글 문서) ...")
    hwp_count = import_hwp_docs(root, traces)
    print("[5/8] .docx (Word 문서) ...")
    docx_count = import_docx_docs(root, traces)
    print("[5b] .pdf (텍스트 레이어) ...")
    pdf_count = import_pdf_docs(root, traces)
    print("[5c] .pptx (슬라이드 텍스트) ...")
    pptx_count = import_pptx_docs(root, traces)
    print("[6/11] 파라미터 sweep 흔적 (compare_*.py + 폴더명) ...")
    has_sweep = import_param_sweep(root, traces)
    print("[7/11] 모델 weights inventory ...")
    has_models = import_model_inventory(root, traces)
    print("[8/11] *.md 분석 보고서/노트 ...")
    md_count = import_md_notes(root, traces)
    print("[9/11] *.json 결과 파일 (evaluation/ranking/metrics) ...")
    json_count = import_json_results(root, traces)
    print("[10/11] 파일명 grid 패턴 (NL-Means t/h sweep 등) ...")
    has_grid = detect_param_grid(root, traces)
    print("[11/11] memory stubs (decisions/domain-facts/experiments_table) ...")
    write_memory_stubs(root, memory, has_legacy, has_models, has_sweep)

    # bundle 재생성
    sync = root / "scripts" / "memory_sync.py"
    if sync.exists():
        import subprocess
        try:
            subprocess.run([sys.executable, str(sync), "bundle"],
                          cwd=root, timeout=30, check=False, capture_output=True)
            print("\n  ✅ memory_sync.py bundle 재생성")
        except Exception as e:
            print(f"\n  ⚠️  bundle 재생성 실패: {e}")

    print(f"\n━━━ 완료 ━━━")
    print(f"  traces/ : legacy={int(has_legacy)} / notebook={nb_count} / "
          f"code={code_count} / hwp={hwp_count} / docx={docx_count} / "
          f"pdf={pdf_count} / pptx={pptx_count} / "
          f"sweep={int(has_sweep)} / models={int(has_models)} / "
          f"notes={md_count} / json_results={json_count} / grid={int(has_grid)}")
    print(f"  위치: {traces.relative_to(root)}/")


if __name__ == "__main__":
    main()
