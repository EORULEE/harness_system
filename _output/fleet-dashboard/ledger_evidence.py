#!/usr/bin/env python3
"""ledger_evidence.py — formal loop ledger 변종 정규화 스캐너 (r12 hardening).

배경: cross-domain canary 가 verdict=PASS 로 완주해도 ledger 저장 위치/형식이 세션마다 달라
collector 가 일부를 못 읽어 live-pass 자동산출 실패(2026-06-25 실측 5변종).
이 모듈은 13개 evidence 위치를 전수 스캔해 단일 normalized record 로 정규화하고,
strict live-pass rule + topology exact-alias 해소로 분류한다. fleet_summary.scan_execution 이
재사용(full rewrite 아님). G8~G10 토큰수집과 deploy_gate 판정에 그대로 연결된다.

read-only. 자기 출력(JSON) 외 write 0. loop-dir/파일명은 user-controlled → 누출 차단 위해
경로는 상대화하고 prompt 본문은 수집하지 않는다(verdict status·AC pass·pair alias 만).
"""
from __future__ import annotations
import json
import re
import hashlib
from pathlib import Path

EVIDENCE_SOURCE_TYPES = (
    "standard_loop_triad", "flat_loop_files", "split_contract_verdict",
    "ralph_markdown_verdict", "debate_verdict", "session_log_observed_only", "malformed",
)
CLASSIFICATIONS = (
    "pair-live-pass", "live-pass-thin-events", "observed-only",
    "static-pass", "never-used", "HOLD",
)
_PASS_TOKENS = ("PASS", "CONDITIONAL-PASS")
MAX_SCAN = 200          # 위치당 파일/디렉터리 상한(DoS·캡)
MAX_BYTES = 512 * 1024  # 파일당 read 캡


def _is_pass(v) -> bool:
    return str(v or "").strip().upper().replace(" ", "-") in _PASS_TOKENS


def _sha256(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()[:MAX_BYTES]).hexdigest()[:16]
    except Exception:
        return ""


def _read_min(p: Path):
    """verdict.json/yaml/contract 최소 파싱. JSON 우선, 실패 시 top-level scalar yaml.
    반환 dict 또는 {'_malformed': True}."""
    try:
        if p.stat().st_size > MAX_BYTES:
            return {"_malformed": True}
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"_malformed": True}
    s = txt.lstrip()
    if s.startswith("{"):
        try:
            d = json.loads(txt)
            return d if isinstance(d, dict) else {"_malformed": True}
        except Exception:
            return {"_malformed": True}
    # 최소 yaml: top-level "key: value" + "key:\n  - item"
    out, cur_list_key = {}, None
    for ln in txt.splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+-\s+", ln) and cur_list_key:
            out.setdefault(cur_list_key, []).append(ln.split("-", 1)[1].strip().strip("'\""))
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", ln)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if v == "":
                cur_list_key = k
            else:
                out[k] = v.strip("'\"")
                cur_list_key = None
    return out or {"_malformed": True}


# ── topology exact-alias table (과수집 방지) ──
def build_alias_table(topo_pairs: list) -> dict:
    """pair_id·c_agent·x_agent·결합표기(c-X+x-X)·접두제거 → pair_id. exact match 전용."""
    alias = {}
    for pr in topo_pairs or []:
        pid = pr.get("pair_id")
        if not pid:
            continue
        keys = {str(pid)}
        for role in ("c_agent", "x_agent"):
            an = pr.get(role)
            if an:
                keys.add(str(an))
                # c-sar → sar (접두 제거 1회, exact)
                if str(an)[1:2] == "-":
                    keys.add(str(an)[2:])
        for k in keys:
            alias[k.strip().lower()] = pid
    return alias


def resolve_pairs(tokens, alias: dict):
    """토큰 리스트 → (resolved pair_id set, method, unresolved list). exact alias 만."""
    resolved, unresolved = set(), []
    for tok in tokens or []:
        t = str(tok).strip().lower()
        # 결합표기 c-sar+x-sar / c-sar,x-sar
        parts = [p for p in re.split(r"[+,/\s]+", t) if p]
        hit = False
        for p in parts or [t]:
            if p in alias:
                resolved.add(alias[p])
                hit = True
        if not hit:
            unresolved.append(str(tok))
    method = "exact-alias" if resolved else ("unresolved" if unresolved else "none")
    return resolved, method, unresolved


