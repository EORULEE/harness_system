#!/usr/bin/env python3
"""
instincts_updater.py v2 — ECC-inspired research instincts system

ECC의 Trigger-Action-Evidence 패턴 + confidence scoring + import/export를
연구 프로젝트에 맞게 각색한 구현. SQLite 대신 YAML 파일 기반.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
.claude/instincts/
├── _meta.yaml                             # 전체 인덱스, 통계, 설정
├── SCHEMA.md                              # 스키마 레퍼런스
├── domain_knowledge/                      # 도메인 사실 기반 패턴
│   └── {id}.yaml
├── methodology/                           # 실험·검증·통계 방법
│   └── {id}.yaml
├── anti_patterns/                         # 피해야 할 접근
│   └── {id}.yaml
├── conventions/                           # 프로젝트 내부 약속
│   └── {id}.yaml
└── _archive/                              # 낮은 신뢰도·오래된
    └── {id}.yaml

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
주요 명령
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  record    — 신규 instinct 생성 또는 기존에 evidence 추가
  match     — 쿼리에 관련된 instinct 검색 (에이전트가 사용)
  list      — 카테고리·태그·신뢰도 필터
  show      — 단일 instinct 상세 출력
  export    — 전체를 단일 YAML 번들로 내보내기 (팀 공유)
  import    — 다른 프로젝트 번들 가져오기
  prune     — 오래된 또는 낮은 신뢰도 archive로 이동
  migrate   — v1 patterns.md → v2 YAML 변환 (1회성)
  stats     — 요약 통계

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Confidence 규칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - 초기값: 0.5 (neutral)
  - Evidence 확증: +0.1 (상한 0.95)
  - Evidence 모순: −0.15 (하한 0.0)
  - 0.8+ 자동 review_status: confirmed
  - 0.3 미만: disputed, prune 대상
  - 최소 적용 권장: 0.5 이상

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
의존성: pyyaml
  pip install pyyaml --break-system-packages
"""

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# 공용 동시성 유틸 import (같은 디렉토리)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, read_modify_write, save_yaml_atomic, load_yaml,
        HAS_YAML, today_str,
    )
except ImportError:
    sys.stderr.write("❌ harness_common.py가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요: pip install pyyaml --break-system-packages\n")
    sys.exit(1)

import yaml  # show 명령에서 직접 yaml.safe_dump 사용

# Step 1: 하이브리드 검색 (옵션, 실패해도 기존 기능 작동)
try:
    import embeddings_store
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False


# ────────────────────────────── 설정 ──────────────────────────────

INSTINCTS_DIR = Path(".claude/instincts")
META_FILE = INSTINCTS_DIR / "_meta.yaml"
ARCHIVE_DIR = INSTINCTS_DIR / "_archive"

CATEGORIES = ["domain_knowledge", "methodology", "anti_patterns", "conventions"]

# 카테고리 한글 설명 (ls / stats에 사용)
CAT_DESC = {
    "domain_knowledge": "도메인 지식 — 반복 관측된 도메인 사실 기반 패턴",
    "methodology": "방법론 — 실험·검증·통계·재현성 관련 원칙",
    "anti_patterns": "안티패턴 — 피해야 할 접근",
    "conventions": "컨벤션 — 프로젝트 내부 약속 (네이밍·경로·포맷)",
}

DEFAULT_META = {
    "version": 2,
    "schema": "ecc-inspired-research-v2",
    "total_instincts": 0,
    "last_updated": None,
    "confidence_threshold_active": 0.3,
    "archive_threshold_days": 180,
    "categories": {c: {"count": 0, "description": CAT_DESC[c]} for c in CATEGORIES},
}

# Confidence 조정 상수
CONF_INITIAL = 0.5
CONF_CONFIRM_DELTA = 0.10
CONF_CONTRADICT_DELTA = -0.15
CONF_MAX = 0.95
CONF_MIN = 0.0
CONF_AUTO_CONFIRM = 0.8
CONF_AUTO_DISPUTE = 0.3

# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_structure():
    """기본 디렉토리 + 메타 생성. 매 명령 시작에 호출."""
    INSTINCTS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    for cat in CATEGORIES:
        (INSTINCTS_DIR / cat).mkdir(exist_ok=True)
    if not META_FILE.exists():
        save_yaml(META_FILE, DEFAULT_META)


# save_yaml은 harness_common의 atomic 버전으로 alias
# (기존 호출부를 모두 그대로 사용하면서 원자적 쓰기 보장)
save_yaml = save_yaml_atomic


def make_id(raw: str) -> str:
    """인간 가독 ID — 영숫자/한글/하이픈만 유지"""
    slug = re.sub(r"[^\w\-가-힣]+", "-", raw.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80]


def iter_instincts(include_archive: bool = False):
    """활성 instinct YAML 순회. (category, path, data) tuple."""
    for cat in CATEGORIES:
        cat_dir = INSTINCTS_DIR / cat
        if not cat_dir.exists():
            continue
        for f in sorted(cat_dir.glob("*.yaml")):
            try:
                yield cat, f, load_yaml(f)
            except yaml.YAMLError as e:
                sys.stderr.write(f"⚠️  YAML 파싱 오류 {f}: {e}\n")
    if include_archive and ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.yaml")):
            try:
                data = load_yaml(f)
                yield data.get("category", "unknown"), f, data
            except yaml.YAMLError:
                continue


def find_instinct(instinct_id: str):
    """ID로 instinct 찾기. 활성 + 아카이브 모두 검색."""
    for cat, f, data in iter_instincts(include_archive=True):
        if data.get("id") == instinct_id:
            return cat, f, data
    return None, None, None


def update_meta():
    """메타 인덱스 갱신."""
    meta = load_yaml(META_FILE) if META_FILE.exists() else dict(DEFAULT_META)
    counts: Counter = Counter()
    total = 0
    for cat, _, _ in iter_instincts():
        counts[cat] += 1
        total += 1
    meta["total_instincts"] = total
    meta["last_updated"] = datetime.now().isoformat(timespec="seconds")
    for cat in CATEGORIES:
        meta.setdefault("categories", {}).setdefault(
            cat, {"description": CAT_DESC[cat]}
        )["count"] = counts.get(cat, 0)
    save_yaml(META_FILE, meta)


def today() -> str:
    return today_str()


def clamp_conf(val: float) -> float:
    # 부동소수점 누적 오차 방지를 위해 소수 2자리로 정규화
    return round(max(CONF_MIN, min(CONF_MAX, val)), 2)


# ────────────────────────────── 명령: record ──────────────────────────────


def cmd_record(args):
    """신규 instinct 생성 또는 기존 evidence 추가.

    동시성: 같은 ID에 대한 병렬 쓰기는 file_lock으로 직렬화.
    신규 생성 시 double-check로 race 방지.
    """
    ensure_structure()

    if args.legacy_positional and len(args.legacy_positional) == 5:
        return _record_v1_compat(*args.legacy_positional, args)

    if not args.id:
        sys.stderr.write("❌ --id 필요\n")
        sys.exit(1)

    instinct_id = make_id(args.id)

    # 모든 카테고리에서 기존 파일 검색
    existing_path = None
    for cat_name in CATEGORIES:
        candidate = INSTINCTS_DIR / cat_name / f"{instinct_id}.yaml"
        if candidate.exists():
            existing_path = candidate
            break

    if existing_path:
        # 기존 — read-modify-write: 락 + 로드 + 수정 + 원자적 저장
        with read_modify_write(existing_path) as data:
            _add_evidence(data, args)
            final_conf = data["confidence"]
            final_status = data["metadata"]["review_status"]
            final_cat = data.get("category", existing_path.parent.name)
        _with_meta_lock(update_meta)
        print(
            f"✅ [{final_cat}] {instinct_id} — evidence 추가 "
            f"(confidence: {final_conf:.2f}, status: {final_status})"
        )
        return

    # 신규 생성
    if not args.category:
        sys.stderr.write(f"❌ 신규 생성에는 --category 필요 ({CATEGORIES})\n")
        sys.exit(1)
    if not args.trigger or not args.action:
        sys.stderr.write("❌ 신규 생성에는 --trigger, --action 필요\n")
        sys.exit(1)

    target = INSTINCTS_DIR / args.category / f"{instinct_id}.yaml"
    with file_lock(target):
        # Double-check: 락 획득 전 race 발생 여부 확인
        if target.exists():
            sys.stderr.write(
                "ℹ️  race 감지: 다른 프로세스가 이미 생성. evidence 추가로 전환.\n"
            )
            data = load_yaml(target)
            _add_evidence(data, args)
            save_yaml_atomic(target, data)
            _with_meta_lock(update_meta)
            print(f"✅ [{args.category}] {instinct_id} — evidence 추가 "
                  f"(confidence: {data['confidence']:.2f})")
            return
        new = _new_instinct(instinct_id, args)
        save_yaml_atomic(target, new)
    _with_meta_lock(update_meta)
    # Step 1: 임베딩 색인
    if HAS_EMBEDDINGS:
        try:
            text_for_index = f"{new.get('trigger', '')}\n{new.get('action', '')}\n{new.get('notes', '')}"
            embeddings_store.index_document("instincts", instinct_id, text_for_index)
        except Exception:
            pass

    print(f"✅ 신규: [{args.category}] {instinct_id} (conf: {new['confidence']:.2f})")


