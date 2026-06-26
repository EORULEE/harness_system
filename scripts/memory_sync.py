#!/usr/bin/env python3
"""
memory_sync.py v2 — 세션 간 영속 메모리 + 자동 컨텍스트 번들

v1 → v2 변화:
  + bundle       : _context.md 자동 생성 (SessionStart 주입용)
  + session-hook : 셸 훅에서 호출하는 entry point (bundle + 요약 출력)
  + prune        : 365일 경과 결정사항을 _archive/로 이동
  + search       : 모든 메모리 파일 grep
  + stats        : 메모리 크기·항목 수·TTL 상태 요약
  + _meta.yaml   : TTL·마지막 bundle 시각·설정 관리
  + Instincts v2 자동 연동 (confidence ≥ 0.8 항목을 bundle에 포함)

v1 호환: add decision / add fact / read / update-map 그대로 유지.

파일 구조:
  .claude/memory/
  ├── decisions.md, domain-facts.md, codebase-map.md   # 기존
  ├── _context.md          # 🆕 세션 주입용 경량 번들
  ├── _meta.yaml           # 🆕 메타
  └── _archive/            # 🆕 오래된 결정사항

의존성: pyyaml (없으면 JSON 폴백)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 공용 동시성 유틸
sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, read_modify_write, save_yaml_atomic, atomic_write,
        load_yaml as _load_yaml_common, HAS_YAML,
    )
except ImportError:
    sys.stderr.write("❌ harness_common.py가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)

if HAS_YAML:
    import yaml

# ────────────────────────────── 상수 ──────────────────────────────

MEMORY_DIR = Path(".claude/memory")
DECISIONS_FILE = MEMORY_DIR / "decisions.md"
FACTS_FILE = MEMORY_DIR / "domain-facts.md"
MAP_FILE = MEMORY_DIR / "codebase-map.md"
CONTEXT_FILE = MEMORY_DIR / "_context.md"
META_FILE = MEMORY_DIR / "_meta.yaml"
ARCHIVE_DIR = MEMORY_DIR / "_archive"
INSTINCTS_DIR = Path(".claude/instincts")

DEFAULT_META = {
    "version": 2,
    "bundle_ttl_days": 7,
    "decision_archive_days": 365,
    "bundle_max_chars": 2000,
    "latest_decisions_count": 10,
    "last_bundle": None,
    "last_prune": None,
    "last_updated": None,
}


# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_structure():
    """디렉토리 + 기본 파일 + 메타 생성."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    if not DECISIONS_FILE.exists():
        DECISIONS_FILE.write_text(
            "# 프로젝트 결정사항\n\n세션 간 자동 유지되는 중요 결정사항입니다.\n\n",
            encoding="utf-8",
        )
    if not FACTS_FILE.exists():
        FACTS_FILE.write_text("# 확정된 도메인 사실\n\n", encoding="utf-8")
    if not MAP_FILE.exists():
        MAP_FILE.write_text(
            "# 코드베이스 구조\n\n`update-map` 명령으로 갱신하세요.\n\n",
            encoding="utf-8",
        )
    if not META_FILE.exists():
        save_meta(DEFAULT_META.copy())


def load_meta() -> dict:
    """메타 로드 (읽기는 락 불필요, atomic rename 덕에 일관성 보장)."""
    ensure_structure()
    if not META_FILE.exists():
        return DEFAULT_META.copy()
    try:
        data = _load_yaml_common(META_FILE)
        return data or DEFAULT_META.copy()
    except Exception:
        return DEFAULT_META.copy()


def save_meta(meta: dict):
    """메타 원자적 저장 — 짧은 락으로 보호."""
    meta["last_updated"] = datetime.now().isoformat(timespec="seconds")
    with file_lock(META_FILE, timeout=5.0):
        save_yaml_atomic(META_FILE, meta)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ────────────────────────────── v1 호환: add / read / update-map ──────────────────────────────


def cmd_add_decision(content_text: str, mark_bundle_stale: bool = True):
    """결정사항 append. POSIX O_APPEND로 atomic (< PIPE_BUF).
    메타 갱신은 별도 짧은 락."""
    ensure_structure()
    entry = f"\n## {today()} — 결정\n{content_text}\n"
    # "a" 모드는 내부적으로 O_APPEND 사용 — 짧은 쓰기는 atomic
    with DECISIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)
        f.flush()
    if mark_bundle_stale:
        with file_lock(META_FILE, timeout=5.0):
            meta = load_meta()
            meta["last_bundle"] = None
            save_yaml_atomic(META_FILE, meta)
    print(f"✅ 결정사항 기록: {today()}")


def cmd_add_fact(domain: str, fact: str, mark_bundle_stale: bool = True):
    """도메인 사실 추가 — RMW이므로 락 필수."""
    ensure_structure()
    with file_lock(FACTS_FILE, timeout=10.0):
        current = FACTS_FILE.read_text(encoding="utf-8")
        section_header = f"## {domain}"
        if section_header not in current:
            new_content = current.rstrip() + f"\n\n{section_header}\n- {fact}\n"
        else:
            lines = current.splitlines()
            insert_at = None
            for i, line in enumerate(lines):
                if line.strip() == section_header:
                    insert_at = i + 1
                    for j in range(i + 1, len(lines)):
                        if lines[j].startswith("## "):
                            insert_at = j
                            break
                        if lines[j].strip() or j == len(lines) - 1:
                            insert_at = j + 1
                    break
            if insert_at is not None:
                lines.insert(insert_at, f"- {fact}")
                new_content = "\n".join(lines) + "\n"
            else:
                new_content = current
        atomic_write(FACTS_FILE, new_content)
    if mark_bundle_stale:
        with file_lock(META_FILE, timeout=5.0):
            meta = load_meta()
            meta["last_bundle"] = None
            save_yaml_atomic(META_FILE, meta)
    print(f"✅ 도메인 사실 기록: [{domain}] {fact}")


