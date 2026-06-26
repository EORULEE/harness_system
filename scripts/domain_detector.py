#!/usr/bin/env python3
"""domain_detector.py — 프로젝트 폴더 스캔하여 도메인 판별용 구조 정보 추출.

목적: Claude 가 도메인을 추론할 수 있도록 객관적 정보 제공.
  - import 문 빈도
  - 설정 파일 (requirements.txt, package.json 등)
  - 파일 구조·확장자 분포
  - README 발췌
  - 키워드 빈도

사용:
  python scripts/domain_detector.py <project_root> [--output <path>]
  
출력: JSON (기본: stdout, --output 지정 시 파일로)

설계 원칙:
  - 구조적 정보만 수집 (의미 해석은 Claude 가 담당)
  - 대용량 파일·바이너리 스킵
  - .claude/, node_modules/, .git/ 등 제외
  - 결정적 동작 (재실행 시 동일 결과)
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────────

# 제외할 디렉토리
EXCLUDE_DIRS = {
    ".claude", ".git", ".svn", ".hg",
    "node_modules", "vendor", "__pycache__",
    "dist", "build", "target", ".next",
    ".venv", "venv", ".env", "env",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode",
}

# 제외할 파일 패턴 (v2.6+: PDF/DOCX/HWP 는 document scanner 가 처리하므로 제외 목록에서 빼냄)
EXCLUDE_FILE_PATTERNS = [
    r".*\.pyc$", r".*\.pyo$", r".*\.so$", r".*\.dylib$", r".*\.dll$",
    r".*\.jpg$", r".*\.jpeg$", r".*\.png$", r".*\.gif$", r".*\.ico$",
    r".*\.mp4$", r".*\.avi$", r".*\.mov$", r".*\.mp3$", r".*\.wav$",
    r".*\.zip$", r".*\.tar$", r".*\.gz$", r".*\.bz2$",
    r".*\.xlsx$",
    r".*\.log$",
]

# 텍스트 파일 최대 크기 (500 KB)
MAX_FILE_SIZE = 500 * 1024

# v2.6+: 도메인 시그널이 풍부한 문서 형식
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".hwp", ".hwpx", ".ipynb"}
MAX_DOC_FILES = 20            # 너무 많으면 느림 (특히 PDF)
MAX_DOC_TEXT_PER_FILE = 5000  # 파일당 추출 글자 수 상한
MAX_DOC_FILE_SIZE = 20 * 1024 * 1024  # 20MB 초과 문서는 스킵 (대용량 보고서 방어)

# import 추출 정규식
IMPORT_PATTERNS = {
    "python": [
        re.compile(r"^\s*import\s+([a-zA-Z_][\w.]*)", re.MULTILINE),
        re.compile(r"^\s*from\s+([a-zA-Z_][\w.]*)\s+import", re.MULTILINE),
    ],
    "javascript": [
        re.compile(r"""^\s*import\s+.*?from\s+['"]([^'"]+)['"]""", re.MULTILINE),
        re.compile(r"""require\(['"]([^'"]+)['"]\)"""),
    ],
    "rust": [
        re.compile(r"^\s*use\s+([a-zA-Z_][\w:]*)", re.MULTILINE),
    ],
    "go": [
        re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE),
    ],
}

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "javascript", ".tsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}

# 설정 파일 목록
CONFIG_FILES = [
    "package.json", "requirements.txt", "requirements.in",
    "Pipfile", "pyproject.toml", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod",
    "composer.json", "Gemfile", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example",
]

# README 파일 후보
README_CANDIDATES = ["README.md", "README.rst", "README.txt", "README", "readme.md"]

# ──────────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────────

def _is_excluded_dir(path: Path) -> bool:
    """제외 디렉토리인지."""
    return path.name in EXCLUDE_DIRS or path.name.startswith(".")


# v2.6.1: 하네스가 install 한 루트 디렉토리 자동 인식 → self-exclusion
# 사용자 본인의 src/scripts/ 같은 코드는 보존, 루트 직속 하네스 디렉토리만 제외
_HARNESS_DIR_MARKERS = {
    "scripts": "harness_common.py",
    "hooks":   "harness-hook-lib.mjs",
    "tests":   "test_concurrency.py",
    "prompts": "compress_trace.md",
}


def _is_root_harness_dir(path: Path, root: Path) -> bool:
    """`path` 가 root 직속의 하네스 관리 디렉토리인지 (마커 파일 존재로 판별).

    예: <project>/scripts/harness_common.py 가 있으면 <project>/scripts 는 제외.
    그러나 <project>/src/scripts/ 같은 사용자 코드는 그대로 스캔됨.
    """
    if not path.is_dir():
        return False
    if path.name not in _HARNESS_DIR_MARKERS:
        return False
    # root 직속만 (parent 가 root 와 같아야 함). 경로 정규화로 비교.
    try:
        if path.parent.resolve() != root.resolve():
            return False
    except OSError:
        return False
    marker = _HARNESS_DIR_MARKERS[path.name]
    return (path / marker).exists()


# v2.6.2: 하네스가 install 시 root 에 떨어뜨리는 CLAUDE.md (헌법) 자동 감지.
# 사용자 본인의 CLAUDE.md (일반적으로 작고 프로젝트 가이드) 는 보존.
_HARNESS_CONSTITUTION_SIGNATURES = (
    "하네스 헌법", "Memory v2", "Circuit Breaker v2", "Campaign v2",
    "Instincts v2", "PAIR-LEAD", "PAIR-DEV", "Discovery Relay",
    "harness-v2", "🛡 응답 규율", "A1 2-pass",
)
_HARNESS_CONSTITUTION_MIN_BYTES = 50_000  # user CLAUDE.md 는 보통 <10KB


def _is_harness_constitution(path: Path, root: Path) -> bool:
    """root/CLAUDE.md 가 하네스 헌법인지 휴리스틱 검사.

    조건 (모두 충족):
      1. 파일명이 CLAUDE.md (case-insensitive)
      2. root 직속 (사용자가 src/CLAUDE.md 같은 자기 거 두는 건 보존)
      3. 50KB 이상 (사용자 본인 CLAUDE.md 는 보통 작음)
      4. 첫 5KB 안에 하네스 시그니처 2개 이상 포함
    """
    if path.name.lower() != "claude.md":
        return False
    try:
        if path.parent.resolve() != root.resolve():
            return False
        if path.stat().st_size < _HARNESS_CONSTITUTION_MIN_BYTES:
            return False
        sample = path.read_text(encoding="utf-8", errors="ignore")[:5000]
    except (OSError, UnicodeDecodeError):
        return False
    hits = sum(1 for sig in _HARNESS_CONSTITUTION_SIGNATURES if sig in sample)
    return hits >= 2


def _is_excluded_file(path: Path) -> bool:
    """제외 파일 패턴 매치."""
    name = path.name.lower()
    return any(re.match(pat, name, re.IGNORECASE) for pat in EXCLUDE_FILE_PATTERNS)


def _read_text_safe(path: Path) -> str | None:
    """파일 안전 읽기 (인코딩·크기 체크)."""
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


# ──────────────────────────────────────────────────────────────────
# 스캐너 함수
# ──────────────────────────────────────────────────────────────────

def scan_file_structure(root: Path) -> dict[str, Any]:
    """파일 구조 · 확장자 분포."""
    ext_counter: Counter[str] = Counter()
    dir_tree: list[str] = []
    total_files = 0
    total_size = 0

    for path in root.rglob("*"):
        # 제외 디렉토리 안에 있으면 스킵
        if any(_is_excluded_dir(p) for p in path.parents):
            continue
        if any(_is_root_harness_dir(p, root) for p in path.parents):
            continue

        if path.is_dir():
            rel = path.relative_to(root)
            depth = len(rel.parts)
            if depth <= 3 and not _is_excluded_dir(path):
                dir_tree.append(str(rel))

        elif path.is_file() and not _is_excluded_file(path):
            ext = path.suffix.lower()
            if ext:
                ext_counter[ext] += 1
            total_files += 1
            try:
                total_size += path.stat().st_size
            except OSError:
                pass

    return {
        "total_files": total_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "extension_counts": dict(ext_counter.most_common(15)),
        "dir_tree_sample": sorted(dir_tree)[:30],
    }


def extract_imports(root: Path) -> dict[str, list[tuple[str, int]]]:
    """언어별 import 빈도 추출."""
    imports_by_lang: dict[str, Counter[str]] = {
        "python": Counter(), "javascript": Counter(),
        "rust": Counter(), "go": Counter(),
    }

    for path in root.rglob("*"):
        if any(_is_excluded_dir(p) for p in path.parents):
            continue
        if any(_is_root_harness_dir(p, root) for p in path.parents):
            continue
        if not path.is_file():
            continue

        lang = LANG_BY_EXT.get(path.suffix.lower())
        if not lang:
            continue

        content = _read_text_safe(path)
        if content is None:
            continue

        for pattern in IMPORT_PATTERNS[lang]:
            for match in pattern.findall(content):
                # 파이썬의 경우 최상위 패키지명만
                if lang == "python" and "." in match:
                    match = match.split(".")[0]
                # JS 상대 경로 스킵
                if lang == "javascript" and match.startswith("."):
                    continue
                # 표준 라이브러리 제외 (간단 필터)
                if match in {"os", "sys", "re", "json", "time", "datetime",
                             "pathlib", "typing", "collections", "functools"}:
                    continue
                imports_by_lang[lang][match] += 1

    return {
        lang: counter.most_common(20)
        for lang, counter in imports_by_lang.items()
        if counter
    }


def read_config_files(root: Path) -> dict[str, str]:
    """설정 파일 원문 읽기 (첫 10KB)."""
    configs: dict[str, str] = {}
    for name in CONFIG_FILES:
        for path in root.glob(name):  # glob 은 루트만
            content = _read_text_safe(path)
            if content is not None:
                configs[name] = content[:10000]
            break
        # 하위 디렉토리에도 있을 수 있음 (monorepo)
        if name not in configs:
            for path in root.rglob(name):
                if any(_is_excluded_dir(p) for p in path.parents):
                    continue
                rel = path.relative_to(root)
                if len(rel.parts) > 3:  # 너무 깊은 곳은 스킵
                    continue
                content = _read_text_safe(path)
                if content is not None:
                    configs[str(rel)] = content[:10000]
    return configs


def read_readme(root: Path) -> dict[str, str]:
    """README 파일 읽기 (첫 5KB)."""
    for name in README_CANDIDATES:
        path = root / name
        if path.exists() and path.is_file():
            content = _read_text_safe(path)
            if content is not None:
                return {"filename": name, "content": content[:5000]}
    return {}


# ──────────────────────────────────────────────────────────────────
# v2.6+: 문서 추출기 (PDF, DOCX, HWPX, HWP, IPYNB)
# ──────────────────────────────────────────────────────────────────
#
# 모든 추출기는 다음 계약을 지킨다:
#   - 의존성 없으면 빈 문자열 반환 (예외 던지지 말 것)
#   - 추출 텍스트는 MAX_DOC_TEXT_PER_FILE 로 trim
#   - 인코딩 오류는 errors="ignore"


def extract_pdf_text(path: Path) -> str:
    """PDF → 텍스트. pypdf 가 있으면 사용, 없으면 빈 문자열.

    의존성: pip install pypdf (선택)
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        # 첫 10페이지만 (도메인 시그널은 보통 abstract/intro 에 있음)
        pages = reader.pages[:10]
        text = "\n".join((p.extract_text() or "") for p in pages)
        return text[:MAX_DOC_TEXT_PER_FILE]
    except Exception:
        return ""


