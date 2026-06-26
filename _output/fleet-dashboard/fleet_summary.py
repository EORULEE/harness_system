#!/usr/bin/env python3
"""fleet_summary.py — 머신별 읽기전용 하네스 수집기 (fleet-dashboard 계약 AC1/AC2/AC9).

각 머신에서 실행 → fleet-summary.json 1개를 자기 홈(또는 --out)에 생성.
- stdlib만 사용 (외부 의존성 0).
- 읽기전용: 자기 출력 json 1개 외에 어떤 파일도 생성/수정하지 않음.
- secret 미수집: 자격증명은 "있음/없음" bool로만 (kb.env의 API key 등 값 미기록).

사용:
  python3 fleet_summary.py --machine <machine> \
      --project <PROJECT_ROOT> \
      --project "<PATH>/06_2026/4_journal/fusion" \
      [--out /path/fleet-summary.json] [--no-mcp]
또는 프로젝트 경로를 한 줄에 하나씩 stdin/--projects-file 로.
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_kb_env(proj: Path) -> dict:
    """프로젝트 .claude/kb.env 파싱 (값 그대로, secret 아님 — vault경로·collection키만)."""
    out = {"vault_dir": None, "kb_collection": None, "domains": None}
    kb = proj / ".claude" / "kb.env"
    if not kb.is_file():
        return out
    try:
        for line in kb.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "KB_VAULT_DIR":
                out["vault_dir"] = v
            elif k == "KB_COLLECTION":
                out["kb_collection"] = v or None
            elif k == "KB_DOMAINS":
                out["domains"] = v or None
    except Exception:
        pass
    return out


def project_scoped_mcp(claude_json: dict, proj_path: str) -> set:
    """~/.claude.json projects[<abspath>].mcpServers 키 집합 (프로젝트-스코프 MCP)."""
    keys = set()
    try:
        projs = claude_json.get("projects", {})
        # 키가 abspath. 정규화 비교.
        target = os.path.abspath(proj_path)
        for k, v in projs.items():
            if os.path.abspath(k) == target and isinstance(v, dict):
                keys.update((v.get("mcpServers") or {}).keys())
    except Exception:
        pass
    return keys


VAULT_CATS = ["literature", "permanent", "decisions", "notes", "templates", "00_inbox"]
TITLE_CAP = 40  # 카테고리/타입별 제목 최대 수집 수


def md_title(f: Path) -> str:
    """첫 '# 제목' 또는 파일명."""
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[:30]:
            s = line.strip()
            if s.startswith("# "):
                return s[2:].strip()[:120]
    except Exception:
        pass
    return f.stem


def titles_in(d: Path) -> list:
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.rglob("*.md")):
        out.append(md_title(f))
        if len(out) >= TITLE_CAP:
            break
    return out


def vault_metrics(vault_dir: str, with_titles: bool = True) -> dict:
    """vault 내용 지표: 카테고리별 노트 수·총 md·최신 수정일 (+제목 목록)."""
    vp = Path(vault_dir)
    by_cat = {}
    items = {}
    for c in VAULT_CATS:
        d = vp / c
        by_cat[c] = sum(1 for _ in d.rglob("*.md")) if d.is_dir() else 0
        if with_titles and by_cat[c]:
            items[c] = titles_in(d)
    all_md = list(vp.rglob("*.md"))
    last = None
    if all_md:
        try:
            ts = max(f.stat().st_mtime for f in all_md)
            last = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
    return {"path": vault_dir, "total_md": len(all_md), "by_cat": by_cat,
            "items": items, "last_modified": last}


def wiki_metrics(vault_dir: str, with_titles: bool = True) -> dict | None:
    """LLM Wiki(vault/wiki) 내용 지표: 노트 수·크기(KB)·타입별 노드(제목)·그래프 유무."""
    wp = Path(vault_dir) / "wiki"
    if not wp.is_dir():
        return None
    notes = list(wp.rglob("*.md"))
    size = 0
    for f in notes:
        try:
            size += f.stat().st_size
        except Exception:
            pass
    subdirs = sorted(d.name for d in wp.iterdir() if d.is_dir())
    nodes = {}
    if with_titles:
        for sd in subdirs:
            t = titles_in(wp / sd)
            if t:
                nodes[sd] = t
    last = None
    if notes:
        try:
            last = datetime.fromtimestamp(max(f.stat().st_mtime for f in notes),
                                          tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
    gfile = wp / "graph" / "graph.html"
    if not gfile.is_file():                                  # 통합본 등은 루트 graph/graph.html
        root_g = Path(vault_dir) / "graph" / "graph.html"
        if root_g.is_file():
            gfile = root_g
    has_graph = gfile.is_file()
    return {"notes": len(notes), "size_kb": round(size / 1024), "subdirs": subdirs,
            "nodes": nodes, "has_graph": has_graph,
            "graph_src": str(gfile) if has_graph else None,
            "last_modified": last}

def pairs_info(proj: Path) -> dict:
    """c-/x- .md 매칭 쌍 + PAIR_TOPOLOGY + 전체 agent 수 (대시보드 정확 표기)."""
    import glob
    A = proj / ".claude" / "agents"
    if not A.is_dir():
        return {"agents_total": 0, "c_md": 0, "x_md": 0, "pairs_matched": 0, "topology": False, "orphan": 0}
    cs = {Path(f).name[2:-3] for f in glob.glob(str(A / "c-*.md"))}
    xs = {Path(f).name[2:-3] for f in glob.glob(str(A / "x-*.md"))}
    total = sum(1 for f in A.iterdir() if f.is_file())
    topo = (proj / ".claude" / "PAIR_TOPOLOGY.yaml").is_file() or (proj / "PAIR_TOPOLOGY.yaml").is_file()
    return {"agents_total": total, "c_md": len(cs), "x_md": len(xs),
            "pairs_matched": len(cs & xs), "topology": topo, "orphan": len(cs ^ xs)}


# ─────────────────────────────────────────────────────────────
# Agent·Pair·Adaptive-Verification Observability (component: fleet_agent_pair_observability)
#   - read-only: 소스(agent/topology/routing/loop)를 읽기만. 자기 출력 JSON 외 write 0.
#   - stdlib only. secret/prompt/transcript/CoT 미수집.
#   - malformed 파일 1개가 전체 수집을 실패시키지 않음(격리).
# ─────────────────────────────────────────────────────────────
import hashlib as _hashlib
import re as _re

AGENT_BAK_RE = _re.compile(r"\.bak", _re.I)
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
MAX_RECENT_RUNS = 20
MAX_EVENTS_BYTES = 256 * 1024          # events.jsonl 파일당 읽기 상한
MAX_LOOP_DIRS = 200                    # 전체 loop 디렉터리 스캔 상한
LOOP_DIR_NAMES = ("loops", "debates")  # _claude/loops, _output/loops, _output/debates


def _sha256_file(p: Path) -> str | None:
    try:
        h = _hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _hash12(s: str) -> str:
    return _hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:12]


def parse_frontmatter(md: Path) -> dict | None:
    """최소 YAML frontmatter(--- ... ---) 파서. 닫는 --- 없으면 None(=invalid-agent).
    멀티라인 리스트(`tools:` 다음 줄 `  - Read`) 도 수집(write_permission 정확도)."""
    try:
        lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    body = lines[1:]
    fm, closed = {}, False
    i = 0
    while i < len(body):
        ln = body[i]
        if ln.strip() == "---":
            closed = True
            break
        # 들여쓴 줄(리스트 항목 등)·빈 줄·주석은 skip
        if ln[:1] in (" ", "\t") or not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        # (Codex MAJOR2) top-level 줄인데 'key: value' 형태가 아니면 malformed → fail-closed(None)
        if ":" not in ln:
            return None
        k, _, v = ln.partition(":")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v == "":   # 멀티라인 리스트 후보: 다음 줄들이 '  - item' 이면 수집
            items = []
            j = i + 1
            while j < len(body) and body[j].lstrip().startswith("- ") and body[j][:1] in (" ", "\t"):
                items.append(body[j].lstrip()[2:].strip().strip("'").strip('"'))
                j += 1
            if items:
                fm[k] = ", ".join(items)   # _split_list 가 동일하게 처리
                i = j
                continue
        fm[k] = v
        i += 1
    return fm if closed else None  # 닫는 --- 없음 → 파싱 실패


def _split_list(v) -> list:
    if not v:
        return []
    v = str(v).strip()
    if v in ("*", "all"):
        return ["*"]
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [t.strip().strip("'").strip('"') for t in v.split(",") if t.strip()]


def _write_perm(tools: list, disallowed: list) -> bool:
    has = ("*" in tools) or bool(WRITE_TOOLS & set(tools))
    # disallowed 가 명시 write-tool 또는 와일드카드(*/all)면 write 차단
    if (WRITE_TOOLS & set(disallowed)) or ("*" in disallowed) or ("all" in disallowed):
        has = False
    return has


def scan_agents(agents_dir: Path, scope: str, topo_pairs: list) -> list:
    """agent .md 인벤토리(읽기전용). .bak* 와 하위 backup 디렉터리 제외."""
    out = []
    if not agents_dir.is_dir():
        return out
    ref_by_pair = {}
    for pr in topo_pairs:
        for role in ("c_agent", "x_agent"):
            an = pr.get(role)
            if an:
                ref_by_pair.setdefault(an, []).append(pr.get("pair_id"))
    for f in sorted(agents_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md" or AGENT_BAK_RE.search(f.name):
            continue
        fm = parse_frontmatter(f)
        name = (fm or {}).get("name") or f.stem
        kind = "c" if f.name.startswith("c-") else "x" if f.name.startswith("x-") else "general"
        tools = _split_list((fm or {}).get("tools"))
        disallowed = _split_list((fm or {}).get("disallowedTools") or (fm or {}).get("disallowed_tools"))
        # 유효 frontmatter + tools 키 부재 = Claude Code 기본 = 전체 도구 상속(Write/Edit) → 무제한·write 가능.
        # frontmatter 자체가 없으면(fm is None=invalid-agent) subagent 로드 불가 → write 불가.
        # (Codex MAJOR1) 빈 frontmatter {}도 유효(installed)이므로 fm is not None 기준 — bool(fm)는 {} 오판.
        tools_unrestricted = (fm is not None) and (("tools" not in fm) or ("*" in tools))
        write_perm = True if tools_unrestricted else _write_perm(tools, disallowed)
        if (WRITE_TOOLS & set(disallowed)) or ("*" in disallowed) or ("all" in disallowed):
            write_perm = False  # disallowed 가 명시 차단하면 무제한이어도 차단
        domain = name[2:] if (kind in ("c", "x") and name[1:2] == "-") else ((fm or {}).get("domain") or None)
        out.append({
            "agent_id": _hash12(f"{scope}:{name}"),
            "name": name,
            "kind": kind,
            "scope": scope,
            "domain": domain,
            "role_summary": ((fm or {}).get("description") or "")[:240],
            "source_path_relative": f.name,
            "source_sha256": _sha256_file(f),
            "tools": tools,
            "disallowed_tools": disallowed,
            "skills": _split_list((fm or {}).get("skills")),
            "tools_unrestricted": tools_unrestricted,   # tools 미선언/와일드카드 = 전체 상속
            "write_permission": write_perm,
            "installed_status": "installed" if fm is not None else "invalid-agent",
            "referenced_by_pairs": ref_by_pair.get(name, []),
            "referenced_by_routes": [],   # routing_matrix/v1 은 agent명을 직접 참조하지 않음
        })
    return out


def _inline(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip("'").strip('"') for x in inner.split(",") if x.strip()] if inner else []
    return v.strip().strip("'").strip('"')


def parse_pair_topology(p: Path):
    """pair_topology/v1 파서. 없으면 None, 손상 시 {'_malformed':True}."""
    if not p.is_file():
        return None
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {"_malformed": True}
    meta = {"schema": None, "project": None, "level": None}
    pairs, cur, in_pairs = [], None, False
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip())
        s = ln.strip()
        if indent == 0:
            in_pairs = False
            for key in ("schema", "project", "level"):
                if s.startswith(key + ":"):
                    meta[key] = s.split(":", 1)[1].strip()
            if s.startswith("pairs:"):
                in_pairs = True
            continue
        if not in_pairs:
            continue
        if s.startswith("- "):
            if cur:
                pairs.append(cur)
            cur = {}
            s2 = s[2:]
            if ":" in s2:
                k, _, v = s2.partition(":")
                cur[k.strip()] = _inline(v)
        elif cur is not None and ":" in s:
            k, _, v = s.partition(":")
            cur[k.strip()] = _inline(v)
    if cur:
        pairs.append(cur)
    if meta["schema"] is None and not pairs:
        return {"_malformed": True}
    return {**meta, "pairs": pairs}


def parse_routing(p: Path):
    """routing_matrix/v1 파서. 없으면 None, 손상 시 {'_malformed':True}."""
    if not p.is_file():
        return None
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {"_malformed": True}
    schema, router, rules, in_rules = None, None, {}, False
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip())
        s = ln.strip()
        if indent == 0:
            in_rules = False
            if s.startswith("schema:"):
                schema = s.split(":", 1)[1].strip()
            elif s.startswith("router:"):
                router = s.split(":", 1)[1].strip()
            elif s.startswith("rules:"):
                in_rules = True
            continue
        if in_rules and ":" in s:
            k, _, v = s.partition(":")
            rules[k.strip()] = v.strip()
    if schema is None and not rules:
        return {"_malformed": True}
    return {"schema": schema, "rules": rules, "router": router}


def routing_summary(routing) -> dict:
    if not routing or routing.get("_malformed"):
        return {"routing_status": "malformed" if routing else "not-configured",
                "route_count": 0, "task_type_count": 0, "one_shot_routes": 0,
                "deterministic_routes": 0, "intra_pair_routes": 0, "cross_domain_routes": 0,
                "human_gated_routes": 0}
    rules = routing.get("rules", {})
    def cnt(pred):
        return sum(1 for k, v in rules.items() if pred(k, (v or "").lower()))
    return {
        "routing_status": "ok",
        "route_count": len(rules),
        "task_type_count": len(rules),
        "one_shot_routes": cnt(lambda k, v: "one-shot" in v or "one_shot" in v),
        "deterministic_routes": cnt(lambda k, v: "deterministic" in k or "fix_max" in v),
        "intra_pair_routes": cnt(lambda k, v: "intra-pair" in v),
        "cross_domain_routes": cnt(lambda k, v: "cross-domain" in v),
        "human_gated_routes": cnt(lambda k, v: "human_gate" in v and "true" in v),
    }


def _strip_yaml_comment(v: str) -> str:
    """인라인 # 주석 제거 — 따옴표 상태 추적(따옴표 안 #·: 보존). (Codex MAJOR3)."""
    v = v.strip()
    out = []
    inq = None
    for i, ch in enumerate(v):
        if inq:
            out.append(ch)
            if ch == inq:
                inq = None
        elif ch in ('"', "'"):
            inq = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or v[i - 1] == " "):
            break   # 따옴표 밖 주석 시작
        else:
            out.append(ch)
    s = "".join(out).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    return s.strip()


