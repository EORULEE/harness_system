#!/usr/bin/env python3
"""decision_receipt.py — decision 상태모델 + mini-contract 2종 (v1.1 ADOPT #3+#4).

상태모델(설계 §2):
  NOT_YET_RESOLVED               항상 수락(안전 상태 — "none-known"류는 전부 여기로).
  BLOCKED_UNDER_TESTED_METHODS   agent 선언 최대치. 선등록 method set + method 별 **실패** evidence.
                                 untried = registered − attempted 로 **기계 계산**(자유문장 불가).
  BLOCKED_UNDER_POLICY           정책 인용문 실재 검증(--policy-quote 가 파일에 실제 존재) 필수.
  ROOT_CAUSE_HYPOTHESIS          원인 주장의 기본(유일 허용) 형태.
거부: BLOCKED / GLOBALLY_IMPOSSIBLE / DECLARE_ROOT_CAUSE(확정형).

evidence 결속(codex 코드리뷰 BLOCKER 1~4 해소):
  - host 결속 엄격: --host 지정 시 receipt subject 가 그 host 여야 함(**local 면제 없음**).
    --host 미지정 = local 선언 → receipt 도 local 이어야 함.
  - 실패 증거 강제: BLOCKED 류 attempts 는 obs receipt ok==false 또는 ledger success==false 만.
    성공/무관 receipt 는 실패를 증명하지 않음.
  - ledger(tu_*) 이벤트는 controller 에서 실행된 것 — **host 결속 불가** → 원격 선언에는 사용 불가
    (원격 실패는 measure.py 의 ok=false receipt 로만).
  - 동일 evidence 재사용 금지(1 receipt 가 전 method 를 닫는 laundering 차단).
  - 시간 순서: method 선등록 ts ≤ evidence ts (등록이 시도에 선행해야 'predefined').
정직 한계(문서화): method_id ↔ 실행된 command 의 의미적 상응은 기계 검증하지 않는다(범용
  ontology 거부 — 감사 stream 이 담당). turn 결속은 runtime _current_turn.txt 기반.

사용:
  decision_receipt.py register-methods --task l3-venv --methods "venv_pip,conda,get_pip"
  decision_receipt.py declare --type BLOCKED_UNDER_TESTED_METHODS --task l3-venv \
      --host server-a --attempted "venv_pip=obs:abc,conda=obs:def" --summary "..."
  decision_receipt.py declare --type ROOT_CAUSE_HYPOTHESIS --summary "SMR 영향 가능성(미검증)"
  decision_receipt.py declare --type BLOCKED_UNDER_POLICY --policy-ref CLAUDE.md \
      --policy-quote "코인·실거래 = hard-refuse"
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vgate_common import (CLAUDE_DIR, DECISIONS, METHODS, RECEIPTS, RUNTIME,
                          flock_append, gate_fingerprint, load_jsonl, make_id, now)

LEDGER = RUNTIME / "tool-use.jsonl"
CURRENT_TURN = RUNTIME / "_current_turn.txt"
PROJECT_ROOT = Path(CLAUDE_DIR).parent

AGENT_STATES = {"NOT_YET_RESOLVED", "BLOCKED_UNDER_TESTED_METHODS",
                "BLOCKED_UNDER_POLICY", "ROOT_CAUSE_HYPOTHESIS"}
REJECT_STATES = {
    "BLOCKED": "BLOCKED_UNDER_TESTED_METHODS(선등록 method 전부 실패 시) 또는 NOT_YET_RESOLVED 로 강등하십시오.",
    "GLOBALLY_IMPOSSIBLE": "open-world 보편부정은 에이전트 선언 불가(사용자 결정 전용). NOT_YET_RESOLVED 로 강등하십시오.",
    "DECLARE_ROOT_CAUSE": "확정 원인은 intervention/contrastive/external_review 없이 선언 불가. ROOT_CAUSE_HYPOTHESIS 로 강등하십시오.",
    "ROOT_CAUSE_CONFIRMED": "확정 원인은 intervention/contrastive/external_review 없이 선언 불가. ROOT_CAUSE_HYPOTHESIS 로 강등하십시오.",
}


def _turn() -> str:
    try:
        return CURRENT_TURN.read_text(encoding="utf-8").strip()[:80]
    except Exception:
        return ""


def _reject(code: str, msg: str, extra: dict | None = None) -> int:
    print(json.dumps({"accepted": False, "reject_code": code, "message": msg,
                      **(extra or {})}, ensure_ascii=False, indent=2))
    return 1


def _accept(rec: dict) -> int:
    rec["accepted"] = True
    rec["turn"] = _turn()  # M5: orchestrator 가 현재 turn 과 대조
    rec["gate_fp"] = gate_fingerprint()
    rec["decision_id"] = make_id("dec", {k: rec.get(k) for k in ("ts", "type", "task", "summary")})
    flock_append(DECISIONS, rec)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def _host_match(subject: dict, host: str | None) -> tuple[bool, str]:
    """B1: local 면제 없는 엄격 host 결속."""
    alias = subject.get("requested_alias", "")
    rhost = subject.get("remote_hostname", "")
    if host:
        if alias == host or rhost == host:
            return True, ""
        return False, f"receipt host(alias='{alias}',hostname='{rhost}') ≠ 선언 host '{host}'"
    if alias in ("local", ""):
        return True, ""
    return False, f"local 선언에 원격 receipt(alias='{alias}') 사용 불가 — --host {alias} 로 선언하십시오"


def _resolve_evidence(ref: str, host: str | None,
                      require_failure: bool = False, min_ts: str | None = None) -> dict:
    """evidence 참조 해석 + 결속 검사. 반환 {ok, assurance, why...}."""
    if ref.startswith("obs:"):
        for r in load_jsonl(RECEIPTS):
            if r.get("receipt_id") != ref:
                continue
            ok_host, why = _host_match(r.get("subject") or {}, host)
            if not ok_host:
                return {"ok": False, "why": why + " (M4 결속)"}
            if require_failure and r.get("ok") is not False:
                return {"ok": False,
                        "why": f"receipt {ref} 는 성공/비실패 관측(ok={r.get('ok')}) — 실패 증거가 될 수 없음"}
            if min_ts and str(r.get("ts", "")) < min_ts:
                return {"ok": False,
                        "why": f"evidence ts {r.get('ts')} < method 등록 ts {min_ts} — 선등록이 시도에 선행해야 함"}
            return {"ok": True, "assurance": "typed_measure",
                    "observable": r.get("observable"), "receipt_ok": r.get("ok"),
                    "ts": r.get("ts")}
        return {"ok": False, "why": f"receipt {ref} 미존재(receipts.jsonl)"}
    if ref.startswith("tu_") or ref.startswith("toolu_"):
        if host and host != "local":
            return {"ok": False,
                    "why": "ledger exec 이벤트는 controller 실행 — 원격 host 결속 불가. "
                           "원격 실패는 measure.py(ok=false receipt)로 증거화하십시오"}
        for r in load_jsonl(LEDGER):
            if r.get("tool_use_id") == ref and r.get("kind") == "exec":
                if require_failure:
                    if "success" not in r:
                        return {"ok": False,
                                "why": f"ledger {ref} 에 success 필드 없음 — 실패 여부 provenance 부족"}
                    if r.get("success") is not False:
                        return {"ok": False,
                                "why": f"ledger {ref} 는 성공 이벤트 — 실패 증거가 될 수 없음"}
                if min_ts and str(r.get("ts", "")) < min_ts:
                    return {"ok": False, "why": f"evidence ts < method 등록 ts {min_ts}"}
                return {"ok": True, "assurance": "untyped_attempt", "success": r.get("success")}
        return {"ok": False, "why": f"ledger 에 kind=exec tool_use_id={ref} 미존재"}
    return {"ok": False, "why": f"알 수 없는 evidence 참조 형식: {ref} (obs:* 또는 tu_*/toolu_*)"}


def cmd_register_methods(args) -> int:
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    if not methods:
        return _reject("EMPTY_METHODS", "method 목록이 비어 있습니다.")
    rec = {"ts": now(), "task": args.task, "methods": methods, "turn": _turn()}
    flock_append(METHODS, rec)
    print(json.dumps({"registered": True, **rec}, ensure_ascii=False, indent=2))
    return 0


def _registration(task: str) -> dict:
    reg: dict = {}
    for r in load_jsonl(METHODS):
        if r.get("task") == task:
            reg = r  # 최신 등록이 정본
    return reg


def cmd_declare(args) -> int:
    dtype = args.type.strip()
    if dtype in REJECT_STATES:
        return _reject("STATE_NOT_DECLARABLE", REJECT_STATES[dtype])
    if dtype not in AGENT_STATES:
        return _reject("UNKNOWN_STATE", f"허용 상태: {sorted(AGENT_STATES)}")

    rec = {"ts": now(), "type": dtype, "task": args.task or "",
           "summary": (args.summary or "")[:400], "host": args.host or ""}

    if dtype == "NOT_YET_RESOLVED":
        return _accept(rec)

    if dtype == "ROOT_CAUSE_HYPOTHESIS":
        ev = {}
        for ref in [e.strip() for e in (args.evidence or "").split(",") if e.strip()]:
            ev[ref] = _resolve_evidence(ref, args.host)
        rec["evidence"] = ev
        rec["modality"] = "hypothesis"
        return _accept(rec)

    if dtype == "BLOCKED_UNDER_POLICY":
        # M6: 임의 파일 존재만으론 불가 — 인용문이 정책 위치의 파일에 실재해야 함.
        if not args.policy_ref or not args.policy_quote:
            return _reject("POLICY_REF_REQUIRED", "--policy-ref <file[:line]> 와 --policy-quote '<인용문>' 필수.")
        pfile = Path(args.policy_ref.split(":")[0])
        try:
            resolved = pfile.resolve()
            allowed = (str(resolved).startswith(str(PROJECT_ROOT.resolve()))
                       or str(resolved).startswith(str(Path.home() / ".claude")))
        except Exception:
            allowed = False
        if not allowed:
            return _reject("POLICY_FILE_OUT_OF_SCOPE",
                           f"정책 파일은 프로젝트 또는 ~/.claude 하위여야 함: {pfile}")
        if not pfile.exists():
            return _reject("POLICY_FILE_MISSING", f"정책 파일 미존재: {pfile}")
        try:
            content = pfile.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return _reject("POLICY_FILE_UNREADABLE", f"읽기 실패: {pfile}")
        if args.policy_quote not in content:
            return _reject("POLICY_QUOTE_NOT_FOUND",
                           f"인용문이 {pfile} 에 없음 — 실재 정책 문구를 그대로 인용하십시오.")
        rec["policy_ref"] = args.policy_ref
        rec["policy_quote"] = args.policy_quote[:200]
        return _accept(rec)

    # ── BLOCKED_UNDER_TESTED_METHODS — mini-contract 본체 ──
    if not args.task:
        return _reject("TASK_REQUIRED", "--task 필수(method set 결속).")
    reg = _registration(args.task)
    registered = reg.get("methods") or []
    if not registered:
        return _reject("METHODS_NOT_REGISTERED",
                       f"task '{args.task}' 에 선등록 method set 없음. "
                       "register-methods 로 유한 method 목록을 먼저 등록하십시오(시도 전에).")
    attempted: dict[str, str] = {}
    for pair in [p.strip() for p in (args.attempted or "").split(",") if p.strip()]:
        if "=" not in pair:
            return _reject("BAD_ATTEMPTED_FORMAT", f"'{pair}' — method_id=evidence_ref 형식 필요.")
        mid, ref = pair.split("=", 1)
        attempted[mid.strip()] = ref.strip()
    if not attempted:
        return _reject("NO_ATTEMPTS", "시도 0건으로는 선언 불가. NOT_YET_RESOLVED 를 사용하십시오.")
    unknown = [m for m in attempted if m not in registered]
    if unknown:
        return _reject("UNREGISTERED_METHOD",
                       f"선등록되지 않은 method: {unknown} (등록된 set: {registered})")
    # B3: 동일 evidence 재사용 금지(1 receipt 로 전 method 를 닫는 laundering 차단)
    refs = list(attempted.values())
    if len(set(refs)) != len(refs):
        dup = sorted({r for r in refs if refs.count(r) > 1})
        return _reject("SAME_EVIDENCE_REUSED",
                       f"동일 evidence 가 복수 method 에 재사용됨: {dup} — method 별 독립 시도 필요.")
    ev_result, bad = {}, []
    reg_ts = str(reg.get("ts", ""))
    for mid, ref in attempted.items():
        # B2+B4: 실패 증거 강제 + B3: 등록 선행(ts) 강제
        res = _resolve_evidence(ref, args.host, require_failure=True, min_ts=reg_ts or None)
        ev_result[mid] = {"ref": ref, **res}
        if not res["ok"]:
            bad.append(f"{mid}: {res['why']}")
    if bad:
        return _reject("EVIDENCE_UNRESOLVED", "; ".join(bad), {"evidence": ev_result})
    untried = [m for m in registered if m not in attempted]
    rec.update({"registered_methods": registered, "attempted": ev_result,
                "untried_computed": untried,
                "search_space_closed": len(untried) == 0})
    if untried:
        rec["note"] = (f"미시도 method 잔존 {untried} — 이 선언은 '시도한 방법이 실패했다'까지만 "
                       "의미하며 blocker 확정이 아님.")
    return _accept(rec)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register-methods")
    r.add_argument("--task", required=True); r.add_argument("--methods", required=True)
    d = sub.add_parser("declare")
    d.add_argument("--type", required=True); d.add_argument("--task")
    d.add_argument("--summary"); d.add_argument("--host")
    d.add_argument("--attempted", help="method_id=evidence_ref[,method_id=evidence_ref...]")
    d.add_argument("--evidence", help="obs:*/tu_* 참조(콤마 구분)")
    d.add_argument("--policy-ref"); d.add_argument("--policy-quote")
    args = ap.parse_args()
    return cmd_register_methods(args) if args.cmd == "register-methods" else cmd_declare(args)


if __name__ == "__main__":
    sys.exit(main())
