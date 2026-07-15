#!/usr/bin/env python3
"""verification_gate_l3.py — L3 근거성(groundedness) 층. LettuceDetect 어댑터. 4-layer 계약 L3.

역할: 주장(answer)이 '제공된 증거(context)'에 뒷받침되는지 토큰단위로 검사.
      뒷받침 안 되는 스팬 = 무근거/환각 신호(warn). 로컬 ModernBERT 추론 → LLM 재호출 0.

의존성: lettucedetect(+torch+transformers). **미설치 → graceful skip**(available=False, 차단 0).
설정:
  VGATE_L3_PYTHON = lettucedetect 설치된 python(venv) 경로. 없으면 현재 인터프리터 시도.
  VGATE_L3_MODEL  = HF 모델 경로(기본 KRLabsOrg lettucedect base modernbert en).
계약: 자동 hard 아님(soft/warn). 최종 차단은 L4 합성.
"""
import os, sys, json, subprocess

MODEL_DEFAULT = "KRLabsOrg/lettucedect-base-modernbert-en-v1"


def _l3_python():
    """lettucedetect 실행 python. 우선순위: VGATE_L3_PYTHON > ext4 전용 venv 자동탐지 > 현재.
    ⚠️ venv 는 반드시 네이티브 FS(ext4)에 — drvfs/9p(/mnt) 면 torch import 수분(사용불가)."""
    env = os.environ.get("VGATE_L3_PYTHON")
    if env:
        return env
    cand = os.path.join(os.path.expanduser("~"), ".cache", "vgate-l3-venv", "bin", "python")
    if os.path.isfile(cand):
        return cand
    return sys.executable


def _import_timeout():
    # ⚠️ torch import 는 FS I/O 에 민감(drvfs/9p 마운트면 수분). ext4 venv 권장.
    try:
        return int(os.environ.get("VGATE_L3_TIMEOUT", "120"))
    except Exception:
        return 120


def available():
    """lettucedetect import 가능 여부(설치 detector). 실패/타임아웃=graceful skip.
    timeout 은 VGATE_L3_TIMEOUT(기본 120s) — drvfs 느린 마운트 대비(ext4 venv면 ~10s)."""
    try:
        r = subprocess.run([_l3_python(), "-c", "import lettucedetect"],
                           capture_output=True, timeout=_import_timeout())
        return r.returncode == 0
    except Exception:
        return False


# 별도 인터프리터에서 실행(torch 무거움 → 격리). context 대비 answer 의 미지원 스팬 추출.
_DETECT = r'''
import sys, json
from lettucedetect.models.inference import HallucinationDetector
p = json.loads(sys.stdin.read())
det = HallucinationDetector(method="transformer", model_path=p["model"])
spans = det.predict(context=p["context"], question=p.get("question",""),
                    answer=p["answer"], output_format="spans")
print(json.dumps({"spans": spans}))
'''


def check_groundedness(answer, context_evidence, question="", timeout=180, model=None):
    """answer 가 context_evidence(증거)에 근거하는가. 반환:
       {available, unsupported_spans, would_block, mode, note}."""
    if not answer or not str(answer).strip():
        return {"available": True, "unsupported_spans": [], "would_block": False,
                "mode": "soft", "note": "empty answer"}
    if not available():
        return {"available": False, "unsupported_spans": [], "would_block": False,
                "mode": "soft", "note": "lettucedetect 미설치 — L3 graceful skip(차단 0)"}
    ctx = context_evidence if isinstance(context_evidence, list) else [str(context_evidence or "")]
    payload = json.dumps({"context": ctx, "answer": str(answer),
                          "question": question or "",
                          "model": model or os.environ.get("VGATE_L3_MODEL", MODEL_DEFAULT)})
    try:
        r = subprocess.run([_l3_python(), "-c", _DETECT], input=payload,
                           capture_output=True, text=True, timeout=timeout, start_new_session=True)
    except subprocess.TimeoutExpired:
        return {"available": True, "unsupported_spans": [], "would_block": False,
                "mode": "soft", "note": "L3 timeout — HOLD(차단 0)"}
    except Exception as e:
        return {"available": True, "unsupported_spans": [], "would_block": False,
                "mode": "soft", "note": f"L3 error: {e}"}
    try:
        spans = json.loads(r.stdout.strip().splitlines()[-1]).get("spans", [])
    except Exception:
        return {"available": True, "unsupported_spans": [], "would_block": False,
                "mode": "soft", "note": f"L3 파싱불가 — HOLD: {(r.stdout or r.stderr)[-200:]}"}
    return {"available": True, "unsupported_spans": spans, "would_block": bool(spans),
            "mode": "soft", "note": f"{len(spans)} unsupported span(s)"}


def as_finding(answer, result):
    """L4 합성용 finding-유사 dict. 자동 hard 아님(soft)."""
    return {"detector": "l3_groundedness", "would_block": result.get("would_block", False),
            "mode": "soft", "available": result.get("available", False),
            "unsupported": len(result.get("unsupported_spans", [])), "note": result.get("note", "")}


def _main():
    try:
        p = json.loads(sys.stdin.read() or "{}")
    except Exception:
        print(json.dumps({"error": "bad-json"})); return 0
    r = check_groundedness(p.get("answer", ""), p.get("evidence", p.get("context", [])),
                           question=p.get("question", ""), timeout=int(p.get("timeout", 180)))
    print(json.dumps(as_finding(p.get("answer", ""), r), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