def _with_meta_lock(fn):
    """메타 파일 갱신을 락으로 보호. 짧은 critical section (~5ms)."""
    with file_lock(META_FILE, timeout=5.0):
        fn()


def _new_instinct(instinct_id: str, args) -> dict:
    now = datetime.now()
    keywords = (
        [k.strip() for k in args.keywords.split(",") if k.strip()]
        if args.keywords
        else args.trigger.lower().split()[:6]
    )
    return {
        "id": instinct_id,
        "version": 1,
        "category": args.category,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
        "trigger": {
            "natural": args.trigger,
            "keywords": keywords,
            "conditions": (
                [c.strip() for c in args.conditions.split(";") if c.strip()]
                if args.conditions
                else []
            ),
        },
        "action": args.action,
        "context": {
            "symptom": args.symptom or "",
            "root_cause": args.cause or "",
        },
        "evidence": [
            {
                "date": today(),
                "campaign": args.campaign or "",
                "observation": args.evidence or args.action,
                "source": args.source or "manual",
                "type": "initial",
            }
        ],
        "confidence": CONF_INITIAL,
        "confidence_history": [
            {"date": today(), "value": CONF_INITIAL, "reason": "initial"}
        ],
        "detected_by": [args.detected_by] if args.detected_by else [],
        "related": [],
        "metadata": {
            "created": now.isoformat(timespec="seconds"),
            "updated": now.isoformat(timespec="seconds"),
            "auto_generated": False,
            "review_status": "draft",
        },
    }


def _add_evidence(instinct: dict, args):
    """기존 instinct에 evidence 추가 + confidence 재계산."""
    now = datetime.now()
    is_contradict = args.contradict
    ev = {
        "date": today(),
        "campaign": args.campaign or "",
        "observation": args.evidence or "(no details)",
        "source": args.source or "manual",
        "type": "contradiction" if is_contradict else "confirmation",
    }
    delta = CONF_CONTRADICT_DELTA if is_contradict else CONF_CONFIRM_DELTA
    old = instinct.get("confidence", CONF_INITIAL)
    new = clamp_conf(old + delta)
    instinct["confidence"] = new
    n_ev = len(instinct.get("evidence", [])) + 1
    instinct.setdefault("confidence_history", []).append({
        "date": today(), "value": new,
        "reason": ("contradicted" if is_contradict else f"+1 confirmation ({n_ev} total)"),
    })
    # review_status 자동 전이
    status = instinct.get("metadata", {}).get("review_status", "draft")
    if new >= CONF_AUTO_CONFIRM and status == "draft":
        instinct["metadata"]["review_status"] = "confirmed"
    elif new < CONF_AUTO_DISPUTE:
        instinct["metadata"]["review_status"] = "disputed"
    instinct.setdefault("evidence", []).append(ev)
    instinct["metadata"]["updated"] = now.isoformat(timespec="seconds")
    if args.detected_by:
        det = instinct.setdefault("detected_by", [])
        if args.detected_by not in det:
            det.append(args.detected_by)


