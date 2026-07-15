#!/usr/bin/env python3
"""verification_gate_l2.py — L2 독립검증(codex refute). 4-layer 계약 §3 L2.

역할: L1이 flag한 주장을 codex(gpt-5.6-sol, 다른 모델)로 '반박 시도'시켜 독립 관점 확보.
      상관오류(같은 모델=같은 편향)를 줄이는 교차모델 층.

⚠️ 설계 제약(정직):
  - codex latency = 분 단위 → **인라인 Stop 훅 동기호출 금지**(모든 응답 지연). on-demand/canary 전용.
  - **자동 hard 차단 아님** — L2 결과는 warn(finding에 기록). 최종 차단은 L4가 층 합의로 결정.
  - codex 실패(timeout/파싱불가) → **HOLD**(가짜 verdict 생성 0, feedback_codex_cli_only).
  - codex = CLI 직접(`codex exec`), 플러그인 금지. stdin 닫음(exec stdin block 함정 회피).

CLI: echo '{"claim":"...","evidence":["..."]}' | python3 verification_gate_l2.py [--timeout N] [--model M]
테스트 주입: GATE_CODEX_CMD='bash -c ...' 로 codex 대체(실호출 없이 파싱/HOLD 검증).
"""
import os, sys, json, re, subprocess

MODEL_DEFAULT = "gpt-5.6-sol"
TIMEOUT_DEFAULT = 300

REFUTE_PROMPT = """You are an adversarial fact-checker. A coding agent produced the CLAIM below.
Try to REFUTE it using ONLY the EVIDENCE. Be skeptical. If the evidence is insufficient to
either confirm or refute, answer "hold" (do NOT guess).

CLAIM:
{claim}

EVIDENCE:
{evidence}

Respond with EXACTLY one JSON line and nothing else:
{{"verdict":"refuted|upheld|hold","reason":"<one short sentence>"}}
- refuted = evidence contradicts the claim
- upheld  = evidence supports the claim
- hold    = evidence insufficient / cannot tell
"""

VALID = {"refuted", "upheld", "hold"}


def _parse_verdict(text):
    """codex 출력에서 마지막 {"verdict":...} json 라인 파싱. 못 찾으면 None."""
    if not text:
        return None
    for m in reversed(list(re.finditer(r'\{[^{}]*"verdict"\s*:\s*"(\w+)"[^{}]*\}', text))):
        v = m.group(1).lower()
        if v in VALID:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = {"verdict": v, "reason": ""}
            obj["verdict"] = v
            obj.setdefault("reason", "")
            return obj
    return None


def _tool_log(model, claim, verdict):
    try:
        sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "lib"))
        from tool_log import log_call
        log_call(tool="codex", model=model, query=f"L2 refute: {claim[:80]}",
                 project="this-project", extra={"layer": "L2", "verdict": verdict})
    except Exception:
        pass


def codex_refute(claim, evidence, model=MODEL_DEFAULT, timeout=TIMEOUT_DEFAULT, codex_bin="codex"):
    """단일 주장을 codex로 반박 시도. 반환 {verdict, reason, raw, ok}. 실패=HOLD."""
    ev = "\n".join(evidence) if isinstance(evidence, (list, tuple)) else str(evidence or "")
    prompt = REFUTE_PROMPT.format(claim=str(claim), evidence=ev or "(no evidence provided)")
    override = os.environ.get("GATE_CODEX_CMD")
    try:
        if override:                                   # 테스트 주입: stdin 으로 prompt 전달
            p = subprocess.run(["bash", "-c", override], input=prompt,
                               capture_output=True, text=True, timeout=timeout, start_new_session=True)
        else:                                          # 실 codex: prompt=arg, stdin 닫음(block 회피)
            p = subprocess.run([codex_bin, "exec", "--model", model, "--sandbox", "read-only",
                                "--skip-git-repo-check", prompt], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=timeout, start_new_session=True)
    except subprocess.TimeoutExpired:
        r = {"verdict": "hold", "reason": "codex timeout", "raw": "", "ok": False}
        _tool_log(model, str(claim), "hold(timeout)"); return r
    except Exception as e:
        return {"verdict": "hold", "reason": f"codex error: {e}", "raw": "", "ok": False}
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    parsed = _parse_verdict(out)
    if parsed is None:
        r = {"verdict": "hold", "reason": "no parseable verdict (HOLD, 가짜생성 금지)", "raw": out[-400:], "ok": False}
        _tool_log(model, str(claim), "hold(unparseable)"); return r
    parsed.update({"raw": out[-400:], "ok": True})
    _tool_log(model, str(claim), parsed["verdict"])
    return parsed


def as_finding(claim, refute_result):
    """L2 결과를 L4 합성용 finding-유사 dict 로. 자동 hard 아님(mode=soft/warn)."""
    v = refute_result.get("verdict", "hold")
    return {"detector": "l2_codex_refute", "claim": claim, "verdict": v,
            "would_block": v == "refuted",           # 반박 성공 = 경고 신호(차단은 L4)
            "mode": "soft", "hold": v == "hold",
            "reason": refute_result.get("reason", "")}


def _main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        print(json.dumps({"error": "bad-json", "verdict": "hold"})); return 0
    claim = payload.get("claim", "")
    if not claim:
        print(json.dumps({"error": "no claim", "verdict": "hold"})); return 0
    model = payload.get("model", MODEL_DEFAULT)
    timeout = int(payload.get("timeout", TIMEOUT_DEFAULT))
    r = codex_refute(claim, payload.get("evidence", []), model=model, timeout=timeout)
    print(json.dumps(as_finding(claim, r), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # argparse-lite
    if "--timeout" in sys.argv or "--model" in sys.argv:
        pass  # payload 로 전달 권장(stdin JSON)
    sys.exit(_main())