def extract_docx_text(path: Path) -> str:
    """DOCX → 텍스트. python-docx 가 있으면 사용.

    의존성: pip install python-docx (선택)
    """
    try:
        import docx  # type: ignore
    except ImportError:
        return ""
    try:
        document = docx.Document(str(path))
        text = "\n".join(p.text for p in document.paragraphs if p.text)
        return text[:MAX_DOC_TEXT_PER_FILE]
    except Exception:
        return ""


def extract_hwpx_text(path: Path) -> str:
    """HWPX (한글 신버전, XML zip) → 텍스트. 표준 라이브러리만 사용.

    의존성: 없음 (zipfile + xml.etree)
    """
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        chunks: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            # Contents/section*.xml 안에 본문이 있음
            section_names = [
                n for n in zf.namelist()
                if n.startswith("Contents/section") and n.endswith(".xml")
            ]
            for name in section_names[:10]:  # 첫 10 섹션만
                try:
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                    root = ET.fromstring(raw)
                    # 모든 텍스트 노드 수집 (네임스페이스 무시)
                    for elem in root.iter():
                        if elem.text:
                            chunks.append(elem.text)
                except (ET.ParseError, KeyError, UnicodeDecodeError):
                    continue
        text = " ".join(chunks)
        return text[:MAX_DOC_TEXT_PER_FILE]
    except (zipfile.BadZipFile, OSError):
        return ""