def _record_v1_compat(area, name, symptom, cause, avoidance, args):
    """v1 포맷 → v2 YAML 변환. 락 보호."""
    cat_map = {"anti": "anti_patterns", "convention": "conventions"}
    category = cat_map.get(area.lower(), "domain_knowledge")
    iid = make_id(f"{area}-{name}")

    # 기존 파일 검색
    existing_path = None
    for cn in CATEGORIES:
        c = INSTINCTS_DIR / cn / f"{iid}.yaml"
        if c.exists():
            existing_path = c
            break

    if existing_path:
        with read_modify_write(existing_path) as data:
            old = data.get("confidence", CONF_INITIAL)
            data["confidence"] = clamp_conf(old + CONF_CONFIRM_DELTA)
            data.setdefault("evidence", []).append({
                "date": today(), "observation": symptom,
                "source": "v1-compat", "type": "confirmation",
            })
            data["metadata"]["updated"] = datetime.now().isoformat(timespec="seconds")
            final_conf = data["confidence"]
        _with_meta_lock(update_meta)
        print(f"✅ v1-호환 갱신: {iid} (conf: {final_conf:.2f})")
        return
    new = {
        "id": iid, "version": 1, "category": category,
        "tags": [area.lower()],
        "trigger": {
            "natural": f"{area} 영역 — {name}",
            "keywords": [area.lower()] + [w for w in name.lower().split() if w][:3],
            "conditions": [],
        },
        "action": avoidance,
        "context": {"symptom": symptom, "root_cause": cause},
        "evidence": [{
            "date": today(), "observation": symptom,
            "source": "v1-compat-initial", "type": "initial",
        }],
        "confidence": CONF_INITIAL,
        "confidence_history": [{"date": today(), "value": CONF_INITIAL, "reason": "initial (v1 compat)"}],
        "detected_by": [],
        "related": [],
        "metadata": {
            "created": datetime.now().isoformat(timespec="seconds"),
            "updated": datetime.now().isoformat(timespec="seconds"),
            "auto_generated": True, "review_status": "draft",
            "source_version": "v1-compat",
        },
    }
    target = INSTINCTS_DIR / category / f"{iid}.yaml"
    with file_lock(target):
        if target.exists():
            # race — evidence 추가로 전환
            with read_modify_write(target) as data:
                data.setdefault("evidence", []).append({
                    "date": today(), "observation": symptom,
                    "source": "v1-compat-race", "type": "confirmation",
                })
                data["confidence"] = clamp_conf(
                    data.get("confidence", CONF_INITIAL) + CONF_CONFIRM_DELTA
                )
        else:
            save_yaml_atomic(target, new)
    _with_meta_lock(update_meta)
    print(f"✅ v1→v2 변환: [{category}] {iid}")


# ────────────────────────────── 명령: match ──────────────────────────────