def _read_yaml_or_json_min(p: Path) -> dict:
    """contract.yaml / verdict.(json|yaml) 최소 파싱. top-level scalar + 멀티라인 리스트(`key:`\\n`  - item`).
    인라인 # 주석 strip. 민감필드 미수집(화이트리스트는 호출부에서)."""
    out = {}
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"_malformed": True}
    if p.suffix == ".json":
        try:
            d = json.loads(txt)
            return d if isinstance(d, dict) else {"_malformed": True}
        except Exception:
            return {"_malformed": True}
    lines = txt.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#") or ln[:1] in (" ", "\t"):
            i += 1
            continue
        if ln.lstrip().startswith("- "):   # 루트 레벨 리스트 항목 — 허용(skip)
            i += 1
            continue
        if ":" not in ln:                  # (Codex MAJOR4) top-level non-key → fail-closed malformed
            return {"_malformed": True}
        k, _, v = ln.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "":   # 멀티라인 리스트 후보: 다음 줄들이 '  - item'
            items = []
            j = i + 1
            while j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].lstrip().startswith("- "):
                items.append(_strip_yaml_comment(lines[j].lstrip()[2:]))
                j += 1
            if items:
                out[k] = items
                i = j
                continue
        out[k] = _strip_yaml_comment(v)
        i += 1
    return out