def cmd_read(target: str = "all"):
    ensure_structure()
    if target in ("decisions", "all"):
        print("━━━ 결정사항 ━━━")
        print(DECISIONS_FILE.read_text(encoding="utf-8"))
    if target in ("facts", "all"):
        print("━━━ 도메인 사실 ━━━")
        print(FACTS_FILE.read_text(encoding="utf-8"))
    if target in ("map", "all"):
        print("━━━ 코드베이스 맵 ━━━")
        print(MAP_FILE.read_text(encoding="utf-8"))
    if target == "context":
        if CONTEXT_FILE.exists():
            print(CONTEXT_FILE.read_text(encoding="utf-8"))
        else:
            print("ℹ️  _context.md 없음 — bundle 명령으로 생성하세요")


def cmd_update_map():
    ensure_structure()
    lines = ["# 코드베이스 구조", f"\n갱신: {now_iso()}\n", "```"]
    ignored = {".git", "__pycache__", "node_modules", ".claude", "venv", ".venv", "outputs"}

    def walk(path: Path, depth: int = 0, max_depth: int = 3):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return
        for item in entries:
            if item.name.startswith(".") or item.name in ignored:
                continue
            prefix = "  " * depth + ("📁 " if item.is_dir() else "📄 ")
            lines.append(f"{prefix}{item.name}")
            if item.is_dir():
                walk(item, depth + 1, max_depth)

    walk(Path("."))
    lines.append("```\n")
    with file_lock(MAP_FILE, timeout=5.0):
        atomic_write(MAP_FILE, "\n".join(lines))
    with file_lock(META_FILE, timeout=5.0):
        meta = load_meta()
        meta["last_bundle"] = None
        save_yaml_atomic(META_FILE, meta)
    print(f"✅ 코드베이스 맵 갱신: {MAP_FILE}")


# ────────────────────────────── bundle: 자동 컨텍스트 생성 ──────────────────────────────


def get_recent_decisions_since(hours: int = 48, campaign: str | None = None, limit: int = 20) -> list[dict]:
    """최근 N시간 내 decisions 항목을 단순 필터링. campaign 문자열이 있으면 body 포함 여부로 추가 필터."""
    decisions = get_recent_decisions(200)
    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = []
    for d in decisions:
        try:
            day = datetime.fromisoformat(d["date"] + "T00:00:00")
        except ValueError:
            continue
        if day < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        if campaign and campaign not in d.get("body", "") and campaign not in d.get("header", ""):
            continue
        filtered.append(d)
    return filtered[:limit]


def get_recent_decisions(limit: int) -> list[dict]:
    """decisions.md에서 최근 N개 항목 파싱."""
    if not DECISIONS_FILE.exists():
        return []
    content = DECISIONS_FILE.read_text(encoding="utf-8")
    # '## YYYY-MM-DD — 결정' 블록 분리
    blocks = re.split(r"\n## ", content)
    entries = []
    for block in blocks[1:]:
        lines = block.strip().split("\n", 1)
        if not lines:
            continue
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", header)
        if not date_match:
            continue
        entries.append({"date": date_match.group(1), "header": header, "body": body})
    # 최신순 정렬
    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries[:limit]


def get_codebase_map_summary(max_lines: int = 25) -> str:
    """codebase-map.md의 헤더+상위 구조만 추출."""
    if not MAP_FILE.exists():
        return ""
    content = MAP_FILE.read_text(encoding="utf-8")
    lines = content.split("\n")
    # '```' 블록 안의 상위 depth만 (2단계까지)
    result = []
    in_code = False
    for line in lines:
        if line.strip() == "```":
            in_code = not in_code
            continue
        if not in_code:
            continue
        stripped = line.rstrip()
        if not stripped:
            continue
        # 들여쓰기 2칸 이하만 (depth 0–1)
        leading = len(line) - len(line.lstrip(" "))
        if leading <= 2:
            result.append(stripped)
        if len(result) >= max_lines:
            break
    return "\n".join(result)


def get_confirmed_instincts(limit: int = 8) -> list[dict]:
    """Instincts v2가 있으면 confidence ≥ 0.8 항목 반환."""
    if not INSTINCTS_DIR.exists():
        return []
    if not HAS_YAML:
        return []
    confirmed = []
    for cat_dir in INSTINCTS_DIR.iterdir():
        if not cat_dir.is_dir() or cat_dir.name.startswith("_"):
            continue
        for yaml_file in cat_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            conf = data.get("confidence", 0)
            if conf < 0.8:
                continue
            trigger_text = data.get("trigger", {}).get("natural", "").strip()
            action_text = data.get("action", "").strip().split("\n")[0][:120]
            confirmed.append({
                "id": data.get("id", yaml_file.stem),
                "category": cat_dir.name,
                "confidence": conf,
                "trigger": trigger_text[:100],
                "action_summary": action_text,
            })
    confirmed.sort(key=lambda x: -x["confidence"])
    return confirmed[:limit]