def cmd_match(args):
    """쿼리에 관련된 instinct 검색. 에이전트가 작업 전 호출하는 용도."""
    ensure_structure()
    # Step 1: hybrid 모드
    if HAS_EMBEDDINGS and getattr(args, "hybrid", False):
        results = embeddings_store.hybrid_search(
            args.query, "instincts", top_k=args.limit,
            semantic_weight=getattr(args, "semantic_weight", 0.5),
        )
        if not results:
            print(f"ℹ️  '{args.query}'에 맞는 instinct 없음 (hybrid)")
            return
        print(f"\n🔍 [hybrid] '{args.query}' 매칭 ({len(results)}건)")
        for iid, score, dbg in results:
            cat, fpath, data = find_instinct(iid)
            if not data:
                continue
            conf = data.get("confidence", 0)
            print(f"  [{score:.4f}] [{cat}] {iid} (conf: {conf:.2f})")
            trigger_val = data.get('trigger', '')
            if isinstance(trigger_val, dict):
                trigger_str = str(trigger_val)[:80]
            else:
                trigger_str = str(trigger_val)[:80]
            print(f"    trigger: {trigger_str}")
            print()
        return

    query = args.query.lower()
    query_words = set(re.findall(r"\w+", query))
    if not query_words:
        print("❌ 빈 쿼리")
        return
    results = []
    for cat, _, data in iter_instincts(include_archive=False):
        conf = data.get("confidence", CONF_INITIAL)
        if conf < args.min_confidence:
            continue
        if args.category and cat != args.category:
            continue
        score = _match_score(query_words, data)
        if score > 0:
            results.append((score * conf, cat, data))
    results.sort(reverse=True, key=lambda x: x[0])
    if not results:
        print(f"🔍 '{args.query}' 관련 instinct 없음 (min_conf={args.min_confidence})")
        return
    top = results[: args.limit]
    if args.format == "json":
        import json
        out = [
            {"category": c, "score": round(s, 3),
             "id": d["id"], "confidence": d["confidence"],
             "trigger": d["trigger"]["natural"], "action": d["action"]}
            for s, c, d in top
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"🔍 '{args.query}' — 관련 instincts 상위 {len(top)}개\n")
    for score, cat, data in top:
        conf = data.get("confidence", CONF_INITIAL)
        status = data.get("metadata", {}).get("review_status", "?")
        print(f"┌─ [{cat}] {data['id']}  (score: {score:.2f} | conf: {conf:.2f} | {status})")
        print(f"│  Trigger: {data['trigger']['natural'][:100]}")
        action_lines = data["action"].strip().split("\n")
        for line in action_lines[:3]:
            print(f"│  Action : {line[:100]}")
        if len(action_lines) > 3:
            print(f"│           ... (+{len(action_lines) - 3}줄)")
        print(f"└─ Evidence: {len(data.get('evidence', []))}건\n")


def _match_score(query_words: set, data: dict) -> float:
    score = 0.0
    trig = data.get("trigger", {})
    keywords = {k.lower() for k in trig.get("keywords", [])}
    tags = {t.lower() for t in data.get("tags", [])}
    nat = trig.get("natural", "").lower()
    nat_words = set(re.findall(r"\w+", nat))
    score += 2.0 * len(query_words & keywords)
    score += 1.5 * len(query_words & tags)
    score += 0.5 * len(query_words & nat_words)
    return score


# ────────────────────────────── 명령: list ──────────────────────────────


def cmd_list(args):
    ensure_structure()
    items = list(iter_instincts(include_archive=args.archive))
    if args.category:
        items = [x for x in items if x[0] == args.category]
    if args.min_confidence is not None:
        items = [x for x in items if x[2].get("confidence", CONF_INITIAL) >= args.min_confidence]
    if args.tag:
        tag = args.tag.lower()
        items = [x for x in items if tag in [t.lower() for t in x[2].get("tags", [])]]
    if not items:
        print("📭 조건에 맞는 instinct 없음")
        return
    by_cat: dict = {}
    for c, _, d in items:
        by_cat.setdefault(c, []).append(d)
    print(f"📋 Instincts 총 {len(items)}개\n")
    for cat in sorted(by_cat):
        lst = sorted(by_cat[cat], key=lambda x: -x.get("confidence", CONF_INITIAL))
        print(f"━━ {cat} ({len(lst)}개) — {CAT_DESC.get(cat, '')}")
        for d in lst:
            conf = d.get("confidence", CONF_INITIAL)
            status = d.get("metadata", {}).get("review_status", "?")
            bar_len = int(conf * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            tags = ", ".join(d.get("tags", [])[:3])
            print(f"  {bar} {conf:.2f} [{status:10s}] {d['id']:50s} {tags}")
        print()


# ────────────────────────────── 명령: show ──────────────────────────────


def cmd_show(args):
    ensure_structure()
    _, _, data = find_instinct(args.id)
    if not data:
        print(f"❌ 없음: {args.id}")
        return
    print(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))


