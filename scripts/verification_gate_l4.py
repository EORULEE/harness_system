#!/usr/bin/env python3
"""verification_gate_l4.py — L4 통합/합성 층. 4-layer 계약 L4.

역할: L1(기계)·L2(codex refute)·L3(근거성) finding 을 합성해 최종 tier/exit_code 결정.
합성 규칙(계약):
  - hard(exit2) = L1 high(=hard-mode would_block) 1건 이상  OR  ≥2개 층이 would_block 합의
  - warn(exit0) = 위 아님 + 어느 한 층이라도 would_block
  - pass(exit0) = 아무 층도 flag 안 함
⚠️ report→hard 승격은 canary FP 검토 후 **human-gate**(AC-L4). 이 모듈은 tier 를 '계산'만;
   실제 차단(hook exit2)은 승격 이후. L1/L2/L3 단독은 자동 hard 아님(합의 필요, L1 high 예외).

L2/L3 는 latency/의존성 때문에 on-demand → 인라인 합성에는 없을 수 있음(있으면 반영).
"""
from __future__ import annotations
import os, sys, json


def _wb(f):
    """finding(dataclass 또는 dict)에서 would_block 안전 추출."""
    if isinstance(f, dict):
        return bool(f.get("would_block"))
    return bool(getattr(f, "would_block", False))


def _mode(f):
    if isinstance(f, dict):
        return f.get("mode", "")
    return getattr(f, "mode", "")


def _name(f):
    if isinstance(f, dict):
        return f.get("detector", "?")
    return getattr(f, "detector", "?")


def compose(l1_result, l2_findings=None, l3_findings=None):
    """l1_result = verification_gate.evaluate() 반환. l2/l3_findings = list[dict] (선택)."""
    l1 = list((l1_result or {}).get("findings", []))
    l2 = list(l2_findings or [])
    l3 = list(l3_findings or [])

    # L1 high = hard-mode 이면서 would_block (부재/허위완료 등 확실 위반)
    l1_high = [f for f in l1 if _wb(f) and _mode(f) == "hard"]

    layers_flagged = []
    if any(_wb(f) for f in l1):
        layers_flagged.append("L1")
    if any(_wb(f) for f in l2):
        layers_flagged.append("L2")
    if any(_wb(f) for f in l3):
        layers_flagged.append("L3")

    hard = bool(l1_high) or len(layers_flagged) >= 2
    if hard:
        tier = "hard"
    elif layers_flagged:
        tier = "warn"
    else:
        tier = "pass"

    reasons = []
    if l1_high:
        reasons.append("L1 high: " + ",".join(sorted({_name(f) for f in l1_high})))
    if len(layers_flagged) >= 2:
        reasons.append("층 합의 ≥2: " + "+".join(layers_flagged))
    if tier == "warn":
        reasons.append("단일층 경고: " + "+".join(layers_flagged))

    return {"tier": tier,
            "exit_code": 2 if hard else 0,
            "layers_flagged": layers_flagged,
            "l1_high": sorted({_name(f) for f in l1_high}),
            "rationale": "; ".join(reasons) or "no findings",
            "counts": {"L1": len(l1), "L2": len(l2), "L3": len(l3)}}


def _main():
    """stdin JSON {output_text,user_input,tool_evidence, [l2_findings],[l3_findings]} → 합성 결과.
    L1 은 여기서 실행(verification_gate). L2/L3 는 미리 계산돼 주입되면 반영(on-demand)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verification_gate as vg
    try:
        p = json.loads(sys.stdin.read() or "{}")
    except Exception:
        print(json.dumps({"tier": "pass", "exit_code": 0, "err": "bad-json"})); return 0
    ctx = vg.Context(output_text=p.get("output_text", ""),
                     user_input=p.get("user_input", ""),
                     tool_evidence=list(p.get("tool_evidence", [])))
    l1 = vg.evaluate(ctx)
    result = compose(l1, p.get("l2_findings"), p.get("l3_findings"))
    # report-only(machine-safe): 가정적 판정은 would_* 로만, serialized exit_code=0(codex r54 #2).
    #    소비자가 exit_code 를 존중해도 차단 안 됨. 실제 hard 강제 = 별도 승인 활성화 설정.
    result["would_tier"] = result["tier"]
    result["would_exit_code"] = result["exit_code"]
    result["tier"] = "report-only"
    result["exit_code"] = 0
    result["report_only"] = True
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