def extract_hwp_text(path: Path) -> str:
    """HWP 5.0 (구버전, OLE) → 텍스트.

    우선순위:
      1) olefile + 자체 파싱 (pip install olefile, 선택)
      2) rhwp CLI subprocess (PATH 에 있으면, 선택)
      3) 빈 문자열

    rhwp 통합 (백로그): https://github.com/edwardkim/rhwp
    """
    # 1) olefile 시도
    try:
        import olefile  # type: ignore
        try:
            ole = olefile.OleFileIO(str(path))
            chunks: list[str] = []
            for stream_name in ole.listdir():
                joined = "/".join(stream_name)
                if "BodyText" in joined or "PrvText" in joined:
                    try:
                        raw = ole.openstream(stream_name).read()
                        # PrvText 는 UTF-16-LE 평문, BodyText 는 압축됨
                        if "PrvText" in joined:
                            chunks.append(raw.decode("utf-16-le", errors="ignore"))
                    except (OSError, UnicodeDecodeError):
                        continue
            ole.close()
            text = " ".join(chunks)
            if text.strip():
                return text[:MAX_DOC_TEXT_PER_FILE]
        except Exception:
            pass
    except ImportError:
        pass

    # 2) rhwp CLI 시도
    import shutil
    rhwp_bin = shutil.which("rhwp")
    if rhwp_bin:
        try:
            import subprocess
            result = subprocess.run(
                [rhwp_bin, "dump", str(path)],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="ignore",
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout[:MAX_DOC_TEXT_PER_FILE]
        except (subprocess.TimeoutExpired, OSError):
            pass

    return ""


def extract_ipynb_text(path: Path) -> str:
    """Jupyter notebook → 텍스트. 표준 라이브러리만 사용.

    code 셀의 source + markdown 셀의 source 를 결합. output 은 무시.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        nb = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return ""
    chunks: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") not in ("code", "markdown"):
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        chunks.append(src)
    text = "\n".join(chunks)
    return text[:MAX_DOC_TEXT_PER_FILE]


# 확장자 → 추출기 매핑
DOCUMENT_EXTRACTORS = {
    ".pdf": extract_pdf_text,
    ".docx": extract_docx_text,
    ".hwpx": extract_hwpx_text,
    ".hwp": extract_hwp_text,
    ".ipynb": extract_ipynb_text,
}


def scan_documents(root: Path) -> dict[str, Any]:
    """v2.6+: PDF/DOCX/HWP/HWPX/IPYNB 에서 도메인 시그널 추출.

    Returns:
        {
            "files_scanned": int,
            "files_by_type": {".pdf": 12, ".ipynb": 3, ...},
            "extracted_text_chars": int,
            "samples": [{"path": str, "type": str, "snippet": str}, ...],  # 최대 5개
            "missing_libs": [...],  # 설치 권장 알림
        }
    """
    files_by_type: Counter[str] = Counter()
    samples: list[dict[str, str]] = []
    total_chars = 0
    files_scanned = 0
    missing_libs: set[str] = set()
    aggregated_text_chunks: list[str] = []

    # 후보 파일 수집 (확장자 기준)
    raw_candidates: list[Path] = []
    for path in root.rglob("*"):
        if any(_is_excluded_dir(p) for p in path.parents):
            continue
        if any(_is_root_harness_dir(p, root) for p in path.parents):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in DOCUMENT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_DOC_FILE_SIZE:
                continue
        except OSError:
            continue
        raw_candidates.append(path)

    # v2.6.1: 종류별 균등 분배. 알파벳 정렬은 docx (d) 가 hwp/pdf 를 밀어내는
    # 결함을 만들었었다 — 한중공동연구 폴더 (HWP 164·PDF 148·DOCX 21) 에서
    # docx 만 다 차지하는 문제. 이제 종류별로 동일 quota 할당.
    by_type: dict[str, list[Path]] = {}
    for p in raw_candidates:
        by_type.setdefault(p.suffix.lower(), []).append(p)

    # 각 그룹 내부는 mtime 내림차순 (최신 우선)
    for ext in by_type:
        try:
            by_type[ext].sort(key=lambda p: -p.stat().st_mtime)
        except OSError:
            pass

    n_types = len(by_type)
    if n_types == 0:
        candidates: list[Path] = []
    else:
        per_type = MAX_DOC_FILES // n_types
        remainder = MAX_DOC_FILES - per_type * n_types
        candidates = []
        for i, ext in enumerate(sorted(by_type.keys())):
            take = per_type + (1 if i < remainder else 0)
            candidates.extend(by_type[ext][:take])

    for path in candidates:
        ext = path.suffix.lower()
        extractor = DOCUMENT_EXTRACTORS.get(ext)
        if extractor is None:
            continue

        text = extractor(path)
        if not text:
            # 의존성 누락인지 추정 (실제 import 결과는 추출기 안에서 결정)
            if ext == ".pdf":
                try:
                    import pypdf  # noqa: F401
                except ImportError:
                    missing_libs.add("pypdf")
            elif ext == ".docx":
                try:
                    import docx  # noqa: F401
                except ImportError:
                    missing_libs.add("python-docx")
            elif ext == ".hwp":
                try:
                    import olefile  # noqa: F401
                except ImportError:
                    missing_libs.add("olefile")
            continue

        files_scanned += 1
        files_by_type[ext] += 1
        total_chars += len(text)
        aggregated_text_chunks.append(text)

        if len(samples) < 5:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = path.name
            samples.append({
                "path": rel,
                "type": ext,
                "snippet": text[:300].strip(),
            })

    return {
        "files_scanned": files_scanned,
        "files_by_type": dict(files_by_type),
        "extracted_text_chars": total_chars,
        "samples": samples,
        "missing_libs": sorted(missing_libs),
        "_aggregated_text": "\n".join(aggregated_text_chunks),  # extract_keywords 로 전달
    }


# ──────────────────────────────────────────────────────────────────
# v2.6+: 폴더 경로 기반 도메인 힌트
# ──────────────────────────────────────────────────────────────────

# 폴더명 키워드 → 후보 도메인 (DOMAIN_CATALOG 키와 정렬)
# v2.6.1: 한국어 키워드 추가 — 연구자 폴더에 흔한 한글 디렉토리 인식
PATH_DOMAIN_HINTS = {
    "sar":          ["sar", "insar", "sentinel", "위상", "간섭계"],
    "insar":        ["insar", "psinsar", "sbas"],
    "ai":           ["ai", "ml", "machine-learning", "deep-learning",
                     "pytorch", "tensorflow", "neural", "딥러닝", "머신러닝"],
    "volcanology":  ["volcano", "volc", "eruption", "etna", "kilauea", "화산", "분화"],
    "geodesy":      ["geodesy", "gnss", "gps", "측지"],
    "remote_sensing": ["remote-sensing", "satellite", "earth-observation",
                       "원격탐사", "위성"],
    # v2.6+: 일반 SWE 도메인 후보 (DOMAIN_CATALOG 미등록 — Claude 가 동적 등록 권장)
    "web_app":      ["web", "frontend", "next", "react", "vue", "svelte"],
    "backend_api":  ["backend", "api", "server", "rest", "graphql"],
    "mobile_app":   ["mobile", "ios", "android", "flutter", "react-native"],
    "game":         ["game", "unity", "unreal", "godot"],
    "trading":      ["trading", "binance", "crypto", "trader", "quant", "트레이딩", "퀀트"],
    "data_pipeline": ["etl", "pipeline", "airflow", "dagster", "spark"],
    # v2.6.1: 한국 연구 환경 신규 도메인 후보
    "research_collab": ["한중", "한일", "한미", "공동연구", "joint-research",
                        "international", "협력연구"],
    "earthquake":   ["earthquake", "seismic", "지진", "지진동", "경주지진"],
    "permafrost":   ["permafrost", "tundra", "arctic", "북극", "동토", "영구동토"],
    "korean_research_proposal": ["연구개발계획서", "제안서", "신청양식",
                                  "atbd", "rfp", "산학협력"],
}


def infer_from_path(root: Path) -> list[dict[str, str]]:
    """폴더 경로에 포함된 키워드로 도메인 후보 제시.

    부모 디렉토리 2단계까지 함께 본다 (`crypto/bot/main` → trading 잡힘).

    Returns:
        [{"domain": "trading", "matched": "binance", "via": "folder_name"}, ...]
    """
    parts = list(root.absolute().parts[-3:])  # 마지막 3 단계
    haystack = " ".join(parts).lower().replace("_", "-")

    matches: list[dict[str, str]] = []
    for domain, keywords in PATH_DOMAIN_HINTS.items():
        for kw in keywords:
            if kw in haystack:
                matches.append({
                    "domain": domain,
                    "matched": kw,
                    "via": "folder_name",
                })
                break  # 같은 도메인 중복 방지
    return matches


def extract_keywords(root: Path, top_n: int = 30,
                     extra_text: str = "") -> dict[str, int]:
    """주요 소스 파일에서 도메인 관련 키워드 빈도 추출.

    일반 영어 불용어 + 프로그래밍 공통 단어 제외.
    v2.6+: extra_text (문서 추출 결과 등) 도 함께 카운트.
    """
    STOP_WORDS = {
        # 영어 불용어
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "should",
        "can", "could", "may", "might", "must", "shall", "to", "of", "in",
        "on", "at", "by", "for", "with", "from", "up", "down", "out", "if",
        "then", "else", "when", "where", "why", "how", "what", "which", "who",
        "and", "or", "but", "not", "no", "yes", "this", "that", "these",
        "those", "it", "its", "as", "such", "so", "than", "too", "very",
        "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
        # 프로그래밍 공통
        "def", "class", "return", "import", "from", "self", "none", "true",
        "false", "null", "undefined", "var", "let", "const", "function",
        "new", "delete", "public", "private", "protected", "static", "void",
        "int", "str", "bool", "list", "dict", "set", "tuple", "float", "double",
        "print", "log", "logger", "error", "warning", "info", "debug", "test",
        "tests", "main", "init", "get", "set", "add", "remove", "create",
        "update", "delete", "find", "check", "run", "build", "make", "file",
        "path", "name", "value", "key", "type", "item", "data", "arg", "args",
        "kwarg", "kwargs", "param", "params", "result", "output", "input",
        "config", "conf", "setting", "settings", "option", "options",
    }

    word_pattern = re.compile(r"\b[a-zA-Z][a-zA-Z_]{2,}\b")
    counter: Counter[str] = Counter()
    files_read = 0
    MAX_FILES = 100  # 너무 많이 읽으면 느림

    for path in root.rglob("*"):
        if any(_is_excluded_dir(p) for p in path.parents):
            continue
        if any(_is_root_harness_dir(p, root) for p in path.parents):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in LANG_BY_EXT and path.suffix.lower() not in {".md", ".txt", ".rst"}:
            continue
        # v2.6.2: 하네스 헌법 (CLAUDE.md 139KB) 키워드 노이즈 제거
        if _is_harness_constitution(path, root):
            continue
        if _is_excluded_file(path):
            continue

        content = _read_text_safe(path)
        if content is None:
            continue

        for word in word_pattern.findall(content):
            word_lower = word.lower()
            if word_lower in STOP_WORDS:
                continue
            if len(word_lower) < 4:
                continue
            counter[word_lower] += 1

        files_read += 1
        if files_read >= MAX_FILES:
            break

    # v2.6+: 문서 추출 텍스트도 카운트 (한국어·영어 모두)
    if extra_text:
        # 한국어 + 영어 단어 패턴 (한글 2자 이상도 포함)
        word_pattern_multi = re.compile(r"[\w가-힣]{2,}", re.UNICODE)
        for word in word_pattern_multi.findall(extra_text):
            wl = word.lower()
            if wl in STOP_WORDS:
                continue
            if len(wl) < 2:
                continue
            # 영어 3자 미만은 노이즈, 한글은 2자부터 의미 있음
            if wl.isascii() and len(wl) < 4:
                continue
            counter[wl] += 1

    return dict(counter.most_common(top_n))


# ──────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────

def scan_project(root: Path) -> dict[str, Any]:
    """프로젝트 전체 스캔 → 구조화된 정보 반환.

    v2.6+: 문서(PDF/DOCX/HWP/HWPX/IPYNB) 텍스트와 폴더명 힌트 포함.
    """
    if not root.exists():
        raise FileNotFoundError(f"프로젝트 루트 없음: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"폴더가 아님: {root}")

    # 문서 먼저 스캔 (extract_keywords 가 결과 활용)
    doc_result = scan_documents(root)
    doc_text = doc_result.pop("_aggregated_text", "")  # 결과에는 노출 안 함

    return {
        "project_root": str(root.absolute()),
        "file_structure": scan_file_structure(root),
        "imports": extract_imports(root),
        "config_files": read_config_files(root),
        "readme": read_readme(root),
        "keyword_frequency": extract_keywords(root, extra_text=doc_text),
        "documents": doc_result,                  # v2.6+
        "path_domain_hints": infer_from_path(root),  # v2.6+
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="프로젝트 폴더 도메인 판별용 구조 정보 추출"
    )
    parser.add_argument("project_root", type=str, help="분석할 프로젝트 루트 폴더")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="출력 JSON 파일 경로 (기본: stdout)")
    parser.add_argument("--compact", action="store_true",
                        help="JSON 압축 출력")

    args = parser.parse_args()
    root = Path(args.project_root)

    try:
        result = scan_project(root)
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    indent = None if args.compact else 2
    output = json.dumps(result, indent=indent, ensure_ascii=False, sort_keys=True)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"✅ 스캔 결과 저장: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