def compose_bundle(meta: dict) -> str:
    """모든 메모리 소스를 하나의 경량 번들로 압축."""
    limit = meta.get("latest_decisions_count", 10)
    max_chars = meta.get("bundle_max_chars", 2000)

    parts: list[str] = []
    parts.append(f"---")
    parts.append(f"generated: {now_iso()}")
    parts.append(f"ttl_days: {meta.get('bundle_ttl_days', 7)}")
    parts.append(f"---")
    parts.append("")
    parts.append("# 📌 Memory Context Bundle (세션 시작 자동 주입용)")
    parts.append("")
    parts.append("> 모든 에이전트는 작업 시작 전 이 파일을 참조합니다.")
    parts.append("> 이 파일은 `memory_sync.py bundle` 실행 시 자동 재생성됩니다.")
    parts.append("")

    # 1) 최근 결정사항
    parts.append(f"## 🎯 최근 결정사항 (최신 {limit}개)")
    parts.append("")
    decisions = get_recent_decisions(limit)
    if decisions:
        for d in decisions:
            body_one_line = re.sub(r"\s+", " ", d["body"])[:160]
            parts.append(f"- **{d['date']}** — {body_one_line}")
    else:
        parts.append("_기록된 결정사항 없음_")
    parts.append("")

    # 2) 도메인 사실
    parts.append("## 📚 확정된 도메인 사실")
    parts.append("")
    facts_content = FACTS_FILE.read_text(encoding="utf-8") if FACTS_FILE.exists() else ""
    # '# 확정된 도메인 사실' 헤더 제거, 본문만
    facts_body = re.sub(r"^# 확정된 도메인 사실\s*\n", "", facts_content, count=1).strip()
    if facts_body:
        parts.append(facts_body)
    else:
        parts.append("_기록된 도메인 사실 없음_")
    parts.append("")

    # 3) 코드베이스 맵 요약
    map_summary = get_codebase_map_summary(25)
    if map_summary:
        parts.append("## 🗺️  코드베이스 구조 요약")
        parts.append("")
        parts.append("```")
        parts.append(map_summary)
        parts.append("```")
        parts.append("")

    # 4) Confirmed instincts (v2 연동)
    instincts = get_confirmed_instincts(8)
    if instincts:
        parts.append("## 🧭 확증된 Instincts (confidence ≥ 0.80)")
        parts.append("")
        for ins in instincts:
            parts.append(
                f"- **[{ins['category']}]** `{ins['id']}` (conf: {ins['confidence']:.2f})"
            )
            parts.append(f"  - 트리거: {ins['trigger']}")
            parts.append(f"  - 대응: {ins['action_summary']}")
        parts.append("")
        parts.append("> 세부 내용은 `scripts/instincts_updater.py show <id>` 로 확인.")
        parts.append("")

    # ── 🆕 캠페인 섹션 (Q4: 선택적 포함) ──
    campaigns_dir = Path(".claude/campaigns")
    index_file = campaigns_dir / "_index.yaml"
    active_file = campaigns_dir / "_active.yaml"
    if index_file.exists() and active_file.exists():
        try:
            idx_data = _load_yaml_common(index_file) or {}
            act_data = _load_yaml_common(active_file) or {}
            campaigns = idx_data.get("campaigns", {})
            active_ids = act_data.get("active_ids", [])
            focus = act_data.get("focus")

            if campaigns:
                parts.append("## 📋 진행 중인 캠페인")
                parts.append("")
                # 최대 3개, last_activity 최신순
                items = sorted(
                    [(cid, info) for cid, info in campaigns.items()
                     if info.get("status") != "done"],
                    key=lambda x: x[1].get("last_activity", ""),
                    reverse=True,
                )[:3]
                for cid, info in items:
                    marker = "⭐" if cid == focus else ("✓" if cid in active_ids else "·")
                    last = info.get("last_activity", "-")[:16]
                    parts.append(
                        f"- {marker} `{cid}` — {info.get('name', '?')} "
                        f"(phase: {info.get('phase', '?')}, 마지막: {last})"
                    )
                if len(campaigns) > 3:
                    parts.append(f"- _... 총 {len(campaigns)}개 캠페인, 전체는 `campaign_manager.py list`_")
                parts.append("")
                parts.append("> 재개: `python scripts/campaign_manager.py continue`")
                parts.append("")
        except Exception as e:
            pass  # 캠페인 파일 읽기 실패해도 bundle은 생성

    # ── 🆕 Discovery Relay 섹션 (미읽음 요약) ──
    discoveries_dir = Path(".claude/discoveries")
    d_index = discoveries_dir / "_index.yaml"
    d_read_dir = discoveries_dir / "_read"
    if d_index.exists():
        try:
            d_idx = _load_yaml_common(d_index) or {}
            all_discs = d_idx.get("discoveries", {})
            if all_discs:
                # 현재 워크트리 감지 (env → git → main)
                import os, subprocess
                wt_id = os.environ.get("HARNESS_WORKTREE_ID")
                if not wt_id:
                    try:
                        r = subprocess.run(
                            ["git", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, timeout=3,
                        )
                        if r.returncode == 0:
                            wt_id = Path(r.stdout.strip()).name or "main"
                    except Exception:
                        wt_id = "main"
                wt_id = wt_id or "main"

                # 읽음 마커 조회
                marker_file = d_read_dir / f"{wt_id}.yaml"
                read_ids = set()
                if marker_file.exists():
                    m = _load_yaml_common(marker_file) or {}
                    read_ids = set(m.get("read_ids", []))

                # 미읽음만 필터
                unread = [
                    (did, info) for did, info in all_discs.items()
                    if did not in read_ids
                ]

                if unread:
                    # severity 순 정렬
                    sev_order = {"critical": 0, "warning": 1, "info": 2}
                    unread.sort(
                        key=lambda x: sev_order.get(
                            x[1].get("severity", "info"), 99))

                    # severity 카운트
                    by_sev = {"critical": 0, "warning": 0, "info": 0}
                    for _, info in unread:
                        s = info.get("severity", "info")
                        by_sev[s] = by_sev.get(s, 0) + 1

                    parts.append(f"## 🔔 읽지 않은 Discovery ({len(unread)}건, 워크트리: {wt_id})")
                    parts.append("")
                    sev_str = []
                    if by_sev["critical"]:
                        sev_str.append(f"🚨 critical {by_sev['critical']}")
                    if by_sev["warning"]:
                        sev_str.append(f"⚠️ warning {by_sev['warning']}")
                    if by_sev["info"]:
                        sev_str.append(f"ℹ️ info {by_sev['info']}")
                    if sev_str:
                        parts.append(f"_심각도: {' · '.join(sev_str)}_")
                        parts.append("")

                    # 상위 3개
                    emoji_map = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
                    for did, info in unread[:3]:
                        emoji = emoji_map.get(info.get("severity", "info"), "•")
                        parts.append(
                            f"- {emoji} `{did}` — {info.get('title', '?')} "
                            f"(by {info.get('published_by', '?')})"
                        )
                    if len(unread) > 3:
                        parts.append(f"- _... 총 {len(unread)}건, 전체는 `discovery_relay.py list --unread`_")
                    parts.append("")
                    parts.append("> 상세: `python scripts/discovery_relay.py show <id>`")
                    parts.append("")
        except Exception:
            pass  # discovery 파일 읽기 실패해도 bundle은 생성

    # ── 🆕 Pending structured review 섹션 (compression_worker v2.4.5) ──
    pending_dir = Path('.claude/runtime/pending_extractions')
    if pending_dir.exists():
        try:
            pending_files = sorted(pending_dir.glob('*.yaml'), key=lambda p: p.stat().st_mtime, reverse=True)
            if pending_files:
                parts.append(f"## 🧾 Structured review 대기 ({len(pending_files)}건)")
                parts.append('')
                for pf in pending_files[:3]:
                    pdata = _load_yaml_common(pf) or {}
                    tid = pdata.get('trace_id', pf.stem)
                    dcnt = len(pdata.get('decisions', []))
                    fcnt = len(pdata.get('facts', []))
                    created = str(pdata.get('created_at', ''))[:16]
                    parts.append(f"- `{tid}` — decisions {dcnt} / facts {fcnt} ({created})")
                if len(pending_files) > 3:
                    parts.append(f"- _... 총 {len(pending_files)}건, 전체는 `compression_worker.py list-pending`_")
                parts.append('')
                parts.append('> 승인: `python scripts/compression_worker.py apply-pending <trace_id>`')
                parts.append('')
        except Exception:
            pass

    # ── 🆕 Trace 섹션 (Layer 1 힌트, Step 1) ──
    traces_index = Path(".claude/memory/_traces_index.yaml")
    if traces_index.exists():
        try:
            tidx = _load_yaml_common(traces_index) or {}
            traces = tidx.get("traces", {})
            if traces:
                # active + 최근 ended 상위 3개
                items = sorted(
                    traces.items(),
                    key=lambda x: x[1].get("last_append") or x[1].get("started", ""),
                    reverse=True,
                )[:3]
                parts.append("## 📝 최근 Trace (Layer 1)")
                parts.append("")
                parts.append("_컨텍스트 창 절약을 위해 제목만 포함. 내용은 retrieve로 검색._")
                parts.append("")
                for tid, info in items:
                    status_icon = "🔄" if info.get("status") == "active" else "✔"
                    sec_count = info.get("section_count", "?")
                    parts.append(
                        f"- {status_icon} `{tid}` — {info.get('name', '?')} "
                        f"({sec_count}섹션)"
                    )
                parts.append("")
                parts.append("> 검색: `python scripts/trace_manager.py retrieve \"<query>\"`")
                parts.append("")
        except Exception:
            pass


    bundle = "\n".join(parts)

    # 토큰 예산 초과 시 잘라내기
    if len(bundle) > max_chars:
        bundle = bundle[: max_chars - 100] + "\n\n_...(번들 크기 상한 도달, 잘림. show 명령으로 원본 참조)_\n"

    return bundle


def cmd_bundle(args):
    """컨텍스트 번들 생성 — _context.md에 저장. 락 보호."""
    ensure_structure()
    meta = load_meta()
    bundle = compose_bundle(meta)
    with file_lock(CONTEXT_FILE, timeout=10.0):
        atomic_write(CONTEXT_FILE, bundle)
    with file_lock(META_FILE, timeout=5.0):
        meta = load_meta()  # 재로드 (다른 프로세스 갱신 반영)
        # microsecond 포함 isoformat — mtime 비교 정밀도 확보
        meta["last_bundle"] = datetime.now().isoformat()
        save_yaml_atomic(META_FILE, meta)
    size = len(bundle)
    max_chars = meta.get("bundle_max_chars", 2000)
    usage = size / max_chars * 100
    if args.quiet:
        return
    print(
        f"✅ Bundle 생성: {CONTEXT_FILE} ({size} chars / {max_chars} max — {usage:.0f}%)"
    )


def _emit_active_context_core():
    """Memory Continuity v2 — SessionStart 최소 주입 (status·objective·completed·next_action·locked_facts·checkpoint).
    _active_context.md(현재 project) 의 핵심 상태를 bundle 앞에 1회 출력.
    completed/locked_facts 는 원문 verbatim(요약·재작성·추론 없음, 각 최대 10·중복 제거).
    파싱 = memory_sync 가 이미 쓰는 yaml.safe_load 재사용(중복 파서 없음). secret 은 write 시 마스킹됨(update_active_context).
    freshness gate: emit 직전 source checkpoint 와 sha256(없으면 mtime) 으로 최신성 검증 — stale 이면
    상태필드 미주입하고 ⚠️ STALE 경고·재처리 안내만 출력(오래된 상태를 현재 사실로 주입 방지).
    best-effort: 어떤 실패에도 무출력으로 통과(기존 memory bundle/KB 주입은 그대로 진행)."""
    try:
        import os, re as _re, yaml, hashlib
        from datetime import datetime
        cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        proj = _re.sub(r'[^a-zA-Z0-9]', '-', cwd)
        mem_root = os.path.expanduser(f"~/.claude/projects/{proj}/memory")
        ac = os.path.join(mem_root, "_active_context.md")
        if not os.path.isfile(ac):
            return
        m = _re.search(r'^---\n(.*?)\n---', open(ac, encoding="utf-8").read(), _re.S)
        if not m:
            return
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            return
        # project 불일치 / failed(quarantine) → 미주입.
        if fm.get("project_id") != proj:
            return
        if fm.get("status") == "failed":
            return

        # ── freshness gate ──────────────────────────────────────────────
        # checkpoint 가 갱신됐는데 worker 실패로 _active_context.md 가 안 따라오면,
        # 오래된 상태를 현재 사실처럼 주입하지 않는다. 우선순위:
        #   1) source_checkpoint_sha256 vs 현재 checkpoint sha256
        #   2) (hash 없을 때만) checkpoint mtime vs ACTIVE_CONTEXT updated_at
        #   3) hash 불일치 / checkpoint 더 최신 → stale
        #   5) 근거 부족(검증 불가) → needs_review (stale 단정 아님, 날조 없음)
        src_cp = fm.get("source_checkpoint")
        cp_path = os.path.join(mem_root, src_cp) if src_cp else None
        cp_exists = bool(cp_path and os.path.isfile(cp_path))
        cp_sha = str(fm.get("source_checkpoint_sha256") or "").strip()
        stale = False; stale_reason = ""; verified = False
        if cp_exists:
            if cp_sha:                                   # (1) hash 우선
                try:
                    cur = hashlib.sha256(open(cp_path, "rb").read()).hexdigest()
                    verified = True
                    if cur != cp_sha:
                        stale = True; stale_reason = "source checkpoint sha256 불일치"
                except Exception:
                    verified = False
            else:                                        # (2) hash 없을 때만 mtime fallback
                try:
                    ua = fm.get("updated_at")
                    ua_ts = datetime.fromisoformat(str(ua)).timestamp() if ua else None
                except Exception:
                    ua_ts = None
                if ua_ts is not None:
                    verified = True
                    if os.path.getmtime(cp_path) > ua_ts + 1:   # 1s tolerance
                        stale = True; stale_reason = "checkpoint 가 ACTIVE_CONTEXT 보다 최신(worker 미반영 의심)"
        if fm.get("status") == "stale":                  # worker 자가보고 stale 도 동일 취급
            stale = True
            if not stale_reason: stale_reason = "status=stale (worker 자가보고)"
        nr = (fm.get("needs_review") in (True, "true", "True")) or (fm.get("status") == "bootstrap") \
             or (not verified and not stale)             # (5) 검증 불가 → needs_review

        out = ["", "## 🔄 ACTIVE CONTEXT (Memory Continuity v2 — 핵심만)"]
        if stale:
            # stale: 상태필드(objective/completed/next_action/locked_facts) 미주입 — 경고·경로·재처리만.
            out.append("- ⚠️ STALE ACTIVE CONTEXT — 이전 상태를 현재 사실로 신뢰하지 마세요.")
            out.append(f"- 사유: {stale_reason}")
            if src_cp:
                out.append(f"- source checkpoint: {src_cp} — 재처리 필요(worker 재실행/checkpoint 확인)")
            out.append("- status=stale(reprocess) · objective/completed/next_action/locked_facts 미주입")
            out.append("")
            print("\n".join(out))
            return

        def _lst(key):                                  # 원문 verbatim + 중복 제거(순서 유지) + 최대 10
            v = fm.get(key)
            if not isinstance(v, list):
                return []
            seen, items = set(), []
            for it in v:
                s = str(it).strip()
                if s and s not in seen:
                    seen.add(s); items.append(s[:160])
                if len(items) >= 10:
                    break
            return items
        if fm.get("current_objective"):
            out.append(f"- 현재 목표: {str(fm['current_objective'])[:200]}")
        comp = _lst("completed")
        if comp:
            out.append("- 완료:")
            out += [f"  - {c}" for c in comp]
        nxt = fm.get("next_action") or ""
        out.append(f"- 다음 행동: {str(nxt)[:200] if nxt else '(unverified — needs_review)'}")
        lf = _lst("locked_facts")
        if lf:
            out.append("- 고정 사실(locked):")
            out += [f"  - {x}" for x in lf]
        if fm.get("latest_checkpoint"):
            out.append(f"- 최신 checkpoint: {str(fm['latest_checkpoint'])[:120]}")
        out.append(f"- status={fm.get('status','?')} · confidence={fm.get('confidence','?')} · source={fm.get('source_event','?')}")
        if nr:
            out.append("- ⚠️ needs_review — 확정 상태 아님(freshness 검증 불가 포함). checkpoint/transcript 로 확인 후 사용.")
        out.append("")
        print("\n".join(out))
    except Exception:
        return


def cmd_session_hook(args):
    """Claude Code SessionStart 훅에서 호출하는 entry.
    
    재생성 조건 (OR):
      - last_bundle이 None (처음 실행)
      - TTL 만료 (7일 기본)
      - 🆕 decisions/facts/traces/instincts의 mtime이 last_bundle보다 최신
        → 새 데이터가 추가됐으니 반영해야 함
    """
    ensure_structure()
    meta = load_meta()
    need_regen = False
    regen_reason = ""
    last_bundle = meta.get("last_bundle")

    if not last_bundle:
        need_regen = True
        regen_reason = "first run"
    else:
        try:
            last_dt = datetime.fromisoformat(last_bundle)
            ttl_days = meta.get("bundle_ttl_days", 7)
            if datetime.now() - last_dt > timedelta(days=ttl_days):
                need_regen = True
                regen_reason = f"TTL expired ({ttl_days}d)"
            else:
                # 🆕 mtime 체크 — 새 데이터가 있는지
                last_bundle_ts = last_dt.timestamp()
                watched_files = [
                    DECISIONS_FILE, FACTS_FILE,
                    Path(".claude/memory/_traces_index.yaml"),
                    Path(".claude/campaigns/_index.yaml"),
                    Path(".claude/campaigns/_active.yaml"),
                    Path(".claude/discoveries/_index.yaml"),
                ]
                # instincts 디렉토리는 재귀 확인
                instincts_dir = Path(".claude/instincts")
                if instincts_dir.exists():
                    for f in instincts_dir.rglob("*.yaml"):
                        if f.stat().st_mtime > last_bundle_ts:
                            need_regen = True
                            regen_reason = f"new instinct: {f.name}"
                            break

                if not need_regen:
                    for f in watched_files:
                        if f.exists() and f.stat().st_mtime > last_bundle_ts:
                            need_regen = True
                            regen_reason = f"updated: {f.name}"
                            break
        except ValueError:
            need_regen = True
            regen_reason = "invalid last_bundle timestamp"

    if need_regen or not CONTEXT_FILE.exists():
        bundle = compose_bundle(meta)
        with file_lock(CONTEXT_FILE, timeout=10.0):
            atomic_write(CONTEXT_FILE, bundle)
        with file_lock(META_FILE, timeout=5.0):
            meta = load_meta()
            # microsecond 포함 — mtime 비교 정밀도 확보
            meta["last_bundle"] = datetime.now().isoformat()
            save_yaml_atomic(META_FILE, meta)

    # 훅 모드: 번들을 stdout으로 출력
    if args.emit_stdout:
        _emit_active_context_core()  # Memory Continuity v2: ACTIVE_CONTEXT 핵심을 bundle 앞에(best-effort)
        print(CONTEXT_FILE.read_text(encoding="utf-8"))
    else:
        size = len(CONTEXT_FILE.read_text(encoding="utf-8"))
        if need_regen:
            print(f"📌 Memory context regenerated ({regen_reason}, {size} chars) — {CONTEXT_FILE}")
        else:
            print(f"📌 Memory context ready (cached, {size} chars) — {CONTEXT_FILE}")


# ────────────────────────────── prune ──────────────────────────────


def cmd_prune(args):
    """365일 경과 결정사항을 _archive/로 이동."""
    ensure_structure()
    meta = load_meta()
    days = args.days if args.days is not None else meta.get("decision_archive_days", 365)
    cutoff = datetime.now() - timedelta(days=days)

    content = DECISIONS_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"\n## ", content)
    header = blocks[0]  # 첫 블록은 H1 헤더
    remaining = [header]
    archived_entries = []

    for block in blocks[1:]:
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", block)
        if not date_match:
            remaining.append("## " + block)
            continue
        date_str = date_match.group(1)
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            remaining.append("## " + block)
            continue
        if entry_date < cutoff:
            archived_entries.append("## " + block)
        else:
            remaining.append("## " + block)

    if not archived_entries:
        print(f"ℹ️  {days}일 이전 결정사항 없음 — 아카이브할 항목 없음")
        return

    if args.dry_run:
        print(f"[DRY] {len(archived_entries)}개 결정사항 아카이브 대상:")
        for e in archived_entries[:5]:
            first_line = e.split("\n", 1)[0]
            print(f"  {first_line}")
        if len(archived_entries) > 5:
            print(f"  ... (+{len(archived_entries) - 5}개)")
        return

    # 아카이브에 append (락 보호)
    archive_file = ARCHIVE_DIR / f"decisions-archive-{datetime.now().strftime('%Y%m%d')}.md"
    with file_lock(archive_file, timeout=10.0):
        prior = archive_file.read_text(encoding="utf-8") if archive_file.exists() else ""
        atomic_write(archive_file, prior + "\n" + "\n".join(archived_entries))

    # decisions.md 갱신 (원자적)
    with file_lock(DECISIONS_FILE, timeout=10.0):
        atomic_write(DECISIONS_FILE, "\n".join(remaining))

    with file_lock(META_FILE, timeout=5.0):
        meta = load_meta()
        meta["last_prune"] = now_iso()
        meta["last_bundle"] = None
        save_yaml_atomic(META_FILE, meta)
    print(f"✅ {len(archived_entries)}개 아카이브: {archive_file}")


