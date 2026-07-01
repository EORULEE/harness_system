#!/usr/bin/env python3
"""deploy_gate.py — 배포 preflight/postflight 게이트 (Integrity Audit + G8~G10 + 6-project live canary 교훈 내장).

읽기전용. 배포 전/후 다음을 자동 차단:
  Agent/Pair 미생성 · formal loop ledger 누락 · Dashboard 파싱 오류 · runtime 불일치 ·
  static-pass 과장 · account-bound 과장 · rollback 미검증.

재사용: fleet-dashboard/fleet_summary.py(collector — agent/pair/ledger 판정). 재구현 0.

사용:
  python3 scripts/deploy_gate.py preflight  --project <path> [--project ...] [--release <id>] [signals...]
  python3 scripts/deploy_gate.py postflight --project <path> ...                # 배포 후(live 포함)
signals: --new-machine --runtime-change --schema-change --pair-creation --prior-hold --active --small-delta --new-project --upgrade
출력: 표준 JSON (selected_audit_level·...·final_state).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / "fleet-dashboard" / "fleet_summary.py"
sys.path.insert(0, str(COLLECTOR.parent))
try:
    import fleet_summary as FS  # 재사용: agent/pair/ledger 판정(G8~G10)
except Exception as e:          # collector 부재 = DEEP 전제 미충족
    FS = None
    _FS_ERR = str(e)

# ── 금지 등식 (배포 과장 차단) ──
FORBIDDEN_EQUALITIES = [
    "declared != deployed", "deployed != wired", "static-pass != ACTIVE",
    "registered != authenticated", "uploaded != Published",
    "agent file != valid pair", "session_log task-call != formal loop verdict",
]


def select_audit_level(sig: dict) -> tuple:
    """FAST/STANDARD/DEEP 자동 선택 + 근거."""
    if sig.get("new_machine") or sig.get("runtime_change") or sig.get("schema_change") or sig.get("prior_hold"):
        rs = [k for k in ("new_machine", "runtime_change", "schema_change", "prior_hold") if sig.get(k)]
        return "DEEP", f"새 머신/OS·hook/runtime/schema 변경·이전 HOLD/FAIL 중 해당: {rs}"
    if sig.get("new_project") or sig.get("upgrade") or sig.get("pair_creation"):
        rs = [k for k in ("new_project", "upgrade", "pair_creation") if sig.get(k)]
        return "STANDARD", f"새 프로젝트·구버전 업그레이드·Pair 생성 필요 중 해당: {rs}"
    if sig.get("active") and sig.get("small_delta"):
        return "FAST", "동일 release·동일 머신·기존 ACTIVE·작은 delta"
    return "STANDARD", "기본값(FAST 조건 미충족·DEEP 트리거 없음)"


def _verdict(findings: list) -> str:
    sev = [f["severity"] for f in findings]
    if "CRITICAL" in sev:
        return "HOLD"
    if "HIGH" in sev:
        return "HOLD"
    if "MEDIUM" in sev:
        return "PASS-with-caveats"
    return "PASS"


def _obs(proj: Path) -> dict:
    if FS is None:
        return {}
    try:
        return FS.observe_agents_pairs(proj)
    except Exception as e:
        return {"_error": str(e)}


# ── Gate 2: 7단계 materialization ──
def gate_materialization(proj: Path, obs: dict) -> dict:
    f = []
    ai = obs.get("agent_inventory") or {}
    pt = obs.get("pair_topology") or {}
    es = obs.get("execution_summary") or {}
    stages = {
        "declared": bool(ai or pt),
        "packaged": (proj / "_output").exists() or (proj / ".claude").exists(),
        "deployed": (proj / ".claude").is_dir(),
        "wired": (proj / ".claude" / "settings.local.json").is_file() or (proj / ".claude" / "settings.json").is_file(),
        "static-verified": pt.get("status") == "configured" and pt.get("pair_count", 0) > 0,
        "live-verified": pt.get("live_pass_count", 0) > 0,
        "centrally-recorded": True,  # registry/SESSION_HISTORY 는 euru 중앙 — 별도 확인
    }
    # 금지 등식: declared≠deployed, deployed≠wired, static-pass≠ACTIVE
    if stages["declared"] and not stages["deployed"]:
        f.append({"severity": "HIGH", "msg": "declared 인데 deployed 아님(materialization-missing)"})
    if stages["deployed"] and not stages["wired"]:
        f.append({"severity": "MEDIUM", "msg": "deployed 인데 wired 아님(installed-unwired: settings 미배선)"})
    if stages["static-verified"] and not stages["live-verified"]:
        f.append({"severity": "MEDIUM", "msg": "static-pass 인데 live-verified 아님 → ACTIVE 과장 금지(static-pass 유지)"})
    return {"gate": "materialization_7stage", "stages": stages, "findings": f, "result": _verdict(f)}


# ── Gate 3: Agent/Pair ──
def gate_agent_pair(proj: Path, obs: dict) -> dict:
    f = []
    ai = obs.get("agent_inventory") or {}
    pt = obs.get("pair_topology") or {}
    # x-agent Write/Edit = CRITICAL
    xw = [a["name"] for a in ai.get("agents", []) if a.get("kind") == "x" and a.get("write_permission")]
    if xw:
        f.append({"severity": "CRITICAL", "msg": f"x-agent Write/Edit 가능 {len(xw)}: {xw[:5]}"})
    # framework-only = HIGH (schema/router 있으나 valid pair 0 + c/x 파일도 0)
    if pt.get("status") in ("cx-files-no-topology",) and pt.get("pair_count", 0) == 0 and pt.get("unpaired_cx_count", 0) > 0:
        f.append({"severity": "MEDIUM", "msg": f"c/x 파일 {pt.get('unpaired_cx_count')} 있으나 topology 없음(unpaired-cx) — valid pair 아님"})
    if pt.get("status") == "not-configured" and (proj / ".claude" / "skills" / "_loop-core").exists():
        f.append({"severity": "HIGH", "msg": "loop 인프라(schema/router)만 있고 실제 c/x agent 0 → framework-only"})
    # broken pair = HIGH
    if pt.get("broken_pair_count"):
        f.append({"severity": "HIGH", "msg": f"broken pair {pt['broken_pair_count']}(topology 있으나 c/x 파일 누락)"})
    # 금지 등식: agent 파일수 != valid pair
    cx_files = ai.get("c_agent_count", 0) + ai.get("x_agent_count", 0)
    valid = pt.get("pair_count", 0)
    note = f"valid pair={valid}(topology entry 기준), c/x 파일={cx_files} — 파일수÷2({cx_files // 2}) 아님"
    return {"gate": "agent_pair", "valid_pairs": valid, "x_write_violations": len(xw),
            "cx_files": cx_files, "note": note, "findings": f, "result": _verdict(f)}


# ── Gate 4: Formal loop ledger ──
def gate_formal_ledger(proj: Path, obs: dict, require_live: bool) -> dict:
    f = []
    pt = obs.get("pair_topology") or {}
    es = obs.get("execution_summary") or {}
    rr = obs.get("recent_runs") or []
    live = pt.get("live_pass_count", 0)
    observed = pt.get("observed_only_count", 0)
    # live-pass 는 contract+events+verdict+PASS 필요 (collector 가 이미 강제 — 여기선 정합 확인)
    for r in rr:
        if r.get("verdict") and not r.get("has_verdict_file"):
            f.append({"severity": "CRITICAL", "msg": "verdict 가 contract 출처(verdict 파일 없음) — live 과장 위험"})
    # 금지 등식: session_log != formal verdict (observed-only 는 ACTIVE 아님)
    if require_live and live == 0 and observed > 0:
        f.append({"severity": "HIGH", "msg": f"observed-only {observed}(session_log task-call만, formal ledger verdict 없음) → ACTIVE 금지"})
    if require_live and live == 0 and pt.get("pair_count", 0) > 0:
        f.append({"severity": "MEDIUM", "msg": "valid pair 있으나 formal loop ledger(live) 0 → static-pass(ACTIVE 아님)"})
    req = "pair-live-pass = contract.yaml + events.jsonl + verdict.json + status/verdict PASS. session_log-only=observed-only. project-local canary 는 해당 프로젝트 cwd 세션 실행(타 프로젝트 ledger 날조 금지)."
    return {"gate": "formal_loop_ledger", "live_pass": live, "observed_only": observed,
            "tracked_loops": es.get("tracked_loop_count", 0), "requirement": req,
            "findings": f, "result": _verdict(f)}


# ── Gate 5: Runtime parity ──
def gate_runtime(level: str) -> dict:
    f = []
    info = {"node": None, "python": None, "HOME": os.environ.get("HOME"), "cwd": os.getcwd()}
    try:
        info["node"] = subprocess.run(["bash", "-lc", "node -v"], capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception:
        pass
    try:
        info["python"] = sys.version.split()[0]
    except Exception:
        pass
    # DEEP: shell-snapshot 의 실제 hook runtime 까지(여기선 로컬 node 만; 원격은 배포 시 ssh 확인)
    if level == "DEEP":
        info["note"] = "DEEP: 대상 머신 shell-snapshot resolve node(실제 hook runtime)와 smoke node 비교 필요. system node ≠ hook runtime(G3 교훈)."
        # modern .mjs 훅 최소 node 18+ (Claude Code 요건)
        m = re.match(r"v(\d+)", info.get("node") or "")
        if m and int(m.group(1)) < 18:
            f.append({"severity": "HIGH", "msg": f"node {info['node']} < 18 — .mjs 훅 실행 위험. shell-snapshot nvm node 확인(system node와 분리)"})
    return {"gate": "runtime_parity", "runtime": info, "level": level, "findings": f, "result": _verdict(f)}


# ── Gate 6: Central integration ──
def gate_central(projs: list, fd_root: Path = ROOT) -> dict:
    f = []
    fd = fd_root / "fleet-dashboard"
    consistent = all((fd / x).is_file() for x in ("fleet_summary.py", "fleet_aggregate.py", "render.py", "fleet-registry.json"))
    if not consistent:
        f.append({"severity": "HIGH", "msg": "Fleet collector/aggregator/renderer/registry 정합 깨짐"})
    # vault commit parity / zotero / design 은 account-bound·external — 상태 분리(과장 차단)
    sep = {"registered != authenticated": "Zotero/MCP registered 가 authenticated 아님(account-bound)",
           "uploaded != Published": "Claude Design uploaded 가 Published 아님(비공개 유지)"}
    return {"gate": "central_integration", "collector_consistent": consistent,
            "state_separation": sep, "findings": f, "result": _verdict(f)}


# ── Gate 7: Rollback/security ──
def gate_rollback_security(release_dir: Path, settings_root: Path = ROOT) -> dict:
    f = []
    # archive 개방·manifest
    arch = release_dir.parent / "archive"
    openable = arch.is_dir() and any(arch.iterdir())
    if not openable:
        f.append({"severity": "HIGH", "msg": "rollback archive 없음/비어 있음"})
    # settings backup valid JSON
    for bak in settings_root.glob(".claude/settings*.bak*"):
        try:
            json.loads(bak.read_text(encoding="utf-8"))
        except Exception:
            f.append({"severity": "MEDIUM", "msg": f"settings 백업 유효 JSON 아님: {bak.name}"})
    # secret residual (release pkg + collector 출력)
    sec = 0
    pat = re.compile(r"ghp_[A-Za-z0-9]{20}|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}|ZOTERO_API_KEY=[A-Za-z0-9]")
    for p in release_dir.glob("*"):
        if p.is_file():
            try:
                sec += len(pat.findall(p.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                pass
    if sec:
        f.append({"severity": "CRITICAL", "msg": f"secret residual {sec}"})
    return {"gate": "rollback_security", "archive_openable": openable, "secret_residual": sec,
            "findings": f, "result": _verdict(f)}


def run(phase: str, projects: list, release_id: str, sig: dict, infra_root=None) -> dict:
    # infra_root: 미지정 시 ROOT(실배포 인프라 검사 — 기존 동작). 지정 시 fleet-dashboard·release/archive 를
    # 이 루트로 검사(smoke hermetic — 실제 인프라 존재여부에 좌우되지 않게, r13). 하위호환.
    infra = Path(infra_root) if infra_root else ROOT
    level, reason = select_audit_level(sig)
    require_live = (phase == "postflight")
    # FAST 는 핵심 게이트만, DEEP 는 전부
    run_runtime = level in ("STANDARD", "DEEP")
    run_central = level in ("STANDARD", "DEEP")
    skipped = []
    if not run_runtime:
        skipped.append({"check": "runtime_parity", "reason": f"{level}: 동일 머신·작은 delta(런타임 무변경 전제)"})
    if not run_central:
        skipped.append({"check": "central_integration", "reason": f"{level}: 중앙 자산 무변경 전제"})

    per_project = []
    for pp in projects:
        proj = Path(pp)
        obs = _obs(proj)
        gm = gate_materialization(proj, obs)
        ga = gate_agent_pair(proj, obs)
        gl = gate_formal_ledger(proj, obs, require_live)
        # (r12) name-collision 방지: 식별 키 = project_id + absolute_path (이름만으로 매칭 금지).
        per_project.append({"project": proj.name, "path": str(proj),
                            "project_absolute_path": str(proj.resolve()) if proj.exists() else str(proj),
                            "materialization": gm, "agent_pair": ga, "formal_loop_ledger": gl})
    rt = gate_runtime(level) if run_runtime else {"gate": "runtime_parity", "result": "SKIP"}
    ce = gate_central(projects, infra) if run_central else {"gate": "central_integration", "result": "SKIP"}
    rb = gate_rollback_security(infra / "_output" / "release" / "current", infra)

    all_results = ([g["result"] for pj in per_project for g in
                    (pj["materialization"], pj["agent_pair"], pj["formal_loop_ledger"])]
                   + [rt.get("result", "SKIP"), ce.get("result", "SKIP"), rb["result"]])
    final = "HOLD" if "HOLD" in all_results else ("CONDITIONAL" if "PASS-with-caveats" in all_results else "PASS")

    expected_mat = {pj["project"]: {k: v for k, v in pj["materialization"]["stages"].items()} for pj in per_project}
    return {
        "phase": phase,
        "baseline_release_id": release_id,
        "selected_audit_level": level,
        "selection_reason": reason,
        "forbidden_equalities": FORBIDDEN_EQUALITIES,
        "checks_to_run": ["materialization_7stage", "agent_pair", "formal_loop_ledger"]
                         + (["runtime_parity"] if run_runtime else []) + (["central_integration"] if run_central else [])
                         + ["rollback_security"],
        "checks_skipped_with_reason": skipped,
        "expected_materialization": expected_mat,
        "formal_loop_ledger_requirement": per_project[0]["formal_loop_ledger"]["requirement"] if per_project else None,
        "per_project": per_project,
        "runtime_parity": rt,
        "central_integration": ce,
        "rollback_security": rb,
        "preflight_result": final if phase == "preflight" else None,
        "postflight_result": final if phase == "postflight" else None,
        "final_state": final,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["preflight", "postflight"])
    ap.add_argument("--project", action="append", default=[])
    ap.add_argument("--release", default="current")
    ap.add_argument("--infra-root", default=None,
                    help="(test) central(fleet-dashboard)·rollback(release/archive) 검사를 이 루트로. 기본 ROOT(실배포). smoke hermetic 용.")
    for s in ("new-machine", "runtime-change", "schema-change", "pair-creation",
              "prior-hold", "active", "small-delta", "new-project", "upgrade"):
        ap.add_argument(f"--{s}", action="store_true")
    args = ap.parse_args()
    rel = args.release
    if rel == "current":
        cur = ROOT / "_output" / "release" / "current" / "SYSTEM_RELEASE.yaml"
        if cur.is_file():
            for ln in cur.read_text(encoding="utf-8").splitlines():
                if ln.startswith("release_id:"):
                    rel = ln.split(":", 1)[1].strip()
                    break
    sig = {s.replace("-", "_"): getattr(args, s.replace("-", "_")) for s in
           ("new_machine", "runtime_change", "schema_change", "pair_creation",
            "prior_hold", "active", "small_delta", "new_project", "upgrade")}
    out = run(args.phase, args.project, rel, sig, args.infra_root)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["final_state"] != "HOLD" else 2


if __name__ == "__main__":
    raise SystemExit(main())