# ── Ralph markdown verdict (엄격) ──
def _parse_ralph_md(p: Path) -> dict:
    """_output/ralph/verdict*.md. 'PASS' 문자열만으로 불충분 — verdict 판정행 + AC pass 근거 필요."""
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]
    except Exception:
        return {"_malformed": True}
    # 최종 판정 행: "최종 판정: ✅ PASS" / "verdict: PASS" / "## ... PASS (AC...)"
    verdict_line = re.search(r"(최종\s*판정|verdict|판정)\s*[:：]?\s*[^\n]*\bPASS\b", txt, re.IGNORECASE)
    ac_pass = len(re.findall(r"\bAC\d+\b[^\n|]*\|?\s*[^\n|]*\bPASS\b", txt)) or \
        len(re.findall(r"\|\s*AC\d+[^|]*\|[^|]*\|\s*PASS\s*\|", txt))
    fail = re.search(r"\b(FAIL|HOLD)\b", txt)
    pair_toks = re.findall(r"\b([cx]-[a-z][a-z0-9_]+)\b", txt)
    iters = re.search(r"iteration[^\n]*?(\d+)\s*회|(\d+)\s*iteration", txt, re.IGNORECASE)
    if not verdict_line:
        return {"verdict": None, "_md": True}
    return {
        "verdict": "PASS",
        "_md": True,
        "ac_pass_count": ac_pass,
        "has_fail_marker": bool(fail),
        "pair_tokens": pair_toks,
        "iteration_count": next((g for g in (iters.groups() if iters else []) if g), None),
    }


def _stem_of_flat(name: str):
    """loop-foo.contract.json → ('loop-foo', 'contract')."""
    m = re.match(r"^(.*)\.(contract|events|verdict)\.(json|jsonl|yaml|yml)$", name)
    return (m.group(1), m.group(2)) if m else (None, None)


