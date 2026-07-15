#!/usr/bin/env python3
"""codex_probe.py — codex(교차모델 x측) 가용성 실측 프로브.

목적: 2-pass 교차검증에서 "codex 되는지 불확실"이라고 넘기는 것을 차단(verify-or-abstain).
      실제 호출은 하지 않고(비용·행업 방지) **가용성만** 결정적으로 판정한다.

판정(available=true) 조건:
  - codex CLI 바이너리 존재 (구 플러그인 캐시 감지는 legacy 잔재 보고용 — 플러그인 제거 2026-07-13, CLI 전용)
  - 그리고 이 머신이 알려진 차단 환경이 아님(HARNESS_CODEX_BLOCKED=1 미설정)

출력: JSON 1줄 {available, reason, plugin, cli}. exit 0(항상).
사용: python3 codex_probe.py   또는   python3 codex_probe.py --quiet(available면 'yes'/아니면 'no')
"""
import json, os, shutil, sys
from pathlib import Path

HOME = Path(os.environ.get("HOME", str(Path.home())))

def _find_plugin():
    for p in (HOME / ".claude/plugins/cache/openai-codex",
              HOME / ".claude/plugins/marketplaces/openai-codex",
              HOME / ".claude/plugins/data/codex-openai-codex"):
        if p.exists():
            return str(p)
    return None

def _find_cli():
    # PATH + 흔한 위치(.npm-global/bin)
    c = shutil.which("codex")
    if c:
        return c
    cand = HOME / ".npm-global/bin/codex"
    return str(cand) if cand.exists() else None

def _live_verify(cli):
    """--live: CLI 실행 가능성만 실측(codex --version, 10s). 추론 호출 없음(비용 0)."""
    if not cli:
        return False, "cli 부재"
    import subprocess
    try:
        r = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=10)
        ver = (r.stdout or r.stderr).strip()[:40]
        return (r.returncode == 0), (ver if r.returncode == 0 else f"exit={r.returncode}")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}"

def probe(live=False):
    plugin = _find_plugin()
    cli = _find_cli()
    blocked = os.environ.get("HARNESS_CODEX_BLOCKED") == "1"
    if blocked:
        return {"available": False, "verified": False,
                "reason": "HARNESS_CODEX_BLOCKED=1 (이 머신 차단 지정)", "plugin": plugin, "cli": cli}
    if cli:
        # r53: 가용성 = CLI 기준(플러그인 제거 2026-07-13). plugin 필드 = legacy 잔재 보고 전용.
        out = {"available": True, "verified": None, "plugin": plugin, "cli": cli,
               "legacy_plugin_residue": bool(plugin),
               "reason": "codex CLI 정적 발견 — 설치≠동작: 실행 확인은 --live, 인증·모델 정책은 별개"}
        if live:
            ok, detail = _live_verify(cli)
            out["verified"] = ok
            out["reason"] = (f"CLI 실행 확인({detail}) — 인증·모델 정책은 별개" if ok
                             else f"정적 발견됐으나 실행 실패({detail}) — available≠동작 실증")
        return out
    return {"available": False, "verified": False,
            "reason": "codex CLI 미발견 — npm install -g @openai/codex 후 codex login (CLI 전용 정책)", "plugin": None, "cli": None}

def main():
    r = probe(live=("--live" in sys.argv))
    if "--quiet" in sys.argv:
        sys.stdout.write("yes" if r["available"] else "no")
    else:
        sys.stdout.write(json.dumps(r, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
