#!/usr/bin/env python3
"""
campaign_manager.py v2 — 장기 연구 캠페인 영속성 관리

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v1 → v2 변화 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
* state.json (JSON) → campaign.yaml (YAML, 주석 가능)
* LATEST 단일 포인터 → _active.yaml 다중 활성 지원
* decisions-log.md → progress.md (시간순 append-only)
* phase 개념 도입 (research / plan / approval / implement / verify / done)
* 🆕 continue 명령 — 재개 브리핑 자동 생성
* 🆕 switch 명령 — 다중 활성 캠페인 간 전환
* 🆕 archive 명령 — 완료 캠페인 아카이브

파일 구조:
  .claude/campaigns/
  ├── _index.yaml                  # 전체 캠페인 목록 (id, name, status, phase, ...)
  ├── _active.yaml                 # 현재 활성 id 목록 + 포커스
  ├── _archive/                    # 아카이브된 캠페인 (이동됨)
  ├── {camp-id}/
  │   ├── campaign.yaml            # 메타 (phase, status, timestamps, ...)
  │   ├── progress.md              # 시간순 진행 일지 (append-only)
  │   ├── checkpoints/             # phase 완료 스냅샷
  │   │   └── {timestamp}-{phase}.yaml
  │   └── artifacts/               # 연구 산출물 (RESEARCH.md, PLAN.md, ...)

v1 호환:
  기존 state.json / LATEST / decisions-log.md는 첫 실행 시 자동 마이그레이션.
  resume, log 명령은 deprecated alias로 유지.

의존성: harness_common.py (같은 디렉토리)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, read_modify_write, save_yaml_atomic, atomic_write,
        load_yaml, append_line_atomic, HAS_YAML, now_iso,
    )
except ImportError:
    sys.stderr.write("❌ harness_common.py가 같은 디렉토리에 필요합니다.\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요: pip install pyyaml --break-system-packages\n")
    sys.exit(1)


# ────────────────────────────── 경로 / 상수 ──────────────────────────────

CAMPAIGNS_DIR = Path(".claude/campaigns")
INDEX_FILE = CAMPAIGNS_DIR / "_index.yaml"
ACTIVE_FILE = CAMPAIGNS_DIR / "_active.yaml"
ARCHIVE_DIR = CAMPAIGNS_DIR / "_archive"

# bootstrap이 생성하는 디렉토리
AGENTS_DIR = Path(".claude/agents")
INSTINCTS_DIR = Path(".claude/instincts")
CONVENTIONS_DIR = INSTINCTS_DIR / "conventions"
ANTI_PATTERNS_DIR = INSTINCTS_DIR / "anti_patterns"

# v1 호환 경로
V1_LATEST = CAMPAIGNS_DIR / "LATEST"

# Phase 정의 (연구용)
PHASES = ["research", "plan", "approval", "implement", "verify", "done"]
PHASE_DESCRIPTIONS = {
    "research": "STEP 1-2 — 전문가 분석 + RESEARCH.md 작성",
    "plan": "STEP 3 — PLAN.md 작성",
    "approval": "STEP 4 — 사용자 검토 및 승인 대기",
    "implement": "STEP 5 — 순차 구현 + 3단계 검증 사이클",
    "verify": "STEP 6 — 최종 통합 검토 보고서",
    "done": "완료 — 아카이브 대기",
}
PHASE_NEXT = dict(zip(PHASES, PHASES[1:]))  # research → plan → ...

STATUSES = ["active", "paused", "blocked", "done"]


# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_structure():
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    if not INDEX_FILE.exists():
        save_yaml_atomic(INDEX_FILE, {"campaigns": {}})
    if not ACTIVE_FILE.exists():
        save_yaml_atomic(ACTIVE_FILE, {"active_ids": [], "focus": None})


def slugify(text: str) -> str:
    """캠페인 이름 → 안전한 slug."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s)
    s = s.strip("-")
    return s[:40] if s else "campaign"


def make_id(name: str, explicit_id: str | None = None) -> str:
    if explicit_id:
        return explicit_id
    date = datetime.now().strftime("%Y-%m-%d")
    return f"camp-{date}-{slugify(name)}"


def campaign_dir(camp_id: str) -> Path:
    return CAMPAIGNS_DIR / camp_id


def campaign_yaml(camp_id: str) -> Path:
    return campaign_dir(camp_id) / "campaign.yaml"


def progress_file(camp_id: str) -> Path:
    return campaign_dir(camp_id) / "progress.md"


def checkpoints_dir(camp_id: str) -> Path:
    return campaign_dir(camp_id) / "checkpoints"


def artifacts_dir(camp_id: str) -> Path:
    return campaign_dir(camp_id) / "artifacts"


def approval_file(camp_id: str) -> Path:
    return campaign_dir(camp_id) / "approval.yaml"


def camp_exists(camp_id: str) -> bool:
    return campaign_yaml(camp_id).exists()


def load_index() -> dict:
    ensure_structure()
    return load_yaml(INDEX_FILE) or {"campaigns": {}}


def load_active() -> dict:
    ensure_structure()
    data = load_yaml(ACTIVE_FILE) or {}
    return {
        "active_ids": data.get("active_ids", []),
        "focus": data.get("focus"),
    }


def load_campaign(camp_id: str) -> dict:
    if not camp_exists(camp_id):
        raise FileNotFoundError(f"캠페인 없음: {camp_id}")
    return load_yaml(campaign_yaml(camp_id))


# ────────────────────────────── v1 마이그레이션 ──────────────────────────────


