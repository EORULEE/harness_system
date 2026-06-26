#!/usr/bin/env python3
"""
trace_manager.py — Layer 1 풀 trace 관리

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
개념 (3계층 메모리의 Layer 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
시도·에러·해결·중간 결과를 **전부** 기록.
세션 시작 시 컨텍스트에 주입되지 않음 (검색으로만 꺼내옴).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
.claude/memory/
├── traces/
│   ├── {slug}.md                   # 원본 trace (Markdown ## 섹션 단위)
│   └── ...
├── _traces_index.yaml              # 모든 trace 메타 (id, name, campaign, status)
└── _active_trace.txt               # 현재 활성 trace id (한 번에 하나)

Campaign 연동 시 — archive 이후:
.claude/campaigns/_archive/{camp-id}/traces/{slug}.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
명령
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  start <name>           새 trace 시작 (active로 설정)
  append "<content>"     현재 active trace에 섹션 추가
  end [<id>]             trace 종료 (LLM 압축은 Step 2에서)
  list [--active]        trace 목록
  show <id>              전문 조회
  retrieve "<query>"     하이브리드 검색 → 관련 섹션 반환
  status                 현재 active trace 상태
  switch <id>            active 전환

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, read_modify_write, save_yaml_atomic, atomic_write,
        append_line_atomic, load_yaml, HAS_YAML, now_iso,
    )
    import embeddings_store
except ImportError as e:
    sys.stderr.write(f"❌ 의존성 로드 실패: {e}\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요\n")
    sys.exit(1)


# ────────────────────────────── 경로 ──────────────────────────────

MEMORY_DIR = Path(".claude/memory")
TRACES_DIR = MEMORY_DIR / "traces"
INDEX_FILE = MEMORY_DIR / "_traces_index.yaml"
ACTIVE_FILE = MEMORY_DIR / "_active_trace.txt"

ICON_MAP = {
    "note": "📝",
    "tried": "🧪",
    "error": "❌",
    "resolved": "✅",
    "hypothesis": "💡",
    "result": "📊",
    "decision": "🎯",
    "reference": "📚",
}


# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_structure():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    TRACES_DIR.mkdir(exist_ok=True)
    if not INDEX_FILE.exists():
        save_yaml_atomic(INDEX_FILE, {"traces": {}, "counter": 0})


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s\-가-힣]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    s = s.strip("-")
    return s[:40] if s else "trace"


def make_id(name: str, explicit_id: str | None = None) -> str:
    if explicit_id:
        return explicit_id
    date = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(name)
    # 이미 존재하면 -NN suffix
    idx = load_yaml(INDEX_FILE) or {"traces": {}}
    base = f"trace-{date}-{slug}"
    if base not in idx.get("traces", {}):
        return base
    for i in range(2, 100):
        candidate = f"{base}-{i:02d}"
        if candidate not in idx["traces"]:
            return candidate
    return f"{base}-{datetime.now().strftime('%H%M%S')}"


def trace_path(trace_id: str) -> Path:
    return TRACES_DIR / f"{trace_id}.md"


def load_index() -> dict:
    ensure_structure()
    return load_yaml(INDEX_FILE) or {"traces": {}, "counter": 0}


def get_active_trace() -> str | None:
    if not ACTIVE_FILE.exists():
        return None
    try:
        val = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        return val if val else None
    except Exception:
        return None


def set_active_trace(trace_id: str | None):
    ensure_structure()
    with file_lock(ACTIVE_FILE):
        if trace_id:
            atomic_write(ACTIVE_FILE, trace_id)
        else:
            atomic_write(ACTIVE_FILE, "")


def trace_exists(trace_id: str) -> bool:
    return trace_path(trace_id).exists()


# ────────────────────────────── 섹션 파싱 ──────────────────────────────


SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def parse_sections(content: str) -> list[dict]:
    """Markdown 문서를 ## 섹션 단위로 분할.

    Returns [{"title": "...", "body": "...", "offset": int}]
    첫 ## 이전의 내용은 "_header"로 레이블.
    """
    sections = []
    matches = list(SECTION_RE.finditer(content))

    # 헤더 (첫 ## 이전)
    if matches:
        header_end = matches[0].start()
        if header_end > 0:
            header_body = content[:header_end].strip()
            if header_body:
                sections.append({
                    "title": "_header",
                    "body": header_body,
                    "offset": 0,
                })
    else:
        # ## 없음 — 전체가 헤더
        return [{"title": "_header", "body": content.strip(), "offset": 0}]

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        sections.append({
            "title": title,
            "body": body,
            "offset": m.start(),
        })

    return sections


# ────────────────────────────── start ──────────────────────────────


def cmd_start(args):
    ensure_structure()

    trace_id = make_id(args.name, args.id)
    if trace_exists(trace_id):
        sys.stderr.write(f"❌ 이미 존재: {trace_id}\n")
        sys.exit(1)

    # Campaign 자동 감지
    campaign_id = args.campaign
    if not campaign_id:
        try:
            active_file = Path(".claude/campaigns/_active.yaml")
            if active_file.exists():
                data = load_yaml(active_file)
                campaign_id = data.get("focus")
        except Exception:
            pass

    created_iso = now_iso()
    header = f"""# Trace: {args.name}