# ────────────────────────────── search ──────────────────────────────


def cmd_search(args):
    """모든 메모리 파일에서 쿼리 검색 (단순 grep)."""
    ensure_structure()
    query = args.query.lower()
    files_to_search = [DECISIONS_FILE, FACTS_FILE, MAP_FILE]
    if args.include_archive and ARCHIVE_DIR.exists():
        files_to_search.extend(ARCHIVE_DIR.glob("*.md"))

    total_hits = 0
    for f in files_to_search:
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        lines = content.split("\n")
        hits = []
        current_section = ""
        for i, line in enumerate(lines, 1):
            if line.startswith("##"):
                current_section = line.strip()
            if query in line.lower():
                hits.append((i, current_section, line.strip()))
        if hits:
            print(f"\n📄 {f.name}")
            for ln, section, text in hits[: args.limit]:
                if section:
                    print(f"  L{ln} [{section[:40]}]: {text[:120]}")
                else:
                    print(f"  L{ln}: {text[:120]}")
            if len(hits) > args.limit:
                print(f"  ... (+{len(hits) - args.limit} 더 있음)")
            total_hits += len(hits)

    if total_hits == 0:
        print(f"🔍 '{args.query}' — 일치 항목 없음")
    else:
        print(f"\n✅ 총 {total_hits}건 일치")