def migrate_v1_if_needed():
    """v1 구조(state.json, LATEST, decisions-log.md)를 v2로 이관."""
    if not CAMPAIGNS_DIR.exists():
        return
    migrated = 0
    for cdir in CAMPAIGNS_DIR.iterdir():
        if not cdir.is_dir() or cdir.name.startswith("_"):
            continue
        state_json = cdir / "state.json"
        if not state_json.exists():
            continue  # 이미 v2이거나 무관 디렉토리
        camp_yaml = cdir / "campaign.yaml"
        if camp_yaml.exists():
            continue  # 이미 마이그레이션됨

        # 변환
        try:
            state = json.loads(state_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        new_campaign = {
            "id": state.get("campaign_id", cdir.name),
            "name": state.get("name", cdir.name),
            "phase": "research",  # v1 step을 phase로 근사 매핑 어려움 → 기본
            "status": "active",
            "created": state.get("created", now_iso()),
            "last_activity": state.get("last_update", now_iso()),
            "v1_step": state.get("current_step"),  # 참조용 보존
            "v1_item": state.get("current_item"),
            "migrated_from_v1": True,
        }
        save_yaml_atomic(camp_yaml, new_campaign)

        # progress.md 생성 (decisions-log.md → progress.md)
        p = cdir / "progress.md"
        old_log = cdir / "decisions-log.md"
        header = f"# Progress: {new_campaign['name']}\n\n시작: {new_campaign['created']}\n\n"
        if old_log.exists():
            body = old_log.read_text(encoding="utf-8")
            atomic_write(p, header + body)
        else:
            atomic_write(p, header)

        # index 반영
        with read_modify_write(INDEX_FILE) as idx:
            idx.setdefault("campaigns", {})[new_campaign["id"]] = {
                "name": new_campaign["name"],
                "phase": new_campaign["phase"],
                "status": new_campaign["status"],
                "created": new_campaign["created"],
                "last_activity": new_campaign["last_activity"],
            }
        migrated += 1

    # LATEST → _active.yaml 포커스 이관
    if V1_LATEST.exists():
        latest = V1_LATEST.read_text(encoding="utf-8").strip()
        if latest and camp_exists(latest):
            with read_modify_write(ACTIVE_FILE) as act:
                if latest not in act.get("active_ids", []):
                    act.setdefault("active_ids", []).append(latest)
                act["focus"] = latest

    if migrated > 0:
        sys.stderr.write(f"ℹ️  v1 캠페인 {migrated}개 v2로 마이그레이션 완료\n")


# ────────────────────────────── progress.md append ──────────────────────────────


def append_progress(camp_id: str, message: str, icon: str = "•"):
    """progress.md에 시간스탬프 + 메시지 한 줄 추가. POSIX O_APPEND atomic."""
    line = f"- {icon} **{datetime.now().strftime('%Y-%m-%d %H:%M')}** — {message}"
    append_line_atomic(progress_file(camp_id), line)
    # last_activity 갱신
    with read_modify_write(campaign_yaml(camp_id)) as camp:
        camp["last_activity"] = now_iso()
    with read_modify_write(INDEX_FILE) as idx:
        if camp_id in idx.get("campaigns", {}):
            idx["campaigns"][camp_id]["last_activity"] = now_iso()


# ────────────────────────────── 명령: bootstrap ──────────────────────────────


def cmd_bootstrap(args):
    """융합 프로젝트 부트스트랩 — campaign + globals + 페어 + 용어 매핑 + anti-patterns 자동 생성.

    v2.4.7+:
    - --auto-detect: domain_detector.py 를 자동 실행하고 스캔 결과 JSON 을
      stdout 에 출력 (Claude 가 이 결과를 해석해서 다음 단계 진행).
      이 모드에서는 실제 campaign 생성 없이 스캔만 수행한다.
    - --scan-output: 스캔 결과 JSON 을 파일로도 저장.
    - 동적 도메인 지원: domain_cache.json 에서 로드된 도메인도 허용.
    """
    # 지연 import (도메인 템플릿 로드 실패 시에도 기본 start는 동작)
    try:
        from domain_templates import (
            DOMAIN_CATALOG, normalize_domain, detect_term_conflicts,
            CROSS_DOMAIN_ANTI_PATTERNS, STANDARD_PAIRS,
            render_constructive_agent, render_critical_agent,
            render_standard_agent_pair,
            # v2.4.7+
            get_domain, list_all_domains,
        )
    except ImportError as e:
        sys.stderr.write(f"❌ domain_templates 로드 실패: {e}\n")
        sys.exit(1)

    # ─────────────────────────────────────────────
    # v2.4.7+: --auto-detect 모드
    # ─────────────────────────────────────────────
    if getattr(args, "auto_detect", False):
        work_dir = Path(getattr(args, "work_dir", None) or ".").absolute()
        if not work_dir.exists():
            sys.stderr.write(f"❌ 작업 디렉토리 없음: {work_dir}\n")
            sys.exit(1)

        # domain_detector.py 를 subprocess 로 호출
        detector_path = Path(__file__).parent / "domain_detector.py"
        if not detector_path.exists():
            sys.stderr.write(
                f"❌ domain_detector.py 없음: {detector_path}\n"
                f"   v2.4.7 이상에서만 지원됩니다.\n"
            )
            sys.exit(1)

        scan_output = getattr(args, "scan_output", None) or "/tmp/domain_scan.json"
        cmd = [
            sys.executable, str(detector_path),
            str(work_dir),
            "--output", scan_output,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stderr:
                sys.stderr.write(result.stderr)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(f"❌ domain_detector 실행 실패:\n{e.stderr}\n")
            sys.exit(1)

        # 스캔 결과 로드 + 요약 출력
        with open(scan_output, "r", encoding="utf-8") as f:
            scan_data = json.load(f)

        # 사용자(또는 Claude) 에게 전달할 요약
        # v2.6+: 문서(PDF/DOCX/HWP/HWPX/IPYNB) + 폴더명 힌트 포함
        documents = scan_data.get("documents", {})
        path_hints = scan_data.get("path_domain_hints", [])

        summary = {
            "_action": "auto_detect_scan_complete",
            "_instruction": (
                "다음 단계: 이 스캔 결과를 해석하여 PRIMARY_DOMAIN 과 "
                "SECONDARY_DOMAINS 를 추론하세요. 우선순위: "
                "(1) path_domain_hints — 폴더 경로가 명시한 도메인 후보, "
                "(2) document_samples — 연구 보고서·노트북에서 추출된 본문, "
                "(3) imports + top_keywords — 코드 시그널. "
                "기존 DOMAIN_CATALOG 에 매칭되지 않는 도메인은 "
                "register_dynamic_domain() 으로 등록한 후, "
                "이 명령을 --domains <확정된_도메인_목록> 로 다시 실행하세요."
            ),
            "scan_output_path": scan_output,
            "work_dir": str(work_dir),
            "file_count": scan_data.get("file_structure", {}).get("total_files", 0),
            "total_size_mb": scan_data.get("file_structure", {}).get("total_size_mb", 0),
            "top_extensions": list(
                scan_data.get("file_structure", {}).get("extension_counts", {}).items()
            )[:5],
            "primary_imports_python": (
                scan_data.get("imports", {}).get("python", []) or []
            )[:10],
            "primary_imports_javascript": (
                scan_data.get("imports", {}).get("javascript", []) or []
            )[:10],
            "config_files_detected": list(scan_data.get("config_files", {}).keys()),
            "readme_found": bool(scan_data.get("readme")),
            "top_keywords": list(
                scan_data.get("keyword_frequency", {}).items()
            )[:15],
            # v2.6+ 신규 필드
            "path_domain_hints": path_hints,
            "documents_scanned": documents.get("files_scanned", 0),
            "documents_by_type": documents.get("files_by_type", {}),
            "document_samples": documents.get("samples", []),
            "missing_doc_libs": documents.get("missing_libs", []),
            "available_domains": list_all_domains(),
            "catalog_hints": {
                "sar": "InSAR 처리, Sentinel-1, coherence",
                "ai": "pytorch, tensorflow, scikit-learn",
                "volcanology": "화산 분화, 지구물리",
            },
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return  # auto-detect 모드는 여기서 종료

    migrate_v1_if_needed()
    ensure_structure()

    # 도메인 정규화 + 미지원 도메인 확인 (v2.4.7: 동적 도메인도 허용)
    raw_domains = [d.strip() for d in (args.domains or "").split(",") if d.strip()]
    if not raw_domains:
        sys.stderr.write(
            "❌ --domains 가 필요합니다 (예: --domains sar,ai,volcanology)\n"
            "   도메인을 모르면 먼저 --auto-detect 로 스캔하세요:\n"
            "   python scripts/campaign_manager.py bootstrap --auto-detect --work-dir .\n"
        )
        sys.exit(1)

    domain_keys: list[str] = []
    unknown: list[str] = []
    for raw in raw_domains:
        key = normalize_domain(raw)
        # v2.4.7+: get_domain() 은 정적+동적 통합 조회
        if key and get_domain(key) is not None:
            if key not in domain_keys:
                domain_keys.append(key)
        else:
            unknown.append(raw)
    if unknown:
        sys.stderr.write(
            f"❌ 지원하지 않는 도메인: {unknown}\n"
            f"   전체 사용 가능 도메인: {list_all_domains()}\n"
            f"   필요하면:\n"
            f"     1) scripts/domain_templates.py 에 정적 추가, 또는\n"
            f"     2) register_dynamic_domain() 으로 동적 등록\n"
        )
        sys.exit(1)

    # campaign 생성 (cmd_start 로직 재사용)
    camp_id = make_id(args.name, args.id)
    if camp_exists(camp_id):
        sys.stderr.write(f"❌ 이미 존재하는 캠페인: {camp_id}\n")
        sys.exit(1)
    cdir = campaign_dir(camp_id)
    cdir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir(camp_id).mkdir(exist_ok=True)
    artifacts_dir(camp_id).mkdir(exist_ok=True)
    campaign = {
        "id": camp_id,
        "name": args.name,
        "phase": "research",
        "status": "active",
        "created": now_iso(),
        "last_activity": now_iso(),
        "deadline": args.deadline,
        "tags": args.tags.split(",") if args.tags else [],
        "description": args.description or "",
        "bootstrapped": True,
        "domains": domain_keys,
    }
    with file_lock(campaign_yaml(camp_id)):
        save_yaml_atomic(campaign_yaml(camp_id), campaign)
    header = (
        f"# Progress: {args.name}\n\n"
        f"- **Campaign ID**: `{camp_id}`\n"
        f"- **Domains**: {', '.join((get_domain(d) or {}).get('display', d) for d in domain_keys)}\n"
        f"- **Output**: {args.output_type or '(지정 안 됨)'}\n"
        f"- **Bootstrapped**: {campaign['created']}\n\n"
        f"## 진행 기록\n"
    )
    with file_lock(progress_file(camp_id)):
        atomic_write(progress_file(camp_id), header)
    append_progress(camp_id, f"bootstrap: {len(domain_keys)} 도메인 + 표준 페어", icon="🚀")

    # globals.yaml — 도메인별 assumption·primary/secondary 자동 설정
    primary = DOMAIN_CATALOG[domain_keys[0]]["display"]
    secondary = [(get_domain(k) or {}).get("display", k) for k in domain_keys[1:]]
    all_assumptions = {}
    for k in domain_keys:
        all_assumptions[k] = (get_domain(k) or {}).get("assumptions", [])
    globals_yaml = {
        "PROJECT_NAME": args.name,
        "PRIMARY_DOMAIN": primary,
        "SECONDARY_DOMAINS": secondary,
        "OUTPUT_TYPE": args.output_type or "",
        "SOLO_RESEARCHER": True,
        "MIN_PAIRS": max(4, len(domain_keys) + 2),  # 도메인 + lead + qa
        "MAX_PAIRS": 8,
        "DOMAIN_ASSUMPTIONS": all_assumptions,
    }
    globals_path = cdir / "globals.yaml"
    save_yaml_atomic(globals_path, globals_yaml)

    # assumptions.yaml — 각 도메인 critical checklist도 포함
    assumptions_payload = {
        "note": "도메인별 기본 가정 + 비판적 검토 체크리스트. x-* 페어가 도전할 대상.",
        "created": now_iso(),
        "domains": {
            k: {
                "display": (get_domain(k) or {}).get("display", k),
                "assumptions": (get_domain(k) or {}).get("assumptions", []),
                "critical_review_checklist": (get_domain(k) or {}).get("critical_review_checklist", []),
            }
            for k in domain_keys
        },
    }
    assumptions_path = cdir / "assumptions.yaml"
    save_yaml_atomic(assumptions_path, assumptions_payload)

    # 에이전트 .md 생성
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    created_agents: list[str] = []

    # (a) 도메인별 c-/x- 페어
    # v2.5.0: composite 모드에서는 Composite 엔진이 대신 생성 (건너뜀)
    if not getattr(args, "composite", False):
        for k in domain_keys:
            dd = get_domain(k) or {}
            kind = dd["agent_kind"]
            c_md = render_constructive_agent(
                kind, dd["pair_id"], dd["display"], args.name,
                dd.get("assumptions", []), dd.get("key_terms", {}),
            )
            x_md = render_critical_agent(
                kind, dd["pair_id"], dd["display"], args.name,
                dd.get("critical_review_checklist", []), dd.get("key_terms", {}),
            )
            c_path = AGENTS_DIR / f"c-{kind}.md"
            x_path = AGENTS_DIR / f"x-{kind}.md"
            if not c_path.exists() or args.overwrite:
                atomic_write(c_path, c_md) ; created_agents.append(c_path.name)
            if not x_path.exists() or args.overwrite:
                atomic_write(x_path, x_md) ; created_agents.append(x_path.name)

    # v2.5.0+: Composite Architecture 모드
    # --composite 가 지정되면 6 패턴 전부 생성 (36 에이전트)
    # 지정되지 않으면 기존 v2.4.7 방식 (도메인 페어 + 표준 4 페어)
    if getattr(args, "composite", False):
        try:
            from domain_templates import render_composite_agents
        except ImportError as e:
            sys.stderr.write(f"❌ Composite 모드 요구: {e}\n")
            sys.exit(1)
        composite_result = render_composite_agents(
            domains=domain_keys,
            project_name=args.name,
            persist_dir=AGENTS_DIR,
        )
        created_agents.extend(composite_result.keys())
        sys.stdout.write(
            f"✅ Composite Architecture 활성: "
            f"{len(composite_result)} 에이전트 (6 패턴) 생성\n"
        )
    else:
        # v2.4.7 기존 방식 (하위 호환)
        # (b) 표준 페어 (lead/dev/qa/methods)
        for kind, pair_id, role, c_duties, x_duties in STANDARD_PAIRS:
            c_md, x_md = render_standard_agent_pair(kind, pair_id, role, args.name, c_duties, x_duties)
            c_path = AGENTS_DIR / f"c-{kind}.md"
            x_path = AGENTS_DIR / f"x-{kind}.md"
            if not c_path.exists() or args.overwrite:
                atomic_write(c_path, c_md) ; created_agents.append(c_path.name)
            if not x_path.exists() or args.overwrite:
                atomic_write(x_path, x_md) ; created_agents.append(x_path.name)

    # 용어 충돌 자동 감지 → conventions/domain-terminology-map.yaml
    conflicts = detect_term_conflicts(domain_keys)
    CONVENTIONS_DIR.mkdir(parents=True, exist_ok=True)
    term_map_payload = {
        "id": "domain-terminology-map",
        "version": 1,
        "category": "conventions",
        "note": "같은 용어가 도메인마다 다른 의미를 가질 때 맥락 명시 필수",
        "created": now_iso(),
        "domains": domain_keys,
        "conflicts": conflicts,
        "rule": "수치를 쓸 때 반드시 어느 도메인 맥락인지 명시한다. 예: 'AI classification accuracy: 92%'",
    }
    save_yaml_atomic(CONVENTIONS_DIR / "domain-terminology-map.yaml", term_map_payload)

    # 융합 anti-patterns → instincts/anti_patterns/cross-domain-*.yaml
    ANTI_PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
    created_ap = []
    for ap in CROSS_DOMAIN_ANTI_PATTERNS:
        ap_path = ANTI_PATTERNS_DIR / f"{ap['id']}.yaml"
        payload = {
            **ap,
            "confidence": 0.8,  # 융합 연구 경험칙은 바로 confirmed 수준
            "evidence": [{
                "date": datetime.now().date().isoformat(),
                "observation": f"bootstrap: {args.name} 프로젝트 초기 주입",
                "type": "seed",
                "source": f"campaign/{camp_id}",
            }],
            "metadata": {
                "created": now_iso(),
                "updated": now_iso(),
                "review_status": "confirmed",
                "detected_by": ["bootstrap"],
            },
        }
        if not ap_path.exists() or args.overwrite:
            save_yaml_atomic(ap_path, payload) ; created_ap.append(ap_path.name)

    # _index / _active 갱신
    with read_modify_write(INDEX_FILE) as idx:
        idx.setdefault("campaigns", {})[camp_id] = {
            "name": args.name,
            "phase": "research",
            "status": "active",
            "created": campaign["created"],
            "last_activity": campaign["last_activity"],
            "domains": domain_keys,
        }
    with read_modify_write(ACTIVE_FILE) as act:
        act.setdefault("active_ids", [])
        if camp_id not in act["active_ids"]:
            act["active_ids"].append(camp_id)
        act["focus"] = camp_id

    # 결과 출력
    print(f"✅ 융합 프로젝트 부트스트랩 완료: {camp_id}")
    print(f"   이름: {args.name}")
    print(f"   도메인: {', '.join((get_domain(d) or {}).get('display', d) for d in domain_keys)}")
    print(f"   생성 파일:")
    print(f"     • {globals_path}")
    print(f"     • {assumptions_path}")
    print(f"     • .claude/agents/ — {len(created_agents)}개 에이전트")
    print(f"     • .claude/instincts/conventions/domain-terminology-map.yaml"
          f" ({len(conflicts)}개 용어 충돌 감지)")
    print(f"     • .claude/instincts/anti_patterns/ — {len(created_ap)}개 융합 anti-pattern")
    if conflicts:
        print(f"")
        print(f"   ⚠️  감지된 용어 충돌:")
        for term, defs in conflicts.items():
            print(f"      - '{term}': {', '.join(defs.keys())}")
        print(f"      → 메타 블록에서 수치 쓸 때 도메인 맥락 명시 필수")


# ────────────────────────────── 명령: start ──────────────────────────────


def cmd_start(args):
    migrate_v1_if_needed()
    ensure_structure()

    camp_id = make_id(args.name, args.id)
    if camp_exists(camp_id):
        sys.stderr.write(f"❌ 이미 존재하는 캠페인: {camp_id}\n")
        sys.stderr.write(f"   --id 로 다른 ID 지정하거나 status/continue 사용\n")
        sys.exit(1)

    # 디렉토리 구조 생성
    cdir = campaign_dir(camp_id)
    cdir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir(camp_id).mkdir(exist_ok=True)
    artifacts_dir(camp_id).mkdir(exist_ok=True)

    # campaign.yaml 생성
    campaign = {
        "id": camp_id,
        "name": args.name,
        "phase": args.phase or "research",
        "status": "active",
        "created": now_iso(),
        "last_activity": now_iso(),
        "deadline": args.deadline,
        "tags": args.tags.split(",") if args.tags else [],
        "description": args.description or "",
    }
    with file_lock(campaign_yaml(camp_id)):
        save_yaml_atomic(campaign_yaml(camp_id), campaign)

    # progress.md 초기화
    header = (
        f"# Progress: {args.name}\n\n"
        f"- **Campaign ID**: `{camp_id}`\n"
        f"- **시작일**: {campaign['created']}\n"
        f"- **Phase**: {campaign['phase']} — {PHASE_DESCRIPTIONS[campaign['phase']]}\n\n"
        f"## 진행 기록\n"
    )
    with file_lock(progress_file(camp_id)):
        atomic_write(progress_file(camp_id), header)

    append_progress(camp_id, f"캠페인 시작 (phase: {campaign['phase']})", icon="🚀")

    # _index.yaml 갱신
    with read_modify_write(INDEX_FILE) as idx:
        idx.setdefault("campaigns", {})[camp_id] = {
            "name": args.name,
            "phase": campaign["phase"],
            "status": "active",
            "created": campaign["created"],
            "last_activity": campaign["last_activity"],
        }

    # _active.yaml에 추가 + focus
    with read_modify_write(ACTIVE_FILE) as act:
        act.setdefault("active_ids", [])
        if camp_id not in act["active_ids"]:
            act["active_ids"].append(camp_id)
        act["focus"] = camp_id

    print(f"✅ 캠페인 시작: {camp_id}")
    print(f"   이름: {args.name}")
    print(f"   경로: {cdir}")
    print(f"   Phase: {campaign['phase']} — {PHASE_DESCRIPTIONS[campaign['phase']]}")


# ────────────────────────────── 명령: continue (핵심!) ──────────────────────────────


def cmd_continue(args):
    """활성 캠페인 재개 — 재개 브리핑 자동 생성."""
    migrate_v1_if_needed()
    ensure_structure()

    target_id = args.id
    if not target_id:
        # 활성 캠페인 중 포커스, 없으면 가장 최근 활동
        active = load_active()
        target_id = active.get("focus")
        if not target_id and active.get("active_ids"):
            # 가장 최근 활동 캠페인
            idx = load_index()
            candidates = [(cid, idx["campaigns"].get(cid, {}).get("last_activity", ""))
                          for cid in active["active_ids"]]
            candidates.sort(key=lambda x: x[1], reverse=True)
            target_id = candidates[0][0] if candidates else None

    if not target_id:
        print("❌ 활성 캠페인 없음. 'start'로 시작하거나 'list'로 확인.")
        sys.exit(1)

    if not camp_exists(target_id):
        sys.stderr.write(f"❌ 캠페인 없음: {target_id}\n")
        sys.exit(1)

    # 브리핑 생성
    briefing = build_briefing(target_id)
    print(briefing)

    # 포커스 갱신
    with read_modify_write(ACTIVE_FILE) as act:
        act["focus"] = target_id
        if target_id not in act.get("active_ids", []):
            act.setdefault("active_ids", []).append(target_id)

    append_progress(target_id, "세션 재개 (continue 명령)", icon="🔄")


def build_briefing(camp_id: str) -> str:
    """재개 브리핑 생성 — continue의 핵심 가치."""
    camp = load_campaign(camp_id)
    last_act = camp.get("last_activity", camp["created"])

    # 경과 시간 계산
    try:
        last_dt = datetime.fromisoformat(last_act)
        elapsed = datetime.now() - last_dt
        if elapsed.days >= 1:
            elapsed_str = f"{elapsed.days}일 {elapsed.seconds // 3600}시간"
        elif elapsed.seconds >= 3600:
            elapsed_str = f"{elapsed.seconds // 3600}시간 {(elapsed.seconds % 3600) // 60}분"
        else:
            elapsed_str = f"{elapsed.seconds // 60}분"
    except ValueError:
        elapsed_str = "알 수 없음"

    # 완료된 checkpoint
    cp_dir = checkpoints_dir(camp_id)
    checkpoints = []
    if cp_dir.exists():
        for cp in sorted(cp_dir.glob("*.yaml")):
            cp_data = load_yaml(cp)
            checkpoints.append({
                "file": cp.name,
                "phase": cp_data.get("phase", "?"),
                "timestamp": cp_data.get("timestamp", cp.stem),
            })

    # progress.md 마지막 5개 라인
    progress_tail = _read_progress_tail(camp_id, n=5)

    # 다음 할 일 추정
    next_hint = _guess_next_action(camp)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 캠페인 재개 — {camp_id}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"이름:        {camp['name']}",
        f"시작일:      {camp['created'][:16]}",
        f"경과:        {elapsed_str} (마지막 활동: {last_act[:16]})",
        f"현재 Phase:  {camp['phase']} — {PHASE_DESCRIPTIONS.get(camp['phase'], '?')}",
        f"Status:      {camp['status']}",
    ]
    if camp.get("deadline"):
        lines.append(f"마감:        {camp['deadline']}")
    if camp.get("tags"):
        lines.append(f"태그:        {', '.join(camp['tags'])}")
    lines.append("")

    if checkpoints:
        lines.append("✅ 완료된 Checkpoint:")
        for cp in checkpoints:
            lines.append(f"    • {cp['phase']} ({cp['timestamp']})")
        lines.append("")

    if progress_tail:
        lines.append("📝 최근 진행 기록 (progress.md):")
        for line in progress_tail:
            lines.append(f"    {line}")
        lines.append("")

    lines.append(f"💡 다음 할 일: {next_hint}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def _read_progress_tail(camp_id: str, n: int = 5) -> list[str]:
    p = progress_file(camp_id)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    # "- 🚀 ...", "- ✅ ..." 같은 진행 기록 줄만 추출
    entries = [l for l in lines if l.startswith("- ")]
    return entries[-n:]


def _guess_next_action(camp: dict) -> str:
    phase = camp.get("phase", "research")
    hints = {
        "research": "STEP 1~2 이어서 진행 → RESEARCH.md 완료 → `checkpoint research`",
        "plan": "PLAN.md 마무리 → `checkpoint plan` → approval 단계 진입",
        "approval": "사용자 검토 대기 중. 승인 후 `approve` → `checkpoint approval`",
        "implement": "다음 task 진행 → 각 task 완료 시 `progress '...'` 기록",
        "verify": "최종 검토 보고서 작성 → 완료 시 `checkpoint verify`",
        "done": "`archive` 로 아카이브",
    }
    return hints.get(phase, "`status`로 현재 상태 확인")


# ────────────────────────────── 명령: progress ──────────────────────────────


def cmd_progress(args):
    migrate_v1_if_needed()
    ensure_structure()

    camp_id = args.id or load_active().get("focus")
    if not camp_id:
        sys.stderr.write("❌ 활성 캠페인 focus 없음. --id 지정 또는 먼저 `continue` 실행.\n")
        sys.exit(1)
    if not camp_exists(camp_id):
        sys.stderr.write(f"❌ 캠페인 없음: {camp_id}\n")
        sys.exit(1)

    icon = args.icon or "•"
    append_progress(camp_id, args.message, icon=icon)
    print(f"✅ [{camp_id}] progress 기록")


# ────────────────────────────── 명령: checkpoint ──────────────────────────────


def _check_step25_pre_plan(camp_id: str, camp: dict) -> str | None:
    """v2.6.3: STEP 2.5 (pre-plan extended cross-pair) 게이트.

    research → plan 전환 시 호출. 통과 조건:
      - skip_step25 플래그 (수동 스킵)
      - 도메인 페어 ≤ 1 (라운드로빈 의미 없음 → 자동 스킵)
      - .claude/runtime/challenges/*-pre-plan-manifest.yaml 존재 + 모두 완료

    실패 시 사용자에게 다음 명령을 안내한다.
    """
    if camp.get("skip_step25"):
        return None

    # 도메인 수 추정 — campaign.yaml 의 domains 배열 또는 globals
    domains = camp.get("domains") or camp.get("globals", {}).get("domains", [])
    if not isinstance(domains, list):
        domains = []
    if len(domains) <= 1:
        # 단일 도메인이면 라운드로빈 무의미 → 자동 스킵
        return None

    challenges_dir = Path(".claude/runtime/challenges")
    if not challenges_dir.exists():
        return _step25_help_message(domains)

    pre_plan = list(challenges_dir.glob("*-pre-plan-manifest.yaml"))
    if not pre_plan:
        return _step25_help_message(domains)

    # 가장 최근 매니페스트 완료 여부
    latest = max(pre_plan, key=lambda p: p.stat().st_mtime)
    m = load_yaml(latest) or {}
    completed = m.get("completed", 0)
    total = m.get("total_challenges", 0)
    if completed != total:
        pending = [c for c in m.get("challenges", [])
                   if c.get("status") != "completed"]
        pending_summary = ", ".join(
            f"{c['challenger']}→{c['target']}" for c in pending[:3]
        )
        return (
            f"STEP 2.5 미완료: {completed}/{total} 도전 완료. "
            f"미완료: {pending_summary}{'...' if len(pending) > 3 else ''}\n"
            f"   완료 후 `verify --phase pre-plan --strict` 통과 필요. --force 로 우회 가능."
        )
    return None


def _step25_help_message(domains: list) -> str:
    pairs_hint = ",".join(f"PAIR-{d.upper()}" for d in domains[:3])
    return (
        "STEP 2.5 (pre-plan extended cross-pair) 미실행. PLAN.md 진입 전 강제.\n"
        f"   다음 명령 실행:\n"
        f"     python scripts/challenge_manager.py plan \\\n"
        f"       --scope extended --phase pre-plan \\\n"
        f"       --pairs 'PAIR-LEAD,PAIR-DEV,PAIR-QA,PAIR-METHODS,{pairs_hint}'\n"
        f"   (모든 도전 record 후)\n"
        f"     python scripts/challenge_manager.py verify --phase pre-plan --strict\n"
        f"   스킵 옵션: campaign.yaml 에 skip_step25: true 추가 또는 checkpoint --force"
    )


def _checkpoint_precondition_error(camp_id: str, camp: dict, phase: str) -> str | None:
    artifacts = artifacts_dir(camp_id)
    if phase == "research":
        if not (artifacts / "RESEARCH.md").exists():
            return "research checkpoint 전 artifacts/RESEARCH.md 가 필요합니다. 없으면 --force 사용"
        # v2.6.3: STEP 2.5 게이트 (research → plan 전환 시 자동 트리거)
        step25_err = _check_step25_pre_plan(camp_id, camp)
        if step25_err:
            return step25_err
    elif phase == "plan":
        if not (artifacts / "PLAN.md").exists():
            return "plan checkpoint 전 artifacts/PLAN.md 가 필요합니다. 없으면 --force 사용"
    elif phase == "approval":
        approval = load_yaml(approval_file(camp_id)) or {}
        if not approval.get("approved"):
            return "approval checkpoint 전 `approve` 명령으로 승인 기록이 필요합니다. 없으면 --force 사용"
    elif phase == "implement":
        if not artifacts.exists() or not any(artifacts.iterdir()):
            return "implement checkpoint 전 artifacts/ 에 최소 1개 산출물이 필요합니다. 없으면 --force 사용"
    return None


def cmd_checkpoint(args):
    migrate_v1_if_needed()
    ensure_structure()

    camp_id = args.id or load_active().get("focus")
    if not camp_id:
        sys.stderr.write("❌ 활성 캠페인 focus 없음.\n")
        sys.exit(1)
    if not camp_exists(camp_id):
        sys.stderr.write(f"❌ 캠페인 없음: {camp_id}\n")
        sys.exit(1)

    camp = load_campaign(camp_id)
    phase = args.phase or camp["phase"]
    if phase not in PHASES:
        sys.stderr.write(f"❌ 지원 안 되는 phase: {phase}\n   지원: {PHASES}\n")
        sys.exit(1)

    current_phase = camp.get("phase", "research")
    if phase != current_phase and not args.force:
        sys.stderr.write(
            f"❌ 현재 phase는 {current_phase} 입니다. `{phase}` checkpoint로 점프할 수 없습니다.\n"
            f"   phase 일치가 필요하며, 강제하려면 --force 사용\n"
        )
        sys.exit(1)

    if not args.force:
        err = _checkpoint_precondition_error(camp_id, camp, phase)
        if err:
            sys.stderr.write(f"❌ {err}\n")
            sys.exit(1)

    # 스냅샷 저장
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cp_file = checkpoints_dir(camp_id) / f"{timestamp}-{phase}.yaml"
    cp_data = {
        "timestamp": now_iso(),
        "phase": phase,
        "label": args.label or "",
        "snapshot": dict(camp),
    }
    with file_lock(cp_file):
        save_yaml_atomic(cp_file, cp_data)

    # phase 전환
    next_phase = PHASE_NEXT.get(phase)
    with read_modify_write(campaign_yaml(camp_id)) as c:
        c["last_activity"] = now_iso()
        if next_phase and not args.no_advance:
            c["phase"] = next_phase
            if next_phase == "done":
                c["status"] = "done"

    with read_modify_write(INDEX_FILE) as idx:
        if camp_id in idx.get("campaigns", {}):
            idx["campaigns"][camp_id]["last_activity"] = now_iso()
            if next_phase and not args.no_advance:
                idx["campaigns"][camp_id]["phase"] = next_phase
                if next_phase == "done":
                    idx["campaigns"][camp_id]["status"] = "done"

    msg = f"Checkpoint 저장: {phase}"
    if args.label:
        msg += f" ({args.label})"
    append_progress(camp_id, msg, icon="✅")

    print(f"✅ [{camp_id}] checkpoint: {phase}" + (f" ({args.label})" if args.label else ""))
    if next_phase and not args.no_advance:
        print(f"   → phase 전환: {phase} → {next_phase}")
    elif args.no_advance:
        print(f"   (--no-advance로 phase 유지)")


# ────────────────────────────── 명령: approve ──────────────────────────────


def cmd_approve(args):
    migrate_v1_if_needed()
    ensure_structure()

    camp_id = args.id or load_active().get("focus")
    if not camp_id:
        sys.stderr.write("❌ 활성 캠페인 focus 없음. --id 지정 또는 먼저 `continue` 실행.\n")
        sys.exit(1)
    if not camp_exists(camp_id):
        sys.stderr.write(f"❌ 캠페인 없음: {camp_id}\n")
        sys.exit(1)

    approval = {
        "approved": True,
        "approved_by": args.by or "user",
        "note": args.note or "",
        "timestamp": now_iso(),
    }
    save_yaml_atomic(approval_file(camp_id), approval)
    append_progress(camp_id, f"승인 기록됨 (by={approval['approved_by']})", icon="📝")
    print(f"✅ [{camp_id}] approval recorded")


# ────────────────────────────── 명령: status ──────────────────────────────


def cmd_status(args):
    migrate_v1_if_needed()
    ensure_structure()

    camp_id = args.id or load_active().get("focus")
    if not camp_id:
        # 활성 없음 — 전체 요약
        idx = load_index()
        if not idx.get("campaigns"):
            print("ℹ️  활성 캠페인 없음")
            return
        print(f"ℹ️  focus 설정 없음. 활성 캠페인 {len(idx['campaigns'])}개:")
        for cid, info in idx["campaigns"].items():
            print(f"   • {cid} — phase: {info.get('phase')}, status: {info.get('status')}")
        return

    if args.format == "json":
        print(json.dumps({
            "campaign": load_campaign(camp_id),
            "briefing": None,
        }, ensure_ascii=False, indent=2, default=str))
        return

    print(build_briefing(camp_id))


# ────────────────────────────── 명령: switch ──────────────────────────────


def cmd_switch(args):
    migrate_v1_if_needed()
    ensure_structure()

    if not camp_exists(args.id):
        sys.stderr.write(f"❌ 캠페인 없음: {args.id}\n")
        sys.exit(1)

    with read_modify_write(ACTIVE_FILE) as act:
        act.setdefault("active_ids", [])
        if args.id not in act["active_ids"]:
            act["active_ids"].append(args.id)
        act["focus"] = args.id

    append_progress(args.id, f"focus 전환됨", icon="🎯")
    print(f"✅ focus → {args.id}")
    print(build_briefing(args.id))


# ────────────────────────────── 명령: archive ──────────────────────────────


def cmd_archive(args):
    ensure_structure()
    if not camp_exists(args.id):
        sys.stderr.write(f"❌ 캠페인 없음: {args.id}\n")
        sys.exit(1)

    cdir = campaign_dir(args.id)
    target = ARCHIVE_DIR / args.id
    if target.exists():
        sys.stderr.write(f"❌ 이미 아카이브됨: {target}\n")
        sys.exit(1)

    # status를 done으로 변경한 뒤 이동
    with read_modify_write(campaign_yaml(args.id)) as c:
        c["status"] = "done"
        c["archived_at"] = now_iso()

    # 디렉토리 이동 (OS-level)
    import shutil
    shutil.move(str(cdir), str(target))

    # index에서 제거, active에서 제거
    with read_modify_write(INDEX_FILE) as idx:
        if args.id in idx.get("campaigns", {}):
            del idx["campaigns"][args.id]
    with read_modify_write(ACTIVE_FILE) as act:
        if args.id in act.get("active_ids", []):
            act["active_ids"].remove(args.id)
        if act.get("focus") == args.id:
            act["focus"] = act["active_ids"][0] if act.get("active_ids") else None

    print(f"✅ 아카이브됨: {args.id} → {target}")


# ────────────────────────────── 명령: list ──────────────────────────────


def cmd_list(args):
    migrate_v1_if_needed()
    ensure_structure()
    idx = load_index()
    active = load_active()
    campaigns = idx.get("campaigns", {})

    if args.format == "json":
        print(json.dumps({
            "campaigns": campaigns,
            "active_ids": active.get("active_ids", []),
            "focus": active.get("focus"),
        }, ensure_ascii=False, indent=2))
        return

    if not campaigns:
        print("ℹ️  캠페인 없음")
        return

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📋 캠페인 목록")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    focus = active.get("focus")
    active_ids = set(active.get("active_ids", []))
    for cid, info in sorted(campaigns.items(),
                            key=lambda x: x[1].get("last_activity", ""),
                            reverse=True):
        marker = " ⭐" if cid == focus else (" ✓" if cid in active_ids else "")
        print(f"{marker} {cid}")
        print(f"    이름:       {info.get('name')}")
        print(f"    phase:      {info.get('phase')}")
        print(f"    status:     {info.get('status')}")
        print(f"    마지막:     {info.get('last_activity', '-')[:16]}")
        print()


# ────────────────────────────── 명령: show ──────────────────────────────


def cmd_show(args):
    if not camp_exists(args.id):
        sys.stderr.write(f"❌ 캠페인 없음: {args.id}\n")
        sys.exit(1)
    camp = load_campaign(args.id)
    if args.format == "json":
        print(json.dumps(camp, ensure_ascii=False, indent=2, default=str))
        return
    print(build_briefing(args.id))


# ────────────────────────────── v1 호환 alias ──────────────────────────────


def cmd_resume(args):
    """v1 호환: resume → continue."""
    sys.stderr.write("ℹ️  'resume'은 deprecated. 대신 'continue' 사용.\n")
    args_new = argparse.Namespace(id=getattr(args, "id", None))
    return cmd_continue(args_new)


def cmd_log(args):
    """v1 호환: log → progress."""
    sys.stderr.write("ℹ️  'log'는 deprecated. 대신 'progress' 사용.\n")
    args_new = argparse.Namespace(
        id=args.id, message=args.message, icon=None,
    )
    return cmd_progress(args_new)


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Campaign Manager v2 — 장기 연구 영속성",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # bootstrap (융합 프로젝트 자동 구성)
    bs = sub.add_parser("bootstrap",
                        help="융합 프로젝트 부트스트랩 — campaign + globals + agents + 용어 매핑 자동 생성")
    bs.add_argument("name", nargs="?", default=None,
                    help="프로젝트 이름 (예: 'SAR+AI로 화산 분화 조기 경보'). "
                         "--auto-detect 모드에서는 생략 가능.")
    bs.add_argument("--domains", default=None,
                    help="쉼표로 구분 (예: sar,ai,volcanology). "
                         "지원: 정적 카탈로그 + 동적 등록 도메인. "
                         "모르면 먼저 --auto-detect 로 스캔하세요.")
    bs.add_argument("--auto-detect", action="store_true",
                    help="[v2.4.7+] 프로젝트 폴더를 스캔하여 도메인 판별용 "
                         "JSON 출력. 이 모드에서는 campaign 생성 안 함. "
                         "스캔 결과를 해석한 뒤 --domains 로 다시 실행하세요.")
    bs.add_argument("--work-dir", default=None,
                    help="[v2.4.7+] --auto-detect 시 스캔할 프로젝트 루트 "
                         "(기본: 현재 디렉토리)")
    bs.add_argument("--composite", action="store_true",
                    help="[v2.5.0+] Composite Architecture 활성화 — "
                         "6 패턴 (core/investigation/expert_pool/debate/pipeline/hierarchical) "
                         "전부 생성 (~36 에이전트). 대규모 복합 프로젝트 권장.")
    bs.add_argument("--scan-output", default=None,
                    help="[v2.4.7+] --auto-detect 스캔 결과 JSON 저장 경로 "
                         "(기본: /tmp/domain_scan.json)")
    bs.add_argument("--output-type", default="",
                    help="산출물 유형 (예: 'ATBD + 논문 + Python 구현')")
    bs.add_argument("--id", help="명시적 캠페인 ID")
    bs.add_argument("--deadline", help="YYYY-MM-DD")
    bs.add_argument("--tags", help="쉼표 구분 태그")
    bs.add_argument("--description", help="간단한 설명")
    bs.add_argument("--overwrite", action="store_true",
                    help="기존 에이전트 .md / anti-pattern이 있어도 덮어씀")

    # start
    sp = sub.add_parser("start", help="새 캠페인 시작")
    sp.add_argument("name", help="사람이 읽기 쉬운 이름")
    sp.add_argument("--id", help="명시적 ID (기본: camp-YYYY-MM-DD-slug)")
    sp.add_argument("--phase", choices=PHASES, help="시작 phase (기본: research)")
    sp.add_argument("--deadline", help="YYYY-MM-DD 형식")
    sp.add_argument("--tags", help="쉼표로 구분된 태그")
    sp.add_argument("--description", help="간단한 설명")

    # continue (핵심)
    cp = sub.add_parser("continue", help="활성 캠페인 재개 + 브리핑 생성")
    cp.add_argument("id", nargs="?", help="ID 생략 시 focus 또는 최근 활동")

    # progress
    pg = sub.add_parser("progress", help="진행 기록 한 줄 추가")
    pg.add_argument("message")
    pg.add_argument("--id", help="ID 생략 시 focus")
    pg.add_argument("--icon", help="이모지 (기본: •)")

    # checkpoint
    ck = sub.add_parser("checkpoint", help="phase 완료 스냅샷 + 다음 phase")
    ck.add_argument("phase", nargs="?", choices=PHASES,
                    help="생략 시 현재 phase")
    ck.add_argument("--id", help="ID 생략 시 focus")
    ck.add_argument("--label", help="설명 라벨")
    ck.add_argument("--no-advance", action="store_true",
                    help="phase 전환 없이 스냅샷만")
    ck.add_argument("--force", action="store_true",
                    help="phase 점프/선행조건 미충족이어도 강제")

    # approve
    ap = sub.add_parser("approve", help="approval phase 진입을 위한 사용자 승인 기록")
    ap.add_argument("--id", help="ID 생략 시 focus")
    ap.add_argument("--by", help="승인 주체 (기본: user)")
    ap.add_argument("--note", help="승인 메모")

    # status
    st = sub.add_parser("status", help="현재 focus 캠페인 브리핑")
    st.add_argument("id", nargs="?")
    st.add_argument("--format", choices=["text", "json"], default="text")

    # switch
    sw = sub.add_parser("switch", help="다른 캠페인으로 focus 전환")
    sw.add_argument("id")

    # archive
    ar = sub.add_parser("archive", help="완료 캠페인 아카이브")
    ar.add_argument("id")

    # list
    ls = sub.add_parser("list", help="전체 캠페인 목록")
    ls.add_argument("--format", choices=["text", "json"], default="text")

    # show
    sh = sub.add_parser("show", help="특정 캠페인 상세")
    sh.add_argument("id")
    sh.add_argument("--format", choices=["text", "json"], default="text")

    # v1 deprecated aliases
    rs = sub.add_parser("resume", help="(deprecated) continue 사용")
    rs.add_argument("id", nargs="?")
    lg = sub.add_parser("log", help="(deprecated) progress 사용")
    lg.add_argument("id")
    lg.add_argument("message")

    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        "bootstrap": cmd_bootstrap,
        "start": cmd_start, "continue": cmd_continue,
        "progress": cmd_progress, "checkpoint": cmd_checkpoint,
        "approve": cmd_approve,
        "status": cmd_status, "switch": cmd_switch,
        "archive": cmd_archive, "list": cmd_list,
        "show": cmd_show,
        "resume": cmd_resume, "log": cmd_log,
    }
    fn = dispatch.get(args.cmd)
    if not fn:
        sys.stderr.write(f"❌ 지원 안 되는 명령: {args.cmd}\n")
        sys.exit(1)
    fn(args)


if __name__ == "__main__":
    main()