# ────────────────────────────── 명령: export / import ──────────────────────────────


def cmd_export(args):
    ensure_structure()
    bundle = {
        "bundle_version": 1,
        "exported": datetime.now().isoformat(timespec="seconds"),
        "source_project": Path.cwd().name,
        "instincts": [d for _, _, d in iter_instincts(include_archive=args.include_archive)],
    }
    out = Path(args.output or f"instincts-export-{datetime.now().strftime('%Y%m%d')}.yaml")
    save_yaml(out, bundle)
    print(f"✅ 내보내기: {out} ({len(bundle['instincts'])}개)")


def cmd_import(args):
    ensure_structure()
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        sys.stderr.write(f"❌ 번들 없음: {bundle_path}\n")
        sys.exit(1)
    bundle = load_yaml(bundle_path)
    imported = bundle.get("instincts", [])
    added, merged, skipped = 0, 0, 0
    for ins in imported:
        iid = ins.get("id")
        cat = ins.get("category", "domain_knowledge")
        if cat not in CATEGORIES:
            cat = "domain_knowledge"
            ins["category"] = cat
        _, existing_file, existing = find_instinct(iid)
        if existing and not args.overwrite:
            if args.merge:
                with read_modify_write(existing_file) as data:
                    data.setdefault("evidence", []).extend(ins.get("evidence", []))
                    data["metadata"]["updated"] = datetime.now().isoformat(timespec="seconds")
                    data["metadata"]["merged_from"] = str(bundle_path)
                merged += 1
            else:
                skipped += 1
            continue
        target = INSTINCTS_DIR / cat / f"{iid}.yaml"
        with file_lock(target):
            save_yaml_atomic(target, ins)
        added += 1
    _with_meta_lock(update_meta)
    print(f"✅ 가져오기: 신규 {added} / 병합 {merged} / 건너뜀 {skipped}")


# ────────────────────────────── 명령: prune ──────────────────────────────


def cmd_prune(args):
    ensure_structure()
    meta = load_yaml(META_FILE)
    days = args.days if args.days is not None else meta.get("archive_threshold_days", 180)
    min_conf = args.min_confidence if args.min_confidence is not None else CONF_AUTO_DISPUTE
    cutoff = datetime.now() - timedelta(days=days)
    archived = 0
    for _, f, data in list(iter_instincts(include_archive=False)):
        conf = data.get("confidence", CONF_INITIAL)
        updated_str = data.get("metadata", {}).get("updated", "")
        try:
            updated = datetime.fromisoformat(updated_str)
        except ValueError:
            continue
        reason = None
        if conf < min_conf:
            reason = f"low_confidence ({conf:.2f})"
        elif updated < cutoff:
            reason = f"stale ({(datetime.now() - updated).days}일)"
        if not reason:
            continue
        if args.dry_run:
            print(f"  [DRY] {data['id']} ← {reason}")
        else:
            archive_target = ARCHIVE_DIR / f"{data['id']}.yaml"
            # 원본 파일 + 아카이브 대상 모두 락
            with file_lock(f):
                data.setdefault("metadata", {})["archived"] = datetime.now().isoformat(timespec="seconds")
                data["metadata"]["archive_reason"] = reason
                with file_lock(archive_target):
                    save_yaml_atomic(archive_target, data)
                if f.exists():
                    f.unlink()
            print(f"  ↘ 아카이브: {data['id']} ({reason})")
        archived += 1
    if not args.dry_run:
        _with_meta_lock(update_meta)
    suffix = " (dry-run)" if args.dry_run else ""
    print(f"\n✅ {archived}개 아카이브{suffix}")


# ────────────────────────────── 명령: migrate ──────────────────────────────