# 수집 허용 필드(화이트리스트) — prompt/response/transcript/CoT/secret 절대 미수집
RUN_FIELDS = ("task_type", "risk_tier", "selected_pairs", "temporary_specialists",
              "validation_mode", "review_topology", "pass_count", "iteration_count",
              "codex_used", "human_gate", "verdict", "stop_reason",
              "started_at", "completed_at")


def scan_execution(proj: Path) -> tuple:
    """loop/debate 실행 evidence 수집(읽기전용·화이트리스트·캡). 반환 (recent_runs, summary)."""
    runs = []
    malformed = 0
    seen_dirs = 0
    search_roots = [proj / "_claude", proj / "_output", proj / ".claude"]
    loop_dirs = []
    for root in search_roots:
        if seen_dirs >= MAX_LOOP_DIRS:
            break
        for nm in LOOP_DIR_NAMES:
            if seen_dirs >= MAX_LOOP_DIRS:
                break
            d = root / nm
            if d.is_dir():
                try:
                    for sub in sorted(d.iterdir()):
                        if seen_dirs >= MAX_LOOP_DIRS:   # append 전 검사(상한 정확)
                            break
                        if sub.is_dir():
                            loop_dirs.append(sub)
                            seen_dirs += 1
                except Exception:
                    malformed += 1
    ledger_infra = any((proj / r / nm).is_dir() for r in ("_claude", "_output", ".claude") for nm in LOOP_DIR_NAMES)
    for sub in loop_dirs:
        contract = next((sub / c for c in ("contract.yaml", "contract.yml") if (sub / c).is_file()), None)
        verdict_f = next((sub / v for v in ("verdict.json", "verdict.yaml", "verdict.yml") if (sub / v).is_file()), None)
        events_f = sub / "events.jsonl"
        if not (contract or verdict_f or events_f.is_file()):
            continue
        lh = _hash12(sub.name)
        rec = {"loop_id_hash": lh, "iteration_count": None,
               "deterministic_verifier_summary": None}
        bad = False
        # 경로는 loop-dir 이름(user-controlled, prompt/secret 가능)을 hash로 치환해 누출 차단
        try:
            base = str(sub.parent.relative_to(proj))
        except Exception:
            base = "loops"
        if contract:
            c = _read_yaml_or_json_min(contract)
            if c.get("_malformed"):
                bad = True
            for fld in RUN_FIELDS:
                if fld in ("verdict", "stop_reason"):
                    continue   # (Codex CRITICAL1) verdict/stop_reason 는 verdict 파일에서만 — contract 신뢰 안 함
                if fld in c and fld not in rec:
                    rec[fld] = c[fld]
            # 거버넌스 위반 플래그(true/True/1 만 위반으로)
            if str(c.get("same_failure_overrun", "")).lower() in ("true", "1", "yes"):
                rec["same_failure_overrun"] = True
            if str(c.get("codex_as_source_truth", "")).lower() in ("true", "1", "yes"):
                rec["codex_as_source_truth"] = True
            rec["contract_path_relative"] = f"{base}/{lh}/{contract.name}"
        if verdict_f:
            vd = _read_yaml_or_json_min(verdict_f)
            if vd.get("_malformed"):
                bad = True
            rec["has_verdict_file"] = True
            # 권위 verdict = real ledger status 우선, 없으면 구 verdict 키. 둘 다 있고 다르면 malformed.
            v_field, s_field = vd.get("verdict"), vd.get("status")
            if v_field is not None and s_field is not None and \
               str(v_field).strip().upper() != str(s_field).strip().upper():
                bad = True   # (Codex MAJOR1) verdict/status 충돌 → malformed
            authoritative = s_field if s_field is not None else v_field
            if authoritative is not None:
                rec["verdict"] = authoritative
            rec["stop_reason"] = vd.get("reason") or vd.get("stop_reason")
            for fld in ("pass_count", "iteration_count", "codex_used"):
                if fld in vd:
                    rec[fld] = vd[fld]
            rec["verdict_path_relative"] = f"{base}/{lh}/{verdict_f.name}"
        # events.jsonl: iteration 수만 카운트(본문 미수집, byte 캡)
        spawned = []
        if events_f.is_file():
            try:
                if events_f.stat().st_size <= MAX_EVENTS_BYTES:
                    n_iter = 0
                    for line in events_f.read_text(encoding="utf-8", errors="replace").splitlines():
                        ls = line.strip()
                        if not ls:
                            continue
                        try:
                            ev = json.loads(ls)
                        except Exception:
                            continue
                        if not isinstance(ev, dict):
                            continue
                        if (ev.get("type") or ev.get("event")) in ("iteration", "iter", "pass"):
                            n_iter += 1
                        # (G10) ledger 스키마 변종 무관 페어 토큰 수집 — exact alias 로만 해소되어 over-collect 안전.
                        ev_name = str(ev.get("event") or "")
                        #  (a) verifier_c_<pair>/verifier_x_<pair> 이벤트명(Flood fact-check)
                        m = _re.match(r"verifier_[cx]_(.+)$", ev_name)
                        if m:
                            spawned.append(m.group(1))
                        #  (b) 이벤트 data 의 agent/pair 참조 필드(fusion pair_spawn·레이더 agents·원격 step.agent·과기부 pair 등)
                        d = ev.get("data")
                        if isinstance(d, dict):
                            # (Codex G10-MINOR) axis 제외 — 이벤트 data의 axis는 자유문자열일 수 있어 over-collect 위험.
                            # agent/pair/c_agent/x_agent 만(전 6개 프로젝트 해소에 충분). contract selected_pairs(axis명)는 별도 경로.
                            for key in ("agent", "pair", "c_agent", "x_agent"):
                                val = d.get(key)
                                if isinstance(val, str):
                                    spawned.extend(t for t in _re.split(r"[/,+\s]+", val) if t)
                            for key in ("agents", "pairs", "selected_pairs"):
                                val = d.get(key)
                                if isinstance(val, list):
                                    spawned.extend(str(t) for t in val if t)
                    if rec.get("iteration_count") in (None, ""):
                        rec["iteration_count"] = n_iter or None
            except Exception:
                bad = True
        rec["spawned_agents"] = spawned
        if bad:
            malformed += 1
            rec["malformed"] = True
        # selected_pairs 정규화
        sp = rec.get("selected_pairs")
        if isinstance(sp, str):
            rec["selected_pairs"] = _split_list(sp)
        runs.append(rec)
    # 최신순(completed_at/started_at desc) 후 캡
    runs.sort(key=lambda r: (r.get("completed_at") or r.get("started_at") or ""), reverse=True)
    capped = runs[:MAX_RECENT_RUNS]
    # live 후보 토큰 = **verdict 파일 존재 + PASS** 인 run 만 (Codex CRITICAL1/2: contract verdict·비-PASS 배제)
    def _is_pass(v):
        return str(v or "").strip().upper().replace(" ", "-") in ("PASS", "CONDITIONAL-PASS")
    live_tokens = set()
    for r in runs:
        if r.get("has_verdict_file") and _is_pass(r.get("verdict")):
            for tok in (r.get("selected_pairs") or []):
                live_tokens.add(str(tok))
            for tok in (r.get("spawned_agents") or []):
                live_tokens.add(str(tok))
    used_pairs = set()
    for r in runs:
        for pid in (r.get("selected_pairs") or []):
            used_pairs.add(str(pid))
    def vc(val):
        return sum(1 for r in runs if str(r.get("verdict", "")).upper() == val)
    summary = {
        "tracked_loop_count": len(runs),
        "pass_count": vc("PASS"),
        "pass_with_caveats_count": sum(1 for r in runs if "CAVEAT" in str(r.get("verdict", "")).upper()
                                       or "CONDITIONAL" in str(r.get("verdict", "")).upper()),
        "hold_count": vc("HOLD"),
        "running_count": sum(1 for r in runs if not r.get("verdict")),
        "malformed_count": malformed,
        "legacy_untracked_count": 0,   # 프로젝트 레벨에서 pair 계산 시 보정
        "last_activity_at": (capped[0].get("completed_at") or capped[0].get("started_at")) if capped else None,
        "last_verdict": capped[0].get("verdict") if capped else None,
        "last_stop_reason": capped[0].get("stop_reason") if capped else None,
        "maximum_observed_pair_fanout": max([len(r.get("selected_pairs") or []) for r in runs] + [0]),
        "maximum_observed_iterations": max([int(r["iteration_count"]) for r in runs
                                            if str(r.get("iteration_count") or "").isdigit()] + [0]),
        "same_failure_overrun": any(r.get("same_failure_overrun") for r in runs),
        "codex_as_source_truth": any(r.get("codex_as_source_truth") for r in runs),
        "ledger_infra": ledger_infra,
        "_used_pairs": sorted(used_pairs),
        "_live_tokens": sorted(live_tokens),
    }
    return capped, summary