def scan_ledger_evidence(project_path, machine_id=None, topo_pairs=None) -> dict:
    """프로젝트의 모든 ledger 변종을 정규화. 반환 {evidence:[...], live_pass_pairs:set, summary:{...}}."""
    proj = Path(project_path)
    abs_path = str(proj.resolve()) if proj.exists() else str(proj)
    project_id = proj.name
    alias = build_alias_table(topo_pairs or [])
    evidence = []

    def _norm(src_type, contract_p, events_p, verdict_p, raw):
        vstatus = raw.get("verdict_status")
        sel = raw.get("selected_pairs") or []
        tokens = list(sel) + list(raw.get("pair_tokens") or [])
        resolved, method, unresolved = resolve_pairs(tokens, alias)
        # 분류(strict)
        if raw.get("malformed"):
            cls = "HOLD"
        elif src_type == "session_log_observed_only":
            cls = "observed-only"
        elif not verdict_p:
            cls = "observed-only" if (events_p or contract_p) else "never-used"
        elif not _is_pass(vstatus):
            cls = "HOLD" if str(vstatus or "").strip().upper() in ("FAIL", "HOLD") else "observed-only"
        elif resolved:
            cls = "live-pass-thin-events" if raw.get("thin_events") else "pair-live-pass"
        elif unresolved:
            cls = "HOLD"   # verdict PASS 인데 pair 미해소 → 과장 금지
        else:
            cls = "observed-only"
        conf = 0.95 if cls == "pair-live-pass" else (0.8 if cls == "live-pass-thin-events" else 0.5)
        rel = lambda x: (str(Path(x).name) if x else None)
        rec = {
            "machine_id": machine_id, "project_id": project_id, "project_absolute_path": abs_path,
            "evidence_source_type": src_type,
            "contract_path": rel(contract_p), "events_path": rel(events_p), "verdict_path": rel(verdict_p),
            "verdict_status": (str(vstatus).upper() if vstatus else None),
            "verdict_reason": raw.get("verdict_reason"),
            "selected_pairs": sorted(resolved), "pair_resolution_method": method,
            "unresolved_pair_evidence": unresolved[:8],
            "validation_mode": raw.get("validation_mode"), "review_topology": raw.get("review_topology"),
            "iteration_count": raw.get("iteration_count"), "stop_reason": raw.get("stop_reason"),
            "mtime": raw.get("mtime"), "sha256": raw.get("sha256"),
            "confidence": conf, "classification": cls,
        }
        evidence.append(rec)
        return rec

    # 1) 표준 triad + 평면파일 + thin-events : _claude/loops · .claude/loops · _output/loops · _output/debates
    flat_groups = {}
    for root in ("_claude", ".claude", "_output"):
        for nm in ("loops", "debates"):
            d = proj / root / nm
            if not d.is_dir():
                continue
            try:
                entries = sorted(d.iterdir())[:MAX_SCAN]
            except Exception:
                continue
            for sub in entries:
                if sub.is_dir():  # 표준/thin triad
                    cf = next((sub / c for c in ("contract.yaml", "contract.yml", "contract.json") if (sub / c).is_file()), None)
                    vf = next((sub / v for v in ("verdict.json", "verdict.yaml", "verdict.yml") if (sub / v).is_file()), None)
                    ef = sub / "events.jsonl"
                    if not (cf or vf or ef.is_file()):
                        continue
                    raw = _extract_triad(cf, vf, ef if ef.is_file() else None)
                    src = "debate_verdict" if nm == "debates" else (
                        "standard_loop_triad" if (cf and vf and ef.is_file()) else "split_contract_verdict")
                    # _norm(src, contract_p, events_p, verdict_p, raw) — 인자 순서 정합(ralph 호출과 동일)
                    _norm(src, cf, (ef if ef.is_file() else None), vf, raw)
                elif sub.is_file():  # 평면파일 후보
                    stem, kind = _stem_of_flat(sub.name)
                    if stem:
                        flat_groups.setdefault((str(d), stem), {})[kind] = sub
    # 평면파일 그룹 정규화
    for (dpath, stem), parts in flat_groups.items():
        cf, ef, vf = parts.get("contract"), parts.get("events"), parts.get("verdict")
        raw = _extract_triad(cf, vf, ef)
        _norm("flat_loop_files", cf, ef, vf, raw)   # (contract_p, events_p, verdict_p) 정합

    # 2) Ralph markdown verdict : _output/ralph/verdict*.{md,json}
    rd = proj / "_output" / "ralph"
    if rd.is_dir():
        try:
            files = [f for f in sorted(rd.iterdir())[:MAX_SCAN]
                     if f.is_file() and f.name.lower().startswith("verdict")]
        except Exception:
            files = []
        for f in files:
            if f.suffix.lower() == ".md":
                md = _parse_ralph_md(f)
                if md.get("_malformed"):
                    _norm("malformed", None, None, f, {"malformed": True})
                    continue
                # 엄격: verdict PASS + (AC pass≥1) + pair alias 근거 필요
                ok = md.get("verdict") == "PASS" and (md.get("ac_pass_count", 0) >= 1) and not md.get("has_fail_marker")
                raw = {"verdict_status": "PASS" if ok else None,
                       "pair_tokens": md.get("pair_tokens"), "iteration_count": md.get("iteration_count"),
                       "mtime": _mtime(f), "sha256": _sha256(f),
                       "malformed": (not ok and bool(md.get("pair_tokens")))}
                _norm("ralph_markdown_verdict", None, None, f, raw)
            else:  # .json
                vd = _read_min(f)
                raw = {"verdict_status": vd.get("status") or vd.get("verdict"),
                       "selected_pairs": vd.get("selected_pairs"),
                       "mtime": _mtime(f), "sha256": _sha256(f), "malformed": vd.get("_malformed")}
                _norm("ralph_markdown_verdict", None, None, f, raw)

    live_pass_pairs = set()
    for e in evidence:
        if e["classification"] in ("pair-live-pass", "live-pass-thin-events"):
            live_pass_pairs.update(e["selected_pairs"])
    summary = {
        "machine_id": machine_id, "project_id": project_id, "project_absolute_path": abs_path,
        "evidence_count": len(evidence),
        "by_classification": {c: sum(1 for e in evidence if e["classification"] == c) for c in CLASSIFICATIONS},
        "by_source_type": {s: sum(1 for e in evidence if e["evidence_source_type"] == s) for s in EVIDENCE_SOURCE_TYPES},
        "live_pass_pairs": sorted(live_pass_pairs),
    }
    return {"evidence": evidence, "live_pass_pairs": live_pass_pairs, "summary": summary}


def _mtime(p: Path):
    try:
        return int(p.stat().st_mtime)
    except Exception:
        return None