def cmd_migrate(args):
    ensure_structure()
    v1 = Path(".claude/instincts/patterns.md")
    if not v1.exists():
        print("ℹ️  v1 patterns.md 없음 — 마이그레이션 불필요")
        return
    content = v1.read_text(encoding="utf-8")
    blocks = re.split(r"\n## ", content)
    migrated = 0
    for block in blocks[1:]:
        m = re.match(r"\[(.*?)\]\s*-\s*(.+?)\n", block)
        if not m:
            continue
        area, name = m.group(1).strip(), m.group(2).strip()
        def grab(key: str) -> str:
            mm = re.search(rf"\*\*{key}\*\*:\s*(.+)", block)
            return mm.group(1).strip() if mm else ""
        symptom = grab("증상") or grab("Symptom") or "?"
        cause = grab("원인") or grab("Cause") or "?"
        avoidance = grab("회피법") or grab("Avoidance") or "?"
        count_m = re.search(r"\*\*발견 횟수\*\*:\s*(\d+)", block)
        count_n = int(count_m.group(1)) if count_m else 2
        cat_map = {"anti": "anti_patterns", "convention": "conventions"}
        category = cat_map.get(area.lower(), "domain_knowledge")
        iid = make_id(f"{area}-{name}")
        # count에 비례하는 initial confidence
        initial_conf = clamp_conf(0.4 + (count_n - 1) * CONF_CONFIRM_DELTA)
        now = datetime.now()
        new = {
            "id": iid, "version": 1, "category": category,
            "tags": [area.lower()],
            "trigger": {
                "natural": f"{area} 영역 — {name}",
                "keywords": [area.lower()] + [w for w in name.lower().split() if w][:3],
                "conditions": [],
            },
            "action": avoidance,
            "context": {"symptom": symptom, "root_cause": cause},
            "evidence": [{
                "date": today(), "observation": f"{count_n}회 관측 (v1 migration)",
                "source": "v1-migration", "type": "initial",
            }],
            "confidence": initial_conf,
            "confidence_history": [
                {"date": today(), "value": initial_conf, "reason": f"v1 migration (count={count_n})"}
            ],
            "detected_by": ["v1-unknown"],
            "related": [],
            "metadata": {
                "created": now.isoformat(timespec="seconds"),
                "updated": now.isoformat(timespec="seconds"),
                "auto_generated": True,
                "review_status": "confirmed" if count_n >= 3 else "draft",
                "migrated_from": "patterns.md",
            },
        }
        target = INSTINCTS_DIR / category / f"{iid}.yaml"
        with file_lock(target):
            save_yaml_atomic(target, new)
        migrated += 1
        print(f"  ↗ [{category}] {iid}")
    v1.rename(v1.with_suffix(".md.v1-backup"))
    _with_meta_lock(update_meta)
    print(f"\n✅ {migrated}개 마이그레이션 — v1 파일은 .v1-backup으로 보관")


# ────────────────────────────── 명령: stats ──────────────────────────────