# 토큰(axis명·agent명·PAIR-X) → pair_id 해소
def _norm_tok(s: str) -> str:
    return str(s).strip().strip('"').strip("'").lower().replace(" ", "-").replace("_", "-")


def resolve_pair_id(token: str, topo_pairs: list):
    """selected_pairs/spawned_agent/session_log pair_inferred 토큰을 topology pair_id 로 해소."""
    t = _norm_tok(token)
    if not t:
        return None
    for pr in topo_pairs:
        pid = str(pr.get("pair_id") or "")
        aliases = {pid.lower(), _norm_tok(pr.get("axis") or ""),
                   _norm_tok(pr.get("c_agent") or ""), _norm_tok(pr.get("x_agent") or ""),
                   ("pair-" + pid).lower()}
        aliases.discard("")
        if t in aliases:
            return pid
    # (Codex G9-MAJOR) exact alias 만 신뢰 — word fallback 제거.
    # fusion axis('1-domain-science')·Flood('science')·session_log('PAIR-SCIENCE') 전부 위 exact alias로 해소됨.
    # fallback은 'verifier_c_not-science'→science 같은 wrong-pair 오매핑만 유발 → 제거.
    return None


def read_session_log_pairs(proj: Path) -> set:
    """.claude/runtime/session_log.jsonl 의 task-call pair_inferred 토큰 집합(observed evidence). 캡·읽기전용."""
    f = proj / ".claude" / "runtime" / "session_log.jsonl"
    if not f.is_file():
        return set()
    out = set()
    try:
        size = f.stat().st_size
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            if size > 4 * 1024 * 1024:      # 큰 로그는 마지막 4MB만
                fh.seek(size - 4 * 1024 * 1024)
                fh.readline()
            for line in fh:
                ls = line.strip()
                if not ls or '"task-call"' not in ls:
                    continue
                try:
                    ev = json.loads(ls)
                except Exception:
                    continue
                if isinstance(ev, dict) and ev.get("event") == "task-call":
                    pi = (ev.get("payload") or {}).get("pair_inferred")
                    if pi:
                        out.add(str(pi))
    except Exception:
        return out
    return out