# ────────────────────────────── stats ──────────────────────────────


def cmd_recall(args):
    items = get_recent_decisions_since(hours=args.hours, campaign=args.campaign, limit=args.limit)
    if args.format == "json":
        print(json.dumps({"hours": args.hours, "campaign": args.campaign, "results": items}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("ℹ️  조건에 맞는 최근 결정사항 없음")
        return
    print(f"\n🧠 최근 결정 복원 (최근 {args.hours}h)")
    for d in items:
        body_one_line = re.sub(r"\s+", " ", d["body"])[:200]
        print(f"- {d['date']} — {body_one_line}")


def cmd_stats(args):
    ensure_structure()
    meta = load_meta()

    def size_str(path: Path) -> str:
        if not path.exists():
            return "—"
        size = path.stat().st_size
        return f"{size:,} B"

    def line_count(path: Path) -> int:
        if not path.exists():
            return 0
        return len(path.read_text(encoding="utf-8").splitlines())

    decisions = get_recent_decisions(9999)
    total_decisions = len(decisions)
    archive_count = len(list(ARCHIVE_DIR.glob("*.md"))) if ARCHIVE_DIR.exists() else 0

    # 번들 TTL 상태
    last_bundle = meta.get("last_bundle")
    ttl_status = "미생성"
    if last_bundle:
        try:
            last_dt = datetime.fromisoformat(last_bundle)
            age_days = (datetime.now() - last_dt).days
            ttl_days = meta.get("bundle_ttl_days", 7)
            if age_days > ttl_days:
                ttl_status = f"만료 ({age_days}일 경과)"
            else:
                ttl_status = f"신선 ({age_days}/{ttl_days}일)"
        except ValueError:
            ttl_status = "파싱 오류"

    confirmed_instincts = get_confirmed_instincts(999)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Memory 통계 (v2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 크기 / 라인 수:
  decisions.md         {size_str(DECISIONS_FILE):>12s}   {line_count(DECISIONS_FILE):>4d} lines
  domain-facts.md      {size_str(FACTS_FILE):>12s}   {line_count(FACTS_FILE):>4d} lines
  codebase-map.md      {size_str(MAP_FILE):>12s}   {line_count(MAP_FILE):>4d} lines
  _context.md (bundle) {size_str(CONTEXT_FILE):>12s}   {line_count(CONTEXT_FILE):>4d} lines
  pending review      {len(list(Path('.claude/runtime/pending_extractions').glob('*.yaml'))) if Path('.claude/runtime/pending_extractions').exists() else 0:>12d} files

결정사항:
  활성:                {total_decisions}개
  아카이브 파일:       {archive_count}개

번들 상태:
  마지막 생성:         {last_bundle or '-'}
  TTL:                 {ttl_status}
  
Instincts 연동:
  Confirmed (≥0.8):    {len(confirmed_instincts)}개 (번들 포함됨)

메타:
  마지막 갱신:         {meta.get('last_updated', '-')}
  마지막 prune:        {meta.get('last_prune', '-')}
""")


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Memory Sync v2 — 자동 컨텍스트 번들 + TTL",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # v1 compat: add
    add = sub.add_parser("add", help="결정사항 / 도메인 사실 추가 (v1 호환)")
    add_sub = add.add_subparsers(dest="add_type", required=True)
    ad = add_sub.add_parser("decision", help="결정사항")
    ad.add_argument("content", nargs="+")
    af = add_sub.add_parser("fact", help="도메인 사실")
    af.add_argument("domain")
    af.add_argument("fact", nargs="+")

    # read (v1)
    rd = sub.add_parser("read", help="메모리 읽기 (v1 호환)")
    rd.add_argument("target", nargs="?", default="all",
                    choices=["all", "decisions", "facts", "map", "context"])

    # update-map (v1)
    sub.add_parser("update-map", help="codebase-map.md 재생성")

    # bundle
    bd = sub.add_parser("bundle", help="_context.md 자동 생성")
    bd.add_argument("--quiet", action="store_true")

    # session-hook
    sh = sub.add_parser("session-hook", help="SessionStart 훅 entry (TTL 검사 + 생성)")
    sh.add_argument("--emit-stdout", action="store_true", dest="emit_stdout",
                    help="번들을 stdout으로 출력 (훅 주입용)")

    # prune
    pr = sub.add_parser("prune", help="365일 경과 결정사항 아카이브")
    pr.add_argument("--days", type=int)
    pr.add_argument("--dry-run", action="store_true", dest="dry_run")

    # search
    sr = sub.add_parser("search", help="메모리 grep")
    sr.add_argument("query")
    sr.add_argument("--limit", type=int, default=10)
    sr.add_argument("--include-archive", action="store_true", dest="include_archive")

    # stats
    sub.add_parser("stats", help="요약 통계")

    # recall
    rc = sub.add_parser("recall", help="최근 결정사항 빠른 복원")
    rc.add_argument("--hours", type=int, default=48)
    rc.add_argument("--campaign")
    rc.add_argument("--limit", type=int, default=10)
    rc.add_argument("--format", choices=["text", "json"], default="text")

    # retrieve (Step 1 하이브리드 검색)
    rp = sub.add_parser("retrieve", help="하이브리드 검색")
    rp.add_argument("query")
    rp.add_argument("--scope", choices=["all", "decisions", "facts", "instincts", "traces"],
                    default="all")
    rp.add_argument("--top", type=int, default=5)
    rp.add_argument("--semantic-weight", type=float, default=0.5,
                    dest="semantic_weight")
    rp.add_argument("--format", choices=["text", "json"], default="text")
    return p



# ────────────────────────────── retrieve (Step 1 — 하이브리드 검색) ──────────────────────────────

def cmd_retrieve(args):
    """메모리 전체(decisions + facts + instincts + traces)에서 쿼리와 관련된 항목 검색."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import embeddings_store
    except ImportError:
        sys.stderr.write("❌ embeddings_store.py 필요\n")
        sys.exit(1)

    query = args.query
    scope = args.scope or "all"

    collections = []
    if scope == "all":
        collections = ["decisions", "facts", "instincts", "traces"]
    else:
        collections = [scope]

    all_results = []
    for col in collections:
        results = embeddings_store.hybrid_search(
            query, col, top_k=args.top,
            semantic_weight=args.semantic_weight,
        )
        for did, score, dbg in results:
            all_results.append({
                "collection": col,
                "id": did,
                "score": round(score, 4),
                "debug": dbg,
            })

    all_results.sort(key=lambda x: x["score"], reverse=True)
    all_results = all_results[:args.top]

    if args.format == "json":
        print(json.dumps({
            "query": query,
            "scope": scope,
            "semantic_backend": embeddings_store.semantic_backend_name(),
            "results": all_results,
        }, ensure_ascii=False, indent=2))
        return

    if not all_results:
        print(f"ℹ️  '{query}'에 맞는 결과 없음 (scope={scope})")
        return

    print(f"\n🔍 '{query}' 검색 결과 ({len(all_results)}건)")
    print(f"   semantic backend: {embeddings_store.semantic_backend_name()}\n")
    for i, r in enumerate(all_results, 1):
        print(f"  {i}. [{r['score']}] [{r['collection']}] {r['id']}")
        if "bm25_rank" in r["debug"]:
            print(f"      bm25_rank: {r['debug']['bm25_rank']}")
        if "semantic_rank" in r["debug"]:
            print(f"      semantic_rank: {r['debug']['semantic_rank']}")
        print()


def main():
    args = build_parser().parse_args()
    if args.cmd == "add":
        if args.add_type == "decision":
            cmd_add_decision(" ".join(args.content))
        elif args.add_type == "fact":
            cmd_add_fact(args.domain, " ".join(args.fact))
    elif args.cmd == "read":
        cmd_read(args.target)
    elif args.cmd == "update-map":
        cmd_update_map()
    elif args.cmd == "bundle":
        cmd_bundle(args)
    elif args.cmd == "session-hook":
        cmd_session_hook(args)
    elif args.cmd == "prune":
        cmd_prune(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "retrieve":
        cmd_retrieve(args)
    elif args.cmd == "recall":
        cmd_recall(args)
    elif args.cmd == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