def _extract_triad(cf, vf, ef) -> dict:
    """contract/verdict/events 파일 묶음 → raw dict(verdict_status·selected_pairs·thin_events 등)."""
    raw = {"malformed": False}
    sel = []
    if cf and Path(cf).is_file():
        c = _read_min(Path(cf))
        if c.get("_malformed"):
            raw["malformed"] = True
        raw["validation_mode"] = c.get("validation_mode")
        raw["review_topology"] = c.get("review_topology")
        # contract 의 selected_pairs / plan pair 계획(PAIR-B/PAIR-C·c-x 표기)
        if c.get("selected_pairs"):
            sp = c["selected_pairs"]
            sel += sp if isinstance(sp, list) else re.split(r"[,\s]+", str(sp))
        # 본문서 c-/x- 또는 PAIR-X 토큰(plan_approved pair evidence)
        try:
            ctext = Path(cf).read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]
            sel += re.findall(r"\b([cx]-[a-z][a-z0-9_]+)\b", ctext)
        except Exception:
            pass
        raw["mtime"] = _mtime(Path(cf))
    if vf and Path(vf).is_file():
        vd = _read_min(Path(vf))
        if vd.get("_malformed"):
            raw["malformed"] = True
        v_field, s_field = vd.get("verdict"), vd.get("status")
        if v_field is not None and s_field is not None and \
           str(v_field).strip().upper() != str(s_field).strip().upper():
            raw["malformed"] = True  # 충돌 → malformed
        raw["verdict_status"] = s_field if s_field is not None else v_field
        raw["verdict_reason"] = vd.get("reason") or vd.get("stop_reason")
        raw["stop_reason"] = vd.get("reason") or vd.get("stop_reason")
        if vd.get("selected_pairs"):
            sp = vd["selected_pairs"]
            sel += sp if isinstance(sp, list) else re.split(r"[,\s]+", str(sp))
        raw["sha256"] = _sha256(Path(vf))
        raw.setdefault("mtime", _mtime(Path(vf)))
    # events: pair 토큰 + thin 판정
    ev_tokens, n_lines = [], 0
    has_pair_event = False
    if ef and Path(ef).is_file():
        try:
            for line in Path(ef).read_text(encoding="utf-8", errors="replace")[:MAX_BYTES].splitlines():
                ls = line.strip()
                if not ls:
                    continue
                n_lines += 1
                try:
                    ev = json.loads(ls)
                except Exception:
                    continue
                if not isinstance(ev, dict):
                    continue
                en = str(ev.get("event") or "")
                m = re.match(r"verifier_[cx]_(.+)$", en)
                if m:
                    ev_tokens.append(m.group(1))
                    has_pair_event = True
                d = ev.get("data")
                if isinstance(d, dict):
                    for k in ("agent", "pair", "c_agent", "x_agent"):
                        if isinstance(d.get(k), str):
                            ev_tokens += [t for t in re.split(r"[/,+\s]+", d[k]) if t]
                            has_pair_event = True
                    for k in ("agents", "pairs", "selected_pairs"):
                        if isinstance(d.get(k), list):
                            ev_tokens += [str(t) for t in d[k] if t]
                            has_pair_event = True
        except Exception:
            raw["malformed"] = True
    sel += ev_tokens
    # thin-events: events 는 있으나 pair 이벤트 없음 + contract/verdict 에서 pair 확보
    raw["thin_events"] = bool(ef) and not has_pair_event and bool(sel)
    raw["selected_pairs"] = sel
    return raw


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--machine", default=None)
    ap.add_argument("--topology", default=None, help="PAIR_TOPOLOGY.yaml (alias)")
    args = ap.parse_args()
    topo = []
    topo_path = None
    if args.topology and Path(args.topology).is_file():
        topo_path = Path(args.topology)
    else:
        # 자동 탐색 (fleet_summary.py:704-706 과 동형): .claude/PAIR_TOPOLOGY.yaml → .claude/domain/ → 루트.
        # --topology 미지정 시에도 pair 해소가 되도록 (미지정 → 빈 alias → 모든 pair unresolved→HOLD 오분류 방지).
        for _cand in (Path(args.project) / ".claude" / "PAIR_TOPOLOGY.yaml",
                      Path(args.project) / ".claude" / "domain" / "PAIR_TOPOLOGY.yaml",
                      Path(args.project) / "PAIR_TOPOLOGY.yaml"):
            if _cand.is_file():
                topo_path = _cand
                break
    if topo_path:
        # fleet_summary.parse_pair_topology 와 동형 최소 파서
        cur, pairs = None, []
        for ln in topo_path.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s.startswith("- pair_id:"):
                cur = {"pair_id": s.split(":", 1)[1].strip()}
                pairs.append(cur)
            elif cur and s.startswith("c_agent:"):
                cur["c_agent"] = s.split(":", 1)[1].strip().strip('"\'')
            elif cur and s.startswith("x_agent:"):
                cur["x_agent"] = s.split(":", 1)[1].strip().strip('"\'')
        topo = pairs
    else:
        import sys as _sys
        print("[warn] PAIR_TOPOLOGY.yaml 없음 → pair resolution 비활성(pair 토큰 unresolved→HOLD). --topology 로 명시 가능.", file=_sys.stderr)
    out = scan_ledger_evidence(args.project, args.machine, topo)
    print(json.dumps(out["summary"], ensure_ascii=False, indent=2))
    for e in out["evidence"]:
        print(json.dumps({k: e[k] for k in ("evidence_source_type", "classification", "verdict_status",
                                            "selected_pairs", "pair_resolution_method", "confidence")},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