def observe_agents_pairs(proj: Path) -> dict:
    """프로젝트의 agent_inventory + pair_topology + routing_summary + execution 통합(읽기전용)."""
    topo = parse_pair_topology(proj / ".claude" / "PAIR_TOPOLOGY.yaml")
    if topo is None:   # .claude/domain/ 대체 위치도 확인(하위호환)
        topo = parse_pair_topology(proj / ".claude" / "domain" / "PAIR_TOPOLOGY.yaml")
    routing = parse_routing(proj / ".claude" / "ROUTING_MATRIX.yaml")
    if routing is None:
        routing = parse_routing(proj / ".claude" / "domain" / "ROUTING_MATRIX.yaml")
    topo_pairs = (topo or {}).get("pairs", []) if isinstance(topo, dict) and not topo.get("_malformed") else []
    routing_present = bool(routing and not routing.get("_malformed") and routing.get("rules"))

    proj_agents = scan_agents(proj / ".claude" / "agents", "project", topo_pairs)
    by_name = {a["name"]: a for a in proj_agents}

    recent_runs, exec_summary = scan_execution(proj)
    has_tracked = exec_summary.get("tracked_loop_count", 0) > 0
    ledger_infra = exec_summary.get("ledger_infra", False)
    # 토큰(axis명·agent명·PAIR-X)을 pair_id 로 해소: live(verdict 보유 ledger) vs observed(session_log task-call)
    live_used = {pid for tok in exec_summary.get("_live_tokens", [])
                 for pid in [resolve_pair_id(tok, topo_pairs)] if pid}
    # (r12 ledger 변종 하드닝) 표준 triad 외 변종(flat 파일·split·thin-events·ralph md·debate)을
    # ledger_evidence 가 정규화·exact-alias 해소 → strict live-pass 만 union. 모듈 부재 시 graceful(기존 동작).
    ledger_evidence_summary = None
    try:
        import ledger_evidence as _LE
        _le = _LE.scan_ledger_evidence(proj, None, topo_pairs)
        live_used |= set(_le.get("live_pass_pairs") or set())
        ledger_evidence_summary = _le.get("summary")
    except Exception:
        pass
    observed = {pid for tok in read_session_log_pairs(proj)
                for pid in [resolve_pair_id(tok, topo_pairs)] if pid}
    observed -= live_used   # live 로 승격된 pair 는 observed 에서 제외(중복·과소 카운트 방지)
    used_pairs = live_used  # 하위호환 last_used 계산용

    # ---- pair 상태 계산(정확 규칙) ----
    topo_malformed = isinstance(topo, dict) and topo.get("_malformed")
    pairs_out = []
    matched_c = set()
    matched_x = set()
    for pr in topo_pairs:
        c, x = pr.get("c_agent"), pr.get("x_agent")
        ca, xa = by_name.get(c), by_name.get(x)
        if ca:
            matched_c.add(c)
        if xa:
            matched_x.add(x)
        problems = []
        if not ca:
            problems.append("c-file-missing")
        if not xa:
            problems.append("x-file-missing")
        x_write = xa["write_permission"] if xa else False
        if x_write:
            problems.append("x-write-permission")
        # trigger: pair 자체 trigger 명시 또는 ROUTING_MATRIX 존재
        has_trigger = routing_present or bool(pr.get("trigger") or pr.get("triggers"))
        if not has_trigger:
            problems.append("no-routing-or-trigger")
        # 구조 판정 (spec: valid = c+x 파일 + routing/trigger + x-write 없음)
        if ("c-file-missing" in problems) or ("x-file-missing" in problems):
            pair_status = "broken-pair"
        elif x_write:
            pair_status = "HOLD"
        elif not has_trigger:
            pair_status = "broken-pair"     # topology 있으나 routing/trigger 부재 → 미완성
        else:
            pair_status = "valid-pair"
        # source(stale) 판정: topology 가 기록한 sha 와 실제 불일치
        rec_c_sha = pr.get("c_agent_sha256") or pr.get("c_sha256")
        rec_x_sha = pr.get("x_agent_sha256") or pr.get("x_sha256")
        source_status = "ok"
        if rec_c_sha and ca and ca.get("source_sha256") and rec_c_sha != ca["source_sha256"]:
            source_status = "stale"
        if rec_x_sha and xa and xa.get("source_sha256") and rec_x_sha != xa["source_sha256"]:
            source_status = "stale"
        # 실행 판정 (formal ledger+verdict = live-pass / session_log task-call만 = observed-only)
        pid_cur = pr.get("pair_id")
        if pair_status != "valid-pair":
            execution_status = "n/a"
        elif pid_cur in live_used:
            execution_status = "live-pass"          # formal ledger + verdict 존재
        elif pid_cur in observed:
            execution_status = "observed-only"       # session_log task-call만, verdict 없음
        elif has_tracked:
            execution_status = "never-used"
        elif ledger_infra:
            execution_status = "static-pass"
        else:
            execution_status = "legacy-untracked"
        pairs_out.append({
            "pair_id": pr.get("pair_id"),
            "pair_name": pr.get("axis") or pr.get("pair_id"),
            "c_agent": c,
            "x_agent": x,
            "domain_stack_refs": pr.get("axis"),
            "purpose_summary": (ca or {}).get("role_summary") or pr.get("axis"),
            "trigger_summary": (routing or {}).get("router") if routing and not routing.get("_malformed") else None,
            "non_trigger_summary": None,
            "deterministic_verifiers": pr.get("deterministic_verifiers"),
            "validation_modes": pr.get("axis"),
            "cross_model_policy": pr.get("cross_model_policy"),
            "maximum_iterations": pr.get("maximum_iterations"),
            "same_failure_limit": pr.get("same_failure_limit") or _extract_same_fail(pr.get("stop_conditions")),
            "stop_conditions": pr.get("stop_conditions"),
            "c_write_permission": pr.get("c_write_permission") or ((ca or {}).get("write_permission")),
            "x_write_permission": pr.get("x_write_permission") or (xa["write_permission"] if xa else None),
            "source_status": source_status,
            "pair_status": pair_status,
            "execution_status": execution_status,
            "problems": problems,
            "last_used_at": exec_summary.get("last_activity_at") if pr.get("pair_id") in used_pairs else None,
            "last_loop_id_hash": next((r["loop_id_hash"] for r in recent_runs
                                       if pr.get("pair_id") in (r.get("selected_pairs") or [])), None),
        })

    # ---- unpaired c/x: topology 에 없는 c-/x- 파일 ----
    all_c = {a["name"] for a in proj_agents if a["kind"] == "c"}
    all_x = {a["name"] for a in proj_agents if a["kind"] == "x"}
    unpaired_c = sorted(all_c - matched_c)
    unpaired_x = sorted(all_x - matched_x)
    # ---- orphan general agent: pair/route 어디에도 참조 안 됨 ----
    generals = [a for a in proj_agents if a["kind"] == "general"]
    orphan_general = [a["name"] for a in generals if not a["referenced_by_pairs"]]

    valid_count = sum(1 for p in pairs_out if p["pair_status"] == "valid-pair")
    # topology status
    if topo is None:
        topo_status = "not-configured" if not (all_c or all_x) else "cx-files-no-topology"
    elif topo_malformed:
        topo_status = "malformed"
    elif valid_count == 0 and pairs_out:
        topo_status = "broken"
    else:
        topo_status = "configured"

    agent_inventory = {
        "status": "installed" if proj_agents else "none",
        "agent_count": len(proj_agents),
        "global_agent_count": 0,                       # 집계기가 글로벌 합산
        "project_agent_count": len(proj_agents),
        "c_agent_count": len(all_c),
        "x_agent_count": len(all_x),
        "general_agent_count": len(generals),
        "temporary_specialist_count": 0,               # loop contract 에서만(현재 0)
        "invalid_agent_count": sum(1 for a in proj_agents if a["installed_status"] == "invalid-agent"),
        "orphan_agent_count": len(orphan_general),
        "orphan_agents": orphan_general,
        "agents": proj_agents,
    }
    pair_topology = {
        "status": topo_status,
        "pair_count": valid_count,                     # ★ valid PAIR_TOPOLOGY entry 수 (파일수÷2 아님)
        "topology_pair_entries": len(pairs_out),
        "static_pass_count": sum(1 for p in pairs_out if p["execution_status"] == "static-pass"),
        "live_pass_count": sum(1 for p in pairs_out if p["execution_status"] == "live-pass"),
        "observed_only_count": sum(1 for p in pairs_out if p["execution_status"] == "observed-only"),
        "never_used_count": sum(1 for p in pairs_out if p["execution_status"] == "never-used"),
        "legacy_untracked_count": sum(1 for p in pairs_out if p["execution_status"] == "legacy-untracked"),
        "broken_pair_count": sum(1 for p in pairs_out if p["pair_status"] == "broken-pair"),
        "hold_pair_count": sum(1 for p in pairs_out if p["pair_status"] == "HOLD"),
        "stale_pair_count": sum(1 for p in pairs_out if p["source_status"] == "stale"),
        "unpaired_cx_count": len(unpaired_c) + len(unpaired_x),
        "unpaired_c": unpaired_c,
        "unpaired_x": unpaired_x,
        "topology_sha256": _sha256_file(proj / ".claude" / "PAIR_TOPOLOGY.yaml"),
        "routing_sha256": _sha256_file(proj / ".claude" / "ROUTING_MATRIX.yaml"),
        "topology_malformed": bool(topo_malformed),
        "pairs": pairs_out,
    }
    exec_summary.pop("_used_pairs", None)
    exec_summary.pop("_live_tokens", None)
    return {
        # (r12) name-collision 방지: 이름 아닌 absolute_path 로 식별(aggregator/registry 매칭 키).
        "project_absolute_path": str(proj.resolve()) if proj.exists() else str(proj),
        "agent_inventory": agent_inventory,
        "pair_topology": pair_topology,
        "routing_summary": routing_summary(routing),
        "execution_summary": exec_summary,
        "recent_runs": recent_runs,
        "ledger_evidence": ledger_evidence_summary,   # (r12) 변종 정규화 요약(분류·source_type 카운트)
    }