def cmd_stats(args):
    ensure_structure()
    _with_meta_lock(update_meta)  # 최신 카운트 반영
    meta = load_yaml(META_FILE)
    active = list(iter_instincts(include_archive=False))
    archive_items = [
        (c, f, d) for c, f, d in iter_instincts(include_archive=True)
        if f.parent.name == "_archive"
    ]
    by_cat = Counter(c for c, _, _ in active)
    by_status = Counter(
        d.get("metadata", {}).get("review_status", "unknown") for _, _, d in active
    )
    conf_bins = {"high (≥0.8)": 0, "med (0.5–0.8)": 0, "low (<0.5)": 0}
    for _, _, d in active:
        c = d.get("confidence", CONF_INITIAL)
        if c >= 0.8:
            conf_bins["high (≥0.8)"] += 1
        elif c >= 0.5:
            conf_bins["med (0.5–0.8)"] += 1
        else:
            conf_bins["low (<0.5)"] += 1
    detect_count = Counter()
    for _, _, d in active:
        for agent in d.get("detected_by", []):
            detect_count[agent] += 1
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Instincts 통계 (v2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
활성:         {len(active)}개
아카이브:     {len(archive_items)}개
마지막 갱신:  {meta.get('last_updated', '-')}
스키마:       {meta.get('schema', '-')}
""")
    print("카테고리별 분포:")
    for cat in CATEGORIES:
        print(f"  {cat:20s} {by_cat.get(cat, 0):3d}  {CAT_DESC[cat]}")
    print("\n신뢰도 분포:")
    for k, v in conf_bins.items():
        print(f"  {k:20s} {v:3d}")
    print("\n리뷰 상태:")
    for k in ["confirmed", "draft", "disputed"]:
        print(f"  {k:20s} {by_status.get(k, 0):3d}")
    if detect_count:
        print("\n상위 탐지 에이전트:")
        for agent, n in detect_count.most_common(5):
            print(f"  {agent:20s} {n:3d}회")
    print()


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Instincts v2 — ECC-inspired research instincts system",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="새 instinct 생성 또는 evidence 추가")
    rec.add_argument("--id", help="instinct ID (신규 또는 기존)")
    rec.add_argument("--category", choices=CATEGORIES)
    rec.add_argument("--trigger", help="자연어 트리거")
    rec.add_argument("--action", help="권장 대응 (핵심 지침)")
    rec.add_argument("--keywords", help="콤마 구분 키워드")
    rec.add_argument("--tags", help="콤마 구분 태그")
    rec.add_argument("--conditions", help="세미콜론 구분 조건")
    rec.add_argument("--evidence", help="관측 사실 (evidence 추가 시)")
    rec.add_argument("--symptom", help="증상 (신규 생성 시)")
    rec.add_argument("--cause", help="근본 원인 (신규 생성 시)")
    rec.add_argument("--campaign", help="캠페인 ID")
    rec.add_argument("--source", help="출처")
    rec.add_argument("--detected-by", dest="detected_by", help="탐지 페어 (PAIR-A 등)")
    rec.add_argument("--contradict", action="store_true", help="증거가 아닌 모순")
    rec.add_argument("legacy_positional", nargs="*",
                     help="v1 호환: <area> <name> <symptom> <cause> <avoidance>")

    m = sub.add_parser("match", help="쿼리에 관련된 instincts 검색")
    m.add_argument("query")
    m.add_argument("--limit", type=int, default=5)
    m.add_argument("--min-confidence", dest="min_confidence", type=float, default=0.3)
    m.add_argument("--category", choices=CATEGORIES)
    m.add_argument("--format", choices=["text", "json"], default="text")
    m.add_argument("--hybrid", action="store_true",
                   help="하이브리드 검색(BM25+semantic)")
    m.add_argument("--semantic-weight", type=float, default=0.5,
                   dest="semantic_weight")

    ls = sub.add_parser("list", help="카테고리·태그·신뢰도 필터 목록")
    ls.add_argument("--category", choices=CATEGORIES)
    ls.add_argument("--tag")
    ls.add_argument("--min-confidence", dest="min_confidence", type=float)
    ls.add_argument("--archive", action="store_true")

    sh = sub.add_parser("show", help="단일 instinct 상세 출력")
    sh.add_argument("id")

    ex = sub.add_parser("export", help="YAML 번들 내보내기")
    ex.add_argument("--output")
    ex.add_argument("--include-archive", action="store_true", dest="include_archive")

    im = sub.add_parser("import", help="YAML 번들 가져오기")
    im.add_argument("bundle")
    im.add_argument("--overwrite", action="store_true")
    im.add_argument("--merge", action="store_true", help="evidence 병합")

    pr = sub.add_parser("prune", help="오래됐거나 낮은 confidence 아카이브")
    pr.add_argument("--days", type=int)
    pr.add_argument("--min-confidence", dest="min_confidence", type=float)
    pr.add_argument("--dry-run", action="store_true", dest="dry_run")

    sub.add_parser("migrate", help="v1 patterns.md → v2 YAML 변환")
    sub.add_parser("stats", help="요약 통계")

    return p


CMDS = {
    "record": cmd_record, "match": cmd_match, "list": cmd_list,
    "show": cmd_show, "export": cmd_export, "import": cmd_import,
    "prune": cmd_prune, "migrate": cmd_migrate, "stats": cmd_stats,
}


def main():
    args = build_parser().parse_args()
    CMDS[args.cmd](args)


if __name__ == "__main__":
    main()
