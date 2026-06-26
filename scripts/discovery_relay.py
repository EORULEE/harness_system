#!/usr/bin/env python3
"""
discovery_relay.py — 워크트리 간 중간 발견 공유

v2.4.5 변경점
- severity 자동 계산(input basis → severity)
- seq cursor 기반 읽음 상태(last_seen_seq + dismissed_ids)
- archived / file_written=false 항목 기본 숨김
- repair / archive 명령 추가
- legacy read_ids 마커와 호환
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import file_lock, read_modify_write, save_yaml_atomic, load_yaml, HAS_YAML, now_iso
except ImportError:
    sys.stderr.write("❌ harness_common.py가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요: pip install pyyaml --break-system-packages\n")
    sys.exit(1)

DISCOVERIES_DIR = Path(".claude/discoveries")
INDEX_FILE = DISCOVERIES_DIR / "_index.yaml"
READ_DIR = DISCOVERIES_DIR / "_read"
ARCHIVE_DIR = DISCOVERIES_DIR / "_archive"

BRIEF_MAX_CHARS = 2000
BRIEF_SOFT_LIMIT = 1500
SEVERITIES = ["info", "warning", "critical"]
SEVERITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def ensure_structure() -> None:
    DISCOVERIES_DIR.mkdir(parents=True, exist_ok=True)
    READ_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    if not INDEX_FILE.exists():
        save_yaml_atomic(INDEX_FILE, {"discoveries": {}, "counter": 0})


def detect_worktree_id() -> str:
    env = os.environ.get("HARNESS_WORKTREE_ID")
    if env:
        return env
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return Path(r.stdout.strip()).name or "main"
    except Exception:
        pass
    return "main"


def discovery_path(disc_id: str) -> Path:
    return DISCOVERIES_DIR / f"{disc_id}.yaml"


def archived_discovery_path(disc_id: str) -> Path:
    return ARCHIVE_DIR / f"{disc_id}.yaml"


def read_marker_path(worktree_id: str) -> Path:
    return READ_DIR / f"{worktree_id}.yaml"


def load_index() -> dict[str, Any]:
    ensure_structure()
    return load_yaml(INDEX_FILE) or {"discoveries": {}, "counter": 0}


def active_discoveries(index: dict[str, Any], include_archived: bool = False) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for did, info in (index.get("discoveries") or {}).items():
        if not info.get("file_written", True):
            continue
        if not include_archived and info.get("archived"):
            continue
        result[did] = info
    return result


def load_read_marker(worktree_id: str) -> dict[str, Any]:
    p = read_marker_path(worktree_id)
    if not p.exists():
        return {"worktree_id": worktree_id, "last_seen_seq": 0, "dismissed_ids": [], "read_ids": [], "last_check": None}
    data = load_yaml(p) or {}
    data.setdefault("worktree_id", worktree_id)
    data.setdefault("last_seen_seq", 0)
    data.setdefault("dismissed_ids", [])
    data.setdefault("read_ids", [])
    data.setdefault("last_check", None)
    return data


def save_read_marker(marker: dict[str, Any]) -> None:
    p = read_marker_path(marker["worktree_id"])
    with file_lock(p, timeout=5.0):
        save_yaml_atomic(p, marker)


def seq_of(info: dict[str, Any]) -> int:
    try:
        return int(info.get("seq", 0) or 0)
    except Exception:
        return 0


def is_read(marker: dict[str, Any], did: str, info: dict[str, Any]) -> bool:
    if did in set(marker.get("read_ids", [])):
        return True
    if did in set(marker.get("dismissed_ids", [])):
        return True
    seq = seq_of(info)
    return seq > 0 and seq <= int(marker.get("last_seen_seq", 0) or 0)


def compute_severity(args) -> tuple[str, dict[str, Any]]:
    basis = {
        "blocking": bool(getattr(args, "blocking", False)),
        "blast_radius": int(getattr(args, "blast_radius", 1) or 1),
        "rerun_cost": getattr(args, "rerun_cost", None),
        "data_risk": getattr(args, "data_risk", "none") or "none",
        "reproducibility": getattr(args, "reproducibility", "suspected") or "suspected",
    }
    if not getattr(args, "auto_severity", False):
        return args.severity, basis
    if basis["blocking"] or basis["data_risk"] == "corruption" or basis["rerun_cost"] == ">1day":
        return "critical", basis
    if basis["blast_radius"] >= 2 or basis["rerun_cost"] == ">1h" or basis["data_risk"] == "quality":
        return "warning", basis
    return "info", basis


def compose_brief(content: str, explicit_brief: str | None = None) -> tuple[str, bool]:
    if explicit_brief:
        if len(explicit_brief) > BRIEF_MAX_CHARS:
            return explicit_brief[:BRIEF_SOFT_LIMIT].rstrip() + "\n\n[truncated]", True
        return explicit_brief, False
    if len(content) <= BRIEF_MAX_CHARS:
        return content, False
    return content[:BRIEF_SOFT_LIMIT].rstrip() + "\n\n_[truncated]_", True


def reserve_discovery_id(worktree_id: str, title: str, severity: str, tags: list[str], published_at: str) -> tuple[str, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    with read_modify_write(INDEX_FILE) as idx:
        idx.setdefault("discoveries", {})
        idx.setdefault("counter", 0)
        prefix = f"disc-{today}-"
        existing = [k for k in idx["discoveries"] if k.startswith(prefix)]
        used = []
        for k in existing:
            try:
                used.append(int(k.rsplit("-", 1)[-1]))
            except ValueError:
                pass
        next_n = max(used) + 1 if used else 1
        disc_id = f"{prefix}{next_n:03d}"
        idx["counter"] = int(idx.get("counter", 0) or 0) + 1
        seq = idx["counter"]
        idx["discoveries"][disc_id] = {
            "title": title,
            "published_by": worktree_id,
            "published_at": published_at,
            "severity": severity,
            "tags": tags,
            "file_written": False,
            "archived": False,
            "seq": seq,
        }
    return disc_id, seq


def mark_file_written(disc_id: str) -> None:
    try:
        with read_modify_write(INDEX_FILE) as idx:
            if disc_id in idx.get("discoveries", {}):
                idx["discoveries"][disc_id]["file_written"] = True
    except Exception:
        pass


def load_discovery(disc_id: str) -> dict[str, Any]:
    p = discovery_path(disc_id)
    if p.exists():
        return load_yaml(p)
    ap = archived_discovery_path(disc_id)
    if ap.exists():
        return load_yaml(ap)
    raise FileNotFoundError(f"Discovery 없음: {disc_id}")


def _seq_to_id_map(index: dict[str, Any]) -> dict[int, str]:
    m: dict[int, str] = {}
    for did, info in active_discoveries(index).items():
        s = seq_of(info)
        if s:
            m[s] = did
    return m


def _mark_read_internal(worktree_id: str, disc_id: str) -> None:
    idx = load_index()
    info = (idx.get("discoveries") or {}).get(disc_id)
    if not info:
        return
    seq = seq_of(info)
    marker = load_read_marker(worktree_id)
    last_seen = int(marker.get("last_seen_seq", 0) or 0)
    dismissed = set(marker.get("dismissed_ids", []))
    legacy = set(marker.get("read_ids", []))

    if seq and seq == last_seen + 1:
        last_seen = seq
        seq_to_id = _seq_to_id_map(idx)
        while seq_to_id.get(last_seen + 1) in dismissed:
            dismissed.remove(seq_to_id[last_seen + 1])
            last_seen += 1
    elif seq and seq > last_seen + 1:
        dismissed.add(disc_id)
    elif seq and seq <= last_seen:
        pass
    else:
        dismissed.add(disc_id)

    legacy.discard(disc_id)
    marker.update({
        "last_seen_seq": last_seen,
        "dismissed_ids": sorted(dismissed),
        "read_ids": sorted(legacy),
        "last_check": now_iso(),
    })
    save_read_marker(marker)


def cmd_publish(args):
    ensure_structure()
    worktree_id = args.worktree or detect_worktree_id()
    severity, severity_basis = compute_severity(args)
    if severity not in SEVERITIES:
        sys.stderr.write(f"❌ severity는 {SEVERITIES} 중 하나\n")
        sys.exit(1)
    brief, truncated = compose_brief(args.content, args.brief)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    published_at = now_iso()
    disc_id, seq = reserve_discovery_id(worktree_id, args.title, severity, tags, published_at)
    discovery = {
        "id": disc_id,
        "seq": seq,
        "title": args.title,
        "brief": brief,
        "content": args.content if len(args.content) > BRIEF_MAX_CHARS else brief,
        "published_by": worktree_id,
        "published_at": published_at,
        "severity": severity,
        "severity_basis": severity_basis,
        "tags": tags,
        "related_campaign": args.campaign,
        "truncated": truncated,
    }
    with file_lock(discovery_path(disc_id), timeout=10.0):
        save_yaml_atomic(discovery_path(disc_id), discovery)
    mark_file_written(disc_id)
    _mark_read_internal(worktree_id, disc_id)
    print(f"✅ Discovery 게시: {SEVERITY_EMOJI[severity]} {disc_id}")
    print(f"   제목:       {args.title}")
    print(f"   워크트리:   {worktree_id}")
    print(f"   severity:   {severity}")
    if tags:
        print(f"   tags:       {', '.join(tags)}")
    if truncated:
        print(f"   ⚠️  content가 {BRIEF_MAX_CHARS}자 초과 → brief 자동 truncation")


def _filtered_discoveries(args) -> tuple[str, dict[str, Any], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    idx = load_index()
    worktree_id = args.worktree or detect_worktree_id()
    marker = load_read_marker(worktree_id)
    discoveries = active_discoveries(idx, include_archived=getattr(args, 'include_archived', False))
    filtered = []
    for did, info in discoveries.items():
        if getattr(args, 'unread', False) and is_read(marker, did, info):
            continue
        sev = getattr(args, 'severity', None)
        if sev and info.get('severity') != sev:
            continue
        from_worktree = getattr(args, 'from_worktree', None)
        if from_worktree and info.get('published_by') != from_worktree:
            continue
        tag = getattr(args, 'tag', None)
        if tag and tag not in info.get('tags', []):
            continue
        filtered.append((did, info))
    filtered.sort(key=lambda x: (SEVERITY_ORDER.get(x[1].get('severity', 'info'), 99), -seq_of(x[1]), x[0]))
    return worktree_id, marker, discoveries, filtered


def cmd_list(args):
    worktree_id, marker, discoveries, filtered = _filtered_discoveries(args)
    if args.format == 'json':
        print(json.dumps({
            'worktree_id': worktree_id,
            'filter': {
                'unread': args.unread,
                'severity': args.severity,
                'from_worktree': args.from_worktree,
                'tag': args.tag,
                'include_archived': getattr(args, 'include_archived', False),
            },
            'count': len(filtered),
            'discoveries': [{**info, 'id': did, 'is_read': is_read(marker, did, info)} for did, info in filtered],
        }, ensure_ascii=False, indent=2))
        return
    if not filtered:
        print(f"ℹ️  조건에 맞는 discovery 없음 (worktree: {worktree_id})")
        return
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📡 Discovery 목록 — {worktree_id} 관점 ({len(filtered)}건)")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for did, info in filtered:
        read_mark = '·' if is_read(marker, did, info) else '🔔'
        emoji = SEVERITY_EMOJI.get(info.get('severity', 'info'), '')
        tag_str = f" [{', '.join(info.get('tags', []))}]" if info.get('tags') else ''
        archived = ' (archived)' if info.get('archived') else ''
        print(f"{read_mark} {emoji} {did}{archived}")
        print(f"   {info.get('title', '?')}{tag_str}")
        print(f"   by: {info.get('published_by', '?')} @ {str(info.get('published_at', '?'))[:16]}  seq={seq_of(info)}")
        print()


def cmd_show(args):
    try:
        disc = load_discovery(args.id)
    except FileNotFoundError as e:
        sys.stderr.write(f"❌ {e}\n")
        sys.exit(1)
    if args.format == 'json':
        print(json.dumps(disc, ensure_ascii=False, indent=2))
        return
    emoji = SEVERITY_EMOJI.get(disc.get('severity', 'info'), '')
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"{emoji} {disc['title']}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"ID:          {disc.get('id')}")
    print(f"seq:         {disc.get('seq', '?')}")
    print(f"게시자:      {disc.get('published_by', '?')}")
    print(f"게시 시각:   {disc.get('published_at', '?')}")
    print(f"severity:    {disc.get('severity', '?')}")
    if disc.get('tags'):
        print(f"tags:        {', '.join(disc['tags'])}")
    if disc.get('related_campaign'):
        print(f"캠페인:      {disc['related_campaign']}")
    if disc.get('archived'):
        print(f"archived:    {disc.get('archived_at', '?')}")
    print()
    print('─── 내용 ───')
    print(disc.get('content', disc.get('brief', '(비어있음)')))
    print()
    if not args.no_mark_read and not disc.get('archived'):
        _mark_read_internal(args.worktree or detect_worktree_id(), args.id)


def cmd_mark_read(args):
    ensure_structure()
    worktree_id = args.worktree or detect_worktree_id()
    idx = load_index()
    discoveries = active_discoveries(idx)
    if args.all:
        max_seq = max((seq_of(info) for info in discoveries.values()), default=0)
        marker = load_read_marker(worktree_id)
        marker['last_seen_seq'] = max_seq
        marker['dismissed_ids'] = []
        marker['read_ids'] = []
        marker['last_check'] = now_iso()
        save_read_marker(marker)
        print(f"✅ 모든 discovery 읽음 처리 ({len(discoveries)}건) — worktree: {worktree_id}")
        return
    if not args.id:
        sys.stderr.write('❌ discovery ID 또는 --all 필요\n')
        sys.exit(1)
    if args.id not in idx.get('discoveries', {}):
        sys.stderr.write(f"❌ Discovery 없음: {args.id}\n")
        sys.exit(1)
    _mark_read_internal(worktree_id, args.id)
    print(f"✅ 읽음 처리: {args.id} — worktree: {worktree_id}")


def cmd_subscribe(args):
    ensure_structure()
    worktree_id = args.worktree or detect_worktree_id()
    idx = load_index()
    marker = load_read_marker(worktree_id)
    discoveries = active_discoveries(idx)
    unread = [{**info, 'id': did} for did, info in discoveries.items() if not is_read(marker, did, info)]
    unread.sort(key=lambda x: (SEVERITY_ORDER.get(x.get('severity', 'info'), 99), -seq_of(x)))
    by_severity = {s: 0 for s in SEVERITIES}
    for u in unread:
        by_severity[u.get('severity', 'info')] += 1
    marker['last_check'] = now_iso()
    save_read_marker(marker)
    result = {
        'worktree_id': worktree_id,
        'unread_count': len(unread),
        'by_severity': by_severity,
        'top_unread': unread[: args.limit],
        'hint': f"전체: python {sys.argv[0]} list --unread",
    }
    if args.format == 'json':
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not unread:
        print(f"✅ 미읽음 discovery 없음 (worktree: {worktree_id})")
        return
    print(f"\n🔔 미읽음 Discovery {len(unread)}건 — {worktree_id}")
    sev_parts = [f"{SEVERITY_EMOJI[s]} {n}" for s, n in by_severity.items() if n > 0]
    if sev_parts:
        print(f"   심각도: {'  '.join(sev_parts)}")
    print()
    for u in unread[: args.limit]:
        print(f"   {SEVERITY_EMOJI.get(u.get('severity', 'info'), '•')} {u['id']} — {u.get('title', '?')}")
        print(f"      by {u.get('published_by', '?')}")


def cmd_archive(args):
    ensure_structure()
    idx = load_index()
    cutoff = datetime.now() - timedelta(days=args.older_than_days)
    archived = []
    for did, info in list(active_discoveries(idx).items()):
        if args.severity and info.get('severity') != args.severity:
            continue
        try:
            ts = datetime.fromisoformat(str(info.get('published_at')))
        except Exception:
            continue
        if ts > cutoff:
            continue
        src = discovery_path(did)
        dst = archived_discovery_path(did)
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
            src.unlink(missing_ok=True)
        with read_modify_write(INDEX_FILE) as idx2:
            if did in idx2.get('discoveries', {}):
                idx2['discoveries'][did]['archived'] = True
                idx2['discoveries'][did]['archived_at'] = now_iso()
        archived.append(did)
    print(f"✅ archive 완료: {len(archived)}건")
    if archived[:5]:
        print(f"   예시: {', '.join(archived[:5])}")


def cmd_repair(args):
    ensure_structure()
    idx = load_index()
    repairs = {'removed_orphans': 0, 'marked_written': 0, 'compacted_markers': 0}
    for did, info in list((idx.get('discoveries') or {}).items()):
        active_file = discovery_path(did)
        archive_file = archived_discovery_path(did)
        if not active_file.exists() and not archive_file.exists():
            with read_modify_write(INDEX_FILE) as idx2:
                idx2.get('discoveries', {}).pop(did, None)
            repairs['removed_orphans'] += 1
            continue
        if not info.get('file_written', True) and (active_file.exists() or archive_file.exists()):
            with read_modify_write(INDEX_FILE) as idx2:
                if did in idx2.get('discoveries', {}):
                    idx2['discoveries'][did]['file_written'] = True
            repairs['marked_written'] += 1
    live_ids = set((load_index().get('discoveries') or {}).keys())
    for mf in READ_DIR.glob('*.yaml'):
        marker = load_yaml(mf) or {}
        marker['read_ids'] = sorted(set(marker.get('read_ids', [])) & live_ids)
        marker['dismissed_ids'] = sorted(set(marker.get('dismissed_ids', [])) & live_ids)
        save_yaml_atomic(mf, marker)
        repairs['compacted_markers'] += 1
    if args.format == 'json':
        print(json.dumps(repairs, ensure_ascii=False, indent=2))
        return
    print('✅ repair 완료')
    for k, v in repairs.items():
        print(f"   {k}: {v}")


def cmd_stats(args):
    idx = load_index()
    active = active_discoveries(idx)
    archived = {did: info for did, info in (idx.get('discoveries') or {}).items() if info.get('archived')}
    markers = {}
    for f in READ_DIR.glob('*.yaml'):
        m = load_yaml(f) or {}
        markers[m.get('worktree_id', f.stem)] = m
    current = detect_worktree_id()
    current_marker = markers.get(current, load_read_marker(current))
    unread = len([1 for did, info in active.items() if not is_read(current_marker, did, info)])
    by_severity = {s: 0 for s in SEVERITIES}
    by_publisher: dict[str, int] = {}
    for info in active.values():
        by_severity[info.get('severity', 'info')] += 1
        pub = info.get('published_by', '?')
        by_publisher[pub] = by_publisher.get(pub, 0) + 1
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 Discovery Relay 통계")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"활성 discovery:   {len(active)}")
    print(f"archived:         {len(archived)}")
    print(f"현재 워크트리:    {current}")
    print(f"내 미읽음:        {unread}")
    print()
    print('severity 분포:')
    for sev in SEVERITIES:
        cnt = by_severity.get(sev, 0)
        print(f"   {SEVERITY_EMOJI[sev]} {sev:8s} {cnt:3d}  {'█' * min(cnt, 20)}")
    print()
    print('워크트리별 게시:')
    for pub, cnt in sorted(by_publisher.items(), key=lambda x: -x[1]):
        print(f"   {pub:20s} {cnt:3d}건")
    if markers:
        print()
        print('워크트리별 읽음 상태:')
        for wt, marker in sorted(markers.items()):
            pending = len([1 for did, info in active.items() if not is_read(marker, did, info)])
            print(f"   {wt:20s} cursor={int(marker.get('last_seen_seq', 0) or 0):4d}  미읽음 {pending:3d}")


def build_parser():
    p = argparse.ArgumentParser(description='Discovery Relay — 워크트리 간 중간 발견 공유')
    sub = p.add_subparsers(dest='cmd', required=True)
    pub = sub.add_parser('publish', help='새 discovery 게시')
    pub.add_argument('title')
    pub.add_argument('content')
    pub.add_argument('--severity', choices=SEVERITIES, default='info')
    pub.add_argument('--auto-severity', action='store_true')
    pub.add_argument('--blocking', action='store_true')
    pub.add_argument('--blast-radius', type=int, default=1)
    pub.add_argument('--rerun-cost', choices=['<10m', '<1h', '>1h', '>1day'])
    pub.add_argument('--data-risk', choices=['none', 'quality', 'corruption'], default='none')
    pub.add_argument('--reproducibility', choices=['reproduced', 'suspected', 'anecdotal'], default='suspected')
    pub.add_argument('--tags')
    pub.add_argument('--campaign')
    pub.add_argument('--brief')
    pub.add_argument('--worktree')

    ls = sub.add_parser('list', help='discovery 목록')
    ls.add_argument('--unread', action='store_true')
    ls.add_argument('--severity', choices=SEVERITIES)
    ls.add_argument('--from-worktree', dest='from_worktree')
    ls.add_argument('--tag')
    ls.add_argument('--worktree')
    ls.add_argument('--include-archived', action='store_true')
    ls.add_argument('--format', choices=['text', 'json'], default='text')

    sh = sub.add_parser('show', help='discovery 상세')
    sh.add_argument('id')
    sh.add_argument('--worktree')
    sh.add_argument('--no-mark-read', action='store_true')
    sh.add_argument('--format', choices=['text', 'json'], default='text')

    mr = sub.add_parser('mark-read', help='읽음 처리')
    mr.add_argument('id', nargs='?')
    mr.add_argument('--all', action='store_true')
    mr.add_argument('--worktree')

    sb = sub.add_parser('subscribe', help='미읽음 요약')
    sb.add_argument('--worktree')
    sb.add_argument('--limit', type=int, default=5)
    sb.add_argument('--format', choices=['text', 'json'], default='text')

    ar = sub.add_parser('archive', help='오래된 discovery archive')
    ar.add_argument('--older-than-days', type=int, required=True)
    ar.add_argument('--severity', choices=SEVERITIES)

    rp = sub.add_parser('repair', help='인덱스/마커 정합성 repair')
    rp.add_argument('--format', choices=['text', 'json'], default='text')

    sub.add_parser('stats', help='전체 통계')
    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        'publish': cmd_publish,
        'list': cmd_list,
        'show': cmd_show,
        'mark-read': cmd_mark_read,
        'subscribe': cmd_subscribe,
        'archive': cmd_archive,
        'repair': cmd_repair,
        'stats': cmd_stats,
    }
    dispatch[args.cmd](args)


if __name__ == '__main__':
    main()