def _extract_same_fail(stop_conditions):
    """stop_conditions(예: ['동일실패2','전역5']) 에서 동일실패 한도 추출."""
    if not stop_conditions:
        return None
    for s in (stop_conditions if isinstance(stop_conditions, list) else [stop_conditions]):
        m = _re.search(r"동일실패\s*(\d+)|same[_-]?fail\w*\s*(\d+)", str(s))
        if m:
            return int(m.group(1) or m.group(2))
    return None


def harness_health(proj: Path) -> dict:
    """B. 배포·하네스 건강: hooks/smoke/scripts 수·Evidence Index·serena·settings·r3 여부."""
    def cnt(sub, pat):
        d = proj / sub
        return len(list(d.glob(pat))) if d.is_dir() else 0
    hooks = cnt("hooks", "*.mjs")
    smoke = cnt("tests", "smoke_*.sh")
    scripts = cnt("scripts", "*.py")
    evidence = (proj / ".claude" / "runtime" / "system_truth_index.json").is_file()
    serena = (proj / ".serena").is_dir()
    settings = (proj / ".claude" / "settings.local.json").is_file()
    last_deploy = None
    sp = proj / ".claude" / "settings.local.json"
    if sp.is_file():
        try:
            last_deploy = datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
    return {"hooks": hooks, "smoke": smoke, "scripts": scripts,
            "evidence_index": evidence, "serena": serena, "settings_local": settings,
            "is_r3": hooks >= 12 and smoke >= 13, "last_deploy": last_deploy}


