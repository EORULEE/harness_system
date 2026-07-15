#!/usr/bin/env python3
"""evidence_bundle.py — 2-pass 전제 evidence 번들 (결론 검토 전 단계).

목적(사용자 승인 2026-06-30):
- c/x verifier 가 '답변 품질·결론'을 보기 **전에**, 답변이 딛고 선 **전제(부재/위치/상태/release
  단정)의 evidence 를 먼저** 묶어 검사하게 한다.
- evidence 가 없는 전제는 'HOLD / Unverified' 로 표시 → 결론을 그 전제 위에 쌓지 않게,
  그리고 c/x 가 **같은 잘못된 전제를 공유하지 않게** 한다.

구현: absence_claim_guard.analyze() (단정 추출 + 증거 대조) + tool_use_audit 조회를 재사용.
      새 검출 로직을 만들지 않음(단일 진실원). 출력 = 전제별 premise_status 번들.

사용:
  echo "<draft conclusion text>" | python3 evidence_bundle.py --turn <id> [--format json]
  → {premises:[{claim,category,evidence_status,evidence_events}], any_hold, verifier_directive}
"""
from __future__ import annotations
import json, os, sys, argparse, subprocess
from pathlib import Path

THIS = Path(__file__).resolve()
GUARD = THIS.parent / "absence_claim_guard.py"
AUDIT = THIS.parent / "tool_use_audit.py"
sys.path.insert(0, str(THIS.parent))
try:
    from absence_claim_guard import load_evidence as _load_evidence  # 단일 진실원 재사용
except Exception:
    _load_evidence = None


def _evidence_fields(turn: str, evidence_file: str | None) -> dict:
    """ledger 이벤트에서 searched_paths / read_files / grep_queries 추출(사용자 G 스펙 필드)."""
    if _load_evidence is None:
        return {"searched_paths": [], "read_files": [], "grep_queries": []}
    try:
        events, _ = _load_evidence(turn, evidence_file)
    except Exception:
        events = []
    read_files, grep_queries, searched_paths = [], [], []
    for e in events:
        t = e.get("target", {}) or {}
        k = e.get("kind", "")
        if k == "read" and t.get("path"):
            read_files.append(t["path"])
        elif k == "search":
            if t.get("pattern"):
                grep_queries.append(t["pattern"])
            if t.get("path"):
                searched_paths.append(t["path"])
        elif k in ("glob", "list", "mcp-read"):
            for v in (t.get("glob"), t.get("path"), t.get("name_path"), t.get("query")):
                if v:
                    searched_paths.append(str(v))
        elif k == "exec":
            searched_paths += [p for p in (t.get("paths") or [])]
    dedup = lambda xs: sorted(set(xs))
    return {"searched_paths": dedup(searched_paths), "read_files": dedup(read_files),
            "grep_queries": dedup(grep_queries)}


def run_guard(text: str, turn: str, evidence_file: str | None) -> dict:
    cmd = [sys.executable, str(GUARD), "--format", "json", "--mode", "report"]
    if turn:
        cmd += ["--turn", turn]
    if evidence_file:
        cmd += ["--evidence-file", evidence_file]
    try:
        r = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=15)
    except Exception as e:
        # Codex V5: guard 가 돌지 않으면 침묵 통과 금지 → guard_error 표시.
        return {"_guard_error": f"spawn:{type(e).__name__}", "details": []}
    if r.returncode != 0:
        return {"_guard_error": f"rc={r.returncode}: {(r.stderr or '')[:200]}", "details": []}
    try:
        return json.loads(r.stdout or "{}")
    except Exception:
        return {"_guard_error": f"invalid-json: {(r.stdout or '')[:120]}", "details": []}


def build_bundle(text: str, turn: str, evidence_file: str | None) -> dict:
    g = run_guard(text, turn, evidence_file)
    guard_error = g.get("_guard_error")
    if guard_error:
        # detector 가 못 돌면 전제 검증 불가 → 결론을 그 위에 쌓지 말 것(any_hold=True).
        return {
            "turn": turn, "guard_error": guard_error, "evidence_events": 0,
            "premise_count": 0, "hold_count": 0, "any_hold": True,
            "premises": [],
            "verifier_directive": f"⛔ guard 실행 실패({guard_error}) — 전제 검증 불가. "
                                  "결론 검토 진행 금지, 'Unverified' 처리 후 사용자에 보고.",
        }
    premises = []
    for f in g.get("details", []):
        premises.append({
            "claim": f["claim"],
            "category": f["category"],
            "evidence_status": "evidenced" if f["evidenced"] else "HOLD/Unverified",
            "needs": f["why"],
        })
    any_hold = any(p["evidence_status"] != "evidenced" for p in premises)
    directive = (
        "전제 HOLD 있음 — c/x verifier 는 결론 품질 검토 **전에** 아래 미검증 전제부터 처리하라: "
        "(1) 근거(grep/read/search) 제시 또는 (2) 'Unverified/확실치 않음'으로 강등. "
        "두 verifier 가 같은 미검증 전제를 공유한 채 결론을 내지 말 것."
        if any_hold else
        "모든 전제 evidenced — 결론 검토 진행 가능."
    )
    ef = _evidence_fields(turn, evidence_file)
    return {
        "turn": turn,
        "evidence_events": g.get("evidence_events", 0),
        "evidence_unavailable": g.get("evidence_unavailable", False),
        "premise_count": len(premises),
        "hold_count": sum(1 for p in premises if p["evidence_status"] != "evidenced"),
        "any_hold": any_hold,
        "premises": premises,
        # ── 사용자 G 스펙 명명 필드(전제 evidence 번들) ──
        "required_facts": [p["claim"] for p in premises],                       # 결론이 딛는 전제(검증 대상)
        "searched_paths": ef["searched_paths"],
        "read_files": ef["read_files"],
        "grep_queries": ef["grep_queries"],
        "unresolved_assumptions": [p["claim"] for p in premises
                                   if p["evidence_status"] != "evidenced"],      # 증거 부족 = precondition HOLD
        "verifier_directive": directive,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file")
    ap.add_argument("--turn", default="")
    ap.add_argument("--evidence-file")
    ap.add_argument("--format", default="text", choices=["text", "json"])
    args = ap.parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else sys.stdin.read()
    bundle = build_bundle(text, args.turn, args.evidence_file)
    if args.format == "json":
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        print(f"전제 {bundle['premise_count']}건 · HOLD {bundle['hold_count']}건")
        for p in bundle["premises"]:
            mark = "✅" if p["evidence_status"] == "evidenced" else "⛔HOLD"
            print(f"  {mark} [{p['category']}] {p['claim'][:80]}")
        print("→", bundle["verifier_directive"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