- **Trace ID**: `{trace_id}`
- **Started**: {created_iso}
- **Campaign**: {campaign_id or '_(none)_'}
- **Status**: active
"""
    if args.description:
        header += f"- **Description**: {args.description}\n"
    header += f"\n## {datetime.now().strftime('%H:%M')} — 시작\n\n"
    if args.description:
        header += f"{args.description}\n\n"
    else:
        header += f"{args.name} 작업 시작.\n\n"

    with file_lock(trace_path(trace_id)):
        atomic_write(trace_path(trace_id), header)

    # 인덱스 갱신
    with read_modify_write(INDEX_FILE) as idx:
        idx.setdefault("traces", {})[trace_id] = {
            "name": args.name,
            "campaign": campaign_id,
            "started": created_iso,
            "ended": None,
            "status": "active",
            "description": args.description or "",
            "section_count": 1,
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
        }
        idx["counter"] = idx.get("counter", 0) + 1

    # 자동으로 active 설정 (--no-activate 옵션으로 바꿀 수 있음)
    if not args.no_activate:
        set_active_trace(trace_id)

    # 임베딩 색인 (헤더 포함)
    try:
        embeddings_store.index_document(
            "traces", trace_id,
            f"{args.name}\n{args.description or ''}"
        )
    except Exception as e:
        sys.stderr.write(f"⚠️  임베딩 색인 실패 (무시하고 계속): {e}\n")

    print(f"✅ Trace 시작: {trace_id}")
    print(f"   이름:      {args.name}")
    print(f"   Campaign:  {campaign_id or '(none)'}")
    print(f"   파일:      {trace_path(trace_id)}")
    if not args.no_activate:
        print(f"   → active trace로 설정됨")


# ────────────────────────────── append ──────────────────────────────


def cmd_append(args):
    ensure_structure()

    trace_id = args.id or get_active_trace()
    if not trace_id:
        sys.stderr.write(
            "❌ 활성 trace 없음. `start`로 시작하거나 --id 지정.\n"
        )
        sys.exit(1)
    if not trace_exists(trace_id):
        sys.stderr.write(f"❌ trace 파일 없음: {trace_id}\n")
        sys.exit(1)

    # 섹션 타이틀 구성
    icon = ICON_MAP.get(args.kind or "note", "•")
    timestamp = datetime.now().strftime("%H:%M")
    if args.title:
        section_title = f"## {timestamp} {icon} {args.title}"
    else:
        section_title = f"## {timestamp} {icon} {args.kind or 'note'}"

    content_block = f"\n{section_title}\n\n{args.content}\n"

    # O_APPEND로 atomic append
    append_line_atomic(trace_path(trace_id), content_block)

    # 인덱스 업데이트
    with read_modify_write(INDEX_FILE) as idx:
        if trace_id in idx.get("traces", {}):
            idx["traces"][trace_id]["section_count"] = \
                idx["traces"][trace_id].get("section_count", 0) + 1
            idx["traces"][trace_id]["last_append"] = now_iso()

    # 섹션 단위 임베딩 색인 (retrieval 시 섹션 정확도 향상)
    try:
        section_id = f"{trace_id}::{datetime.now().strftime('%H%M%S')}"
        embeddings_store.index_document(
            "trace_sections", section_id,
            f"{args.title or args.kind or ''}: {args.content[:1000]}"
        )
    except Exception:
        pass

    print(f"✅ [{trace_id}] {icon} 섹션 추가: {args.title or args.kind or 'note'}")


# ────────────────────────────── end ──────────────────────────────


def cmd_end(args):
    ensure_structure()
    trace_id = args.id or get_active_trace()
    if not trace_id:
        sys.stderr.write("❌ active trace 없음\n")
        sys.exit(1)
    if not trace_exists(trace_id):
        sys.stderr.write(f"❌ trace 파일 없음: {trace_id}\n")
        sys.exit(1)

    # 종료 섹션 추가
    summary = args.summary or "작업 완료"
    end_block = (
        f"\n## {datetime.now().strftime('%H:%M')} ✅ 종료\n\n"
        f"{summary}\n"
    )
    append_line_atomic(trace_path(trace_id), end_block)

    # 인덱스 업데이트
    with read_modify_write(INDEX_FILE) as idx:
        if trace_id in idx.get("traces", {}):
            idx["traces"][trace_id]["ended"] = now_iso()
            idx["traces"][trace_id]["status"] = "ended"
            idx["traces"][trace_id]["end_summary"] = summary

    # active 해제
    if get_active_trace() == trace_id:
        set_active_trace(None)

    print(f"✅ Trace 종료: {trace_id}")

    # ── Step 2: LLM 압축 자동 호출 ──
    if not args.no_compress:
        try:
            import compression_worker
            print(f"🔄 LLM 압축 중... ({args.backend})")
            result = compression_worker.compress_trace(
                trace_id,
                llm_backend=args.backend,
                timeout=args.timeout,
            )
            status = result.get("status")
            if status == "success":
                print(f"✅ 압축 완료:")
                if result.get("summary"):
                    print(f"   요약:      {result['summary']}")
                print(f"   instincts: 신규 {len(result.get('instincts_added', []))}, "
                      f"갱신 {len(result.get('instincts_updated', []))}")
                if result.get('pending_review'):
                    print(f"   structured: decisions {result.get('decisions_pending', 0)} / facts {result.get('facts_pending', 0)} → review 대기")
                    print(f"   승인:      python scripts/compression_worker.py apply-pending {trace_id}")
                else:
                    print(f"   decisions: {result.get('decisions_added', 0)}")
                    print(f"   facts:     {result.get('facts_added', 0)}")
            elif status == "queued":
                print(f"⚠️  압축 실패 → 큐에 등록: {result.get('reason')}")
                print(f"   나중에 재시도: python scripts/compression_worker.py retry-queue")
            else:
                print(f"⚠️  압축 오류: {result.get('reason')}")
        except ImportError:
            print(f"   (compression_worker.py 없음, 압축 스킵)")
        except Exception as e:
            print(f"   ⚠️ 압축 중 예외 (trace는 보존됨): {e}")


# ────────────────────────────── list ──────────────────────────────


def cmd_list(args):
    ensure_structure()
    idx = load_index()
    traces = idx.get("traces", {})
    active = get_active_trace()

    if args.format == "json":
        print(json.dumps(
            {"traces": traces, "active": active},
            ensure_ascii=False, indent=2
        ))
        return

    if not traces:
        print("ℹ️  trace 없음")
        return

    filtered = traces.items()
    if args.active:
        filtered = [(tid, info) for tid, info in filtered
                    if info.get("status") == "active"]
    if args.campaign:
        filtered = [(tid, info) for tid, info in filtered
                    if info.get("campaign") == args.campaign]

    filtered = sorted(filtered,
                      key=lambda x: x[1].get("started", ""),
                      reverse=True)

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📝 Trace 목록 ({len(filtered)}건)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for tid, info in filtered:
        marker = "⭐" if tid == active else (
            "🔄" if info.get("status") == "active" else "✔"
        )
        camp = info.get("campaign") or "-"
        print(f"{marker} {tid}")
        print(f"    이름:       {info.get('name')}")
        print(f"    campaign:   {camp}")
        print(f"    status:     {info.get('status')}")
        print(f"    섹션 수:    {info.get('section_count', '?')}")
        print(f"    시작:       {info.get('started', '-')[:16]}")
        print()


# ────────────────────────────── show ──────────────────────────────


def cmd_show(args):
    if not trace_exists(args.id):
        sys.stderr.write(f"❌ trace 없음: {args.id}\n")
        sys.exit(1)

    content = trace_path(args.id).read_text(encoding="utf-8")
    if args.sections_only:
        sections = parse_sections(content)
        for s in sections:
            if s["title"] == "_header":
                continue
            print(f"  • {s['title']}  ({len(s['body'])} chars)")
        return

    print(content)


# ────────────────────────────── retrieve (핵심) ──────────────────────────────


def cmd_retrieve(args):
    """쿼리 → 관련 trace 또는 섹션 반환. Step 1의 핵심 기능."""
    ensure_structure()
    query = args.query

    if args.scope == "sections":
        # 섹션 단위 검색 (더 세밀)
        results = embeddings_store.hybrid_search(
            query, "trace_sections", top_k=args.top,
            semantic_weight=args.semantic_weight,
        )
    else:
        # trace 단위 검색
        results = embeddings_store.hybrid_search(
            query, "traces", top_k=args.top,
            semantic_weight=args.semantic_weight,
        )

    # 결과 풀어서 문맥 제공
    output = {
        "query": query,
        "scope": args.scope,
        "semantic_backend": embeddings_store.semantic_backend_name(),
        "results": [],
    }

    idx = load_index()
    for item_id, score, debug in results:
        if args.scope == "sections":
            # item_id = "{trace_id}::{timestamp}"
            trace_id = item_id.split("::", 1)[0]
            # 섹션 내용을 원본 파일에서 추출 필요 (여기선 최근 N자)
            output["results"].append({
                "section_id": item_id,
                "trace_id": trace_id,
                "trace_name": idx["traces"].get(trace_id, {}).get("name"),
                "score": round(score, 4),
                "debug": debug,
            })
        else:
            trace_info = idx["traces"].get(item_id, {})
            # 전문 대신 헤더 + 섹션 목록
            content = trace_path(item_id).read_text(encoding="utf-8") \
                if trace_exists(item_id) else ""
            sections = parse_sections(content)
            output["results"].append({
                "trace_id": item_id,
                "name": trace_info.get("name"),
                "status": trace_info.get("status"),
                "campaign": trace_info.get("campaign"),
                "section_count": len([s for s in sections if s["title"] != "_header"]),
                "section_titles": [s["title"] for s in sections
                                   if s["title"] != "_header"][:5],
                "score": round(score, 4),
                "debug": debug,
            })

    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # text 모드
    if not output["results"]:
        print(f"ℹ️  '{query}'에 맞는 {args.scope} 없음")
        print(f"   semantic backend: {output['semantic_backend']}")
        return

    print(f"\n🔍 '{query}' 검색 결과 ({len(output['results'])}건)")
    print(f"   semantic backend: {output['semantic_backend']}")
    print(f"   scope: {args.scope}\n")
    for i, r in enumerate(output["results"], 1):
        if args.scope == "sections":
            print(f"  {i}. [{r['score']}] {r['trace_name']}")
            print(f"     trace: {r['trace_id']}")
            print(f"     section: {r['section_id'].split('::')[-1]}")
        else:
            print(f"  {i}. [{r['score']}] {r['name']}  ({r['trace_id']})")
            print(f"     status: {r['status']}, sections: {r['section_count']}")
            if r["section_titles"]:
                for st in r["section_titles"][:3]:
                    print(f"       · {st[:60]}")
            print(f"     → 전문: trace_manager.py show {r['trace_id']}")
        print()


# ────────────────────────────── status ──────────────────────────────


def cmd_status(args):
    active = get_active_trace()
    if not active:
        print("ℹ️  active trace 없음")
        return

    idx = load_index()
    info = idx.get("traces", {}).get(active, {})

    if args.format == "json":
        print(json.dumps({"active": active, "info": info},
                         ensure_ascii=False, indent=2))
        return

    print(f"\n📝 Active trace: {active}")
    print(f"   이름:        {info.get('name')}")
    print(f"   campaign:    {info.get('campaign') or '-'}")
    print(f"   시작:        {info.get('started', '-')[:16]}")
    print(f"   섹션 수:     {info.get('section_count', '?')}")
    print(f"   status:      {info.get('status')}")


# ────────────────────────────── switch ──────────────────────────────


def cmd_switch(args):
    if not trace_exists(args.id):
        sys.stderr.write(f"❌ trace 없음: {args.id}\n")
        sys.exit(1)
    set_active_trace(args.id)
    print(f"✅ active trace → {args.id}")


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Trace Manager — 풀 실험 노트 + 하이브리드 검색",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # start
    sp = sub.add_parser("start", help="새 trace 시작")
    sp.add_argument("name")
    sp.add_argument("--id", help="명시적 ID (기본: trace-YYYY-MM-DD-slug)")
    sp.add_argument("--campaign", help="연동할 캠페인 ID (미지정 시 자동 감지)")
    sp.add_argument("--description")
    sp.add_argument("--tags")
    sp.add_argument("--no-activate", action="store_true",
                    help="active trace로 설정 안 함")

    # append
    ap = sub.add_parser("append", help="섹션 추가")
    ap.add_argument("content", help="섹션 내용")
    ap.add_argument("--id", help="특정 trace (기본: active)")
    ap.add_argument("--title", help="섹션 제목")
    ap.add_argument(
        "--kind",
        choices=list(ICON_MAP.keys()),
        default="note",
        help=f"섹션 유형 ({', '.join(ICON_MAP.keys())})"
    )

    # end
    ep = sub.add_parser("end", help="trace 종료 + 자동 LLM 압축")
    ep.add_argument("id", nargs="?", help="생략 시 active")
    ep.add_argument("--summary", help="종료 요약")
    ep.add_argument("--no-compress", action="store_true",
                    help="LLM 압축 건너뛰기")
    ep.add_argument("--backend", choices=["claude", "codex", "mock"],
                    default="claude",
                    help="압축에 쓸 LLM (기본: claude)")
    ep.add_argument("--timeout", type=float, default=60.0)

    # list
    lp = sub.add_parser("list", help="trace 목록")
    lp.add_argument("--active", action="store_true",
                    help="active 상태만")
    lp.add_argument("--campaign", help="특정 캠페인만")
    lp.add_argument("--format", choices=["text", "json"], default="text")

    # show
    shp = sub.add_parser("show", help="trace 전문 조회")
    shp.add_argument("id")
    shp.add_argument("--sections-only", action="store_true",
                     help="섹션 제목만")

    # retrieve (핵심)
    rp = sub.add_parser("retrieve", help="하이브리드 검색")
    rp.add_argument("query")
    rp.add_argument("--top", type=int, default=5)
    rp.add_argument("--scope", choices=["traces", "sections"],
                    default="traces")
    rp.add_argument("--semantic-weight", type=float, default=0.5,
                    dest="semantic_weight")
    rp.add_argument("--format", choices=["text", "json"], default="text")

    # status
    stp = sub.add_parser("status", help="active trace 상태")
    stp.add_argument("--format", choices=["text", "json"], default="text")

    # switch
    swp = sub.add_parser("switch", help="active 전환")
    swp.add_argument("id")

    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        "start": cmd_start, "append": cmd_append, "end": cmd_end,
        "list": cmd_list, "show": cmd_show, "retrieve": cmd_retrieve,
        "status": cmd_status, "switch": cmd_switch,
    }
    fn = dispatch.get(args.cmd)
    if not fn:
        sys.stderr.write(f"❌ 명령 없음: {args.cmd}\n")
        sys.exit(1)
    fn(args)


if __name__ == "__main__":
    main()