def contradictions_count(vault_dir: str) -> int:
    """vault/wiki/contradictions.md 의 미해소 모순 항목 수(## 헤더)."""
    f = Path(vault_dir) / "wiki" / "contradictions.md"
    if not f.is_file():
        return 0
    try:
        return sum(1 for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()
                   if ln.startswith("## "))
    except Exception:
        return 0


def count_sessions(home: Path, proj_path: str) -> int | None:
    """~/.claude/projects/<encoded>/ 의 세션(jsonl) 수. 인코딩 = 비영숫자→'-'."""
    import re
    enc = re.sub(r"[^a-zA-Z0-9]", "-", os.path.abspath(proj_path))
    d = home / ".claude" / "projects" / enc
    if not d.is_dir():
        return None
    try:
        return sum(1 for f in d.iterdir() if f.suffix == ".jsonl")
    except Exception:
        return None


def _find_claude() -> str | None:
    for cand in ("claude", str(Path.home() / ".local" / "bin" / "claude")):
        try:
            r = subprocess.run(["bash", "-lc", f"command -v {cand}"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return cand
        except Exception:
            continue
    return None


def mcp_connected_set(claude: str | None, cwd: str | None = None, timeout: int = 20) -> list | None:
    """`claude mcp list`(cwd 기준 스코프) 파싱 → ✔ Connected 서버명. 실패 시 None(graceful).
    cwd를 프로젝트 경로로 주면 그 프로젝트-스코프 MCP(kb/design 등)까지 포함된다."""
    if not claude:
        return None
    try:
        r = subprocess.run(["bash", "-lc", f"cd {json.dumps(cwd)} 2>/dev/null; {claude} mcp list" if cwd
                            else f"{claude} mcp list"],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    connected = []
    for line in (r.stdout or "").splitlines():
        # 형식: "name: <cmd/url> - ✔ Connected"
        if ":" in line and "Connected" in line and "✔" in line:
            connected.append(line.split(":", 1)[0].strip())
    return connected


def collect_project(proj_path: str, home: Path, claude_json: dict,
                    claude_bin: str | None, verify_mcp: bool) -> dict:
    proj = Path(proj_path)
    entry = {
        "name": proj.name,
        "path": str(proj),
        "exists": proj.is_dir(),
        "knowledge_io": {
            "vault": None,            # {path,total_md,by_cat,last_modified}
            "wiki": None,             # {notes,size_kb,subdirs,last_modified}
            "kb": None,           # {collection, items}  ← items는 집계기가 채움
            "claude_design": False,
        },
        "mcp": {"kb": False, "design": False, "serena": False},
        "mcp_connected": {"kb": None, "design": None, "serena": None},
        "harness": None,
        "sessions": None,
    }
    if not proj.is_dir():
        return entry

    entry["harness"] = harness_health(proj)
    entry["pairs"] = pairs_info(proj)         # 하위호환(구버전 render 용 — 보존)
    try:
        entry.update(observe_agents_pairs(proj))   # ★ 신규: agent/pair/routing/execution 관측
    except Exception as e:                          # malformed 1개가 전체 수집 실패시키지 않음
        entry["agent_pair_error"] = str(e)[:200]

    kb = read_kb_env(proj)
    # notes-app vault: kb.env의 KB_VAULT_DIR 우선, 없으면 <proj>/vault
    vault_dir = None
    if kb["vault_dir"] and Path(kb["vault_dir"]).is_dir():
        vault_dir = kb["vault_dir"]
    elif (proj / "vault").is_dir():
        vault_dir = str(proj / "vault")
    if vault_dir:
        entry["knowledge_io"]["vault"] = vault_metrics(vault_dir)
        wm = wiki_metrics(vault_dir)
        if wm is not None:
            wm["contradictions"] = contradictions_count(vault_dir)
        entry["knowledge_io"]["wiki"] = wm
    if kb["kb_collection"]:
        entry["knowledge_io"]["kb"] = {"collection": kb["kb_collection"], "items": None}

    # MCP (프로젝트 스코프 설정 키)
    mcp_keys = project_scoped_mcp(claude_json, proj_path)
    entry["mcp"]["kb"] = "kb" in mcp_keys
    entry["mcp"]["design"] = any("design" in k for k in mcp_keys)
    entry["mcp"]["serena"] = "serena" in mcp_keys
    entry["knowledge_io"]["claude_design"] = entry["mcp"]["design"]

    # 연결 검증: kb/design이 프로젝트-스코프로 설정된 경우만 그 cwd에서 mcp list 호출(비용 최소)
    if verify_mcp and claude_bin and (entry["mcp"]["kb"] or entry["mcp"]["design"]):
        conn = mcp_connected_set(claude_bin, cwd=proj_path)
        if conn is not None:
            cs = set(conn)
            entry["mcp_connected"]["kb"] = ("kb" in cs) if entry["mcp"]["kb"] else None
            entry["mcp_connected"]["design"] = (any("design" in c for c in cs)) if entry["mcp"]["design"] else None
            entry["mcp_connected"]["serena"] = ("serena" in cs) if entry["mcp"]["serena"] else None

    entry["sessions"] = count_sessions(home, proj_path)
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", required=True)
    ap.add_argument("--project", action="append", default=[])
    ap.add_argument("--projects-file")
    ap.add_argument("--out")
    ap.add_argument("--no-mcp", action="store_true", help="claude mcp list 생략(빠름)")
    args = ap.parse_args()

    paths = list(args.project)
    if args.projects_file:
        paths += [l.strip() for l in Path(args.projects_file).read_text().splitlines() if l.strip()]
    if not paths and not sys.stdin.isatty():
        paths += [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]

    home = Path.home()
    claude_json = {}
    cj = home / ".claude.json"
    if cj.is_file():
        try:
            claude_json = json.loads(cj.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            claude_json = {}

    claude_bin = None if args.no_mcp else _find_claude()
    # 머신 글로벌 agent(~/.claude/agents/*.md) — 모든 프로젝트 공통(general/c/x)
    try:
        global_agents = scan_agents(home / ".claude" / "agents", "global", [])
    except Exception:
        global_agents = []
    result = {
        "machine": args.machine,
        "hostname": socket.gethostname(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mcp_user_scope_connected": None if args.no_mcp else mcp_connected_set(claude_bin),
        "global_agents": global_agents,
        "global_agent_count": len(global_agents),
        "projects": [collect_project(p, home, claude_json, claude_bin, not args.no_mcp) for p in paths],
    }

    out = args.out or str(home / "fleet-summary.json")
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stderr.write(f"[fleet_summary] machine={args.machine} projects={len(result['projects'])} -> {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
