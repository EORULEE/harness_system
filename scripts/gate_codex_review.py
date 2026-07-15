#!/usr/bin/env python3
"""
gate_codex_review.py — Knowledge Promotion Gate 전용 scoped Codex 적대검토 호출.

Live canary 교훈 반영(최소 범위):
- (구)플러그인 adversarial-review 는 working-tree 전체를 전달했음 → Gate 는 원래 미사용. 플러그인 자체 제거됨(2026-07-13, CLI 전용).
- 대신 **scope-isolated direct invocation**: 후보 노트 + evidence 파일 allow-list 만 전달.
  · 중립 cwd(임시 디렉터리)에서 실행 · 파일 탐색 차단(self-contained 프롬프트, sandbox read-only)
  · 호출 전 secret scan(하나라도 걸리면 전송 차단) · 실제 전달 파일 manifest 기록
  · timeout 기본 1회 + 재시도 최대 1회 · 두 번 모두 실패 → HOLD(가짜 결과 생성 금지)
  · 프로세스 종료는 **PID/PGID 기반**(전역 pattern kill 금지) · timeout/exit/stderr 를 tool log 에 기록.

method 태그: "scoped-direct-invocation"(이 helper) — codex_review_ref 에 그대로 기록.

CLI:
  gate_codex_review.py --candidate <path> --evidence <path> [--evidence ...] \
      --out <review.md> [--manifest <m.json>] [--timeout 900] [--retries 1] [--codex-bin codex]
환경변수(테스트 주입): GATE_CODEX_CMD = codex 대체 명령(bash -c). PROMPT_FILE 로 프롬프트 경로 전달.
종료코드: 0=review 생성(ok) · 3=HOLD(2회 실패) · 4=secret_blocked · 5=allowlist_violation
"""
import os, sys, json, argparse, subprocess, tempfile, signal, hashlib, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from secret_masking import count_matches, residual_count, mask_secrets
except Exception:
    def count_matches(t): return 0
    def residual_count(t): return 0
    def mask_secrets(t): return t

METHOD = "scoped-direct-invocation"
RETRY_HARD_CAP = 1   # 기본 1회 + 재시도 최대 1회(총 2회)

CRITERIA = ("1 unsupported claim, 2 numeric/metric distortion, 3 over-generalization, "
            "4 fabricated statistical significance, 5 stale/superseded, 6 contradiction, "
            "7 source-conclusion mismatch, 8 missing scope/limitations, "
            "9 sensitive-info/disclosure risk, 10 alternative explanation or counterexample")

def _tool_log(**kw):
    try:
        sys.path.insert(0, str(Path.home()/".claude"/"lib"))
        from tool_log import log_call
        log_call(**kw)
    except Exception:
        pass

def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build_allowlist(candidate, evidence):
    """allow-list = 후보 + evidence 파일만. 디렉터리/부재/중복 거부(working-tree 전체 전달 차단)."""
    files, seen = [], set()
    for p in [candidate] + list(evidence):
        ap = os.path.abspath(p)
        if not os.path.isfile(ap):
            raise ValueError(f"allowlist 위반: 파일 아님/부재 → {p} (디렉터리·glob·working-tree 금지)")
        if ap in seen:
            continue
        seen.add(ap); files.append(ap)
    return files

def secret_precheck(files):
    """전송 전 각 파일 secret scan. 하나라도 걸리면 차단(전송 안 함)."""
    hits = []
    for f in files:
        t = Path(f).read_text(encoding="utf-8", errors="ignore")
        n = count_matches(t) + residual_count(t)
        if n > 0:
            hits.append((f, n))
    return hits

def assemble_prompt(files):
    parts = [
        "You are an adversarial reviewer. Review ONLY the candidate + evidence below.",
        "Do NOT request files, do NOT explore any repository, do NOT make changes. Output only rebuttals.",
        f"\nADVERSARIAL CRITERIA (check each): {CRITERIA}.",
        "Be concise: one specific rebuttal per applicable criterion. "
        "End with one-line verdict: PROMOTE-AS-IS / PROMOTE-WITH-EDITS / HOLD.\n",
    ]
    for f in files:
        parts.append(f"\n===== FILE: {os.path.basename(f)} =====\n")
        parts.append(Path(f).read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)

def run_once(prompt, timeout, codex_bin, neutral_cwd):
    """단 1회 codex 실행. PID/PGID 기반 종료(전역 pattern kill 미사용). 반환: (ok, stdout, exit_code, timed_out, stderr_tail)."""
    pf = os.path.join(neutral_cwd, "_prompt.txt")
    Path(pf).write_text(prompt, encoding="utf-8")
    inj = os.environ.get("GATE_CODEX_CMD")
    if inj:
        cmd = ["bash", "-c", inj]
        env = {**os.environ, "PROMPT_FILE": pf}
    else:
        cmd = [codex_bin, "exec", "--model", "gpt-5.6-sol", "--sandbox", "read-only",
               "--skip-git-repo-check", prompt]
        env = dict(os.environ)
    # start_new_session=True → 자체 프로세스 그룹. timeout 시 그 PGID 만 kill(전역 pattern kill 아님).
    proc = subprocess.Popen(cmd, stdin=open(pf, "rb"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=neutral_cwd, env=env, start_new_session=True)
    pid = proc.pid
    try:
        out, err = proc.communicate(timeout=timeout)
        # stderr_tail 은 tool_log·반환값으로 흘러가므로 저장 전 secret 마스킹(codex #9 해소).
        errtail = mask_secrets(err.decode("utf-8", "ignore"))[-500:]
        return (proc.returncode == 0 and bool(out.strip()), out.decode("utf-8", "ignore"),
                proc.returncode, False, errtail, pid)
    except subprocess.TimeoutExpired:
        # 이 PID 의 프로세스 그룹만 종료(전역 pattern kill 미사용)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try: proc.kill()
            except Exception: pass
        try: out, err = proc.communicate(timeout=10)
        except Exception: out, err = b"", b""
        errtail = mask_secrets(err.decode("utf-8", "ignore"))[-500:]
        return (False, out.decode("utf-8", "ignore"), 124, True, errtail, pid)

def review(candidate, evidence, out_path, manifest_path, timeout, retries, codex_bin):
    files = build_allowlist(candidate, evidence)              # working-tree 전체 차단
    hits = secret_precheck(files)
    if hits:
        _tool_log(tool="gate-codex-review", query="secret_blocked before transmit",
                  model="gpt-5.6-sol", tokens_in=0, tokens_out=0, sources=len(files))
        return {"status": "secret_blocked", "method": METHOD, "transmitted": [],
                "secret_files": [os.path.basename(f) for f, _ in hits], "exit_code": 5}
    # manifest(실제 전달 파일 기록)
    manifest = {"method": METHOD, "transmitted": [
        {"file": f, "sha256": sha256(f), "bytes": os.path.getsize(f)} for f in files]}
    if manifest_path:
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    prompt = assemble_prompt(files)
    retries = min(int(retries), RETRY_HARD_CAP)               # 재시도 최대 1회 강제
    attempts, last = 0, None
    with tempfile.TemporaryDirectory(prefix="gate_codex_") as nd:   # 중립 cwd
        for attempt in range(retries + 1):                   # 1 + retries(≤1) = 최대 2회
            attempts += 1
            ok, out, code, timed_out, errtail, pid = run_once(prompt, timeout, codex_bin, nd)
            _tool_log(tool="gate-codex-review",
                      query=f"attempt={attempts} exit={code} timed_out={timed_out} pid={pid} stderr={errtail[:120]}",
                      model="gpt-5.6-sol", tokens_in=0, tokens_out=0, sources=len(files))
            last = {"exit_code": code, "timed_out": timed_out, "stderr_tail": errtail}
            if ok:
                Path(out_path).write_text(
                    f"# Codex adversarial review (method={METHOD})\n"
                    f"date_attempts: {attempts} · exit: {code}\n"
                    f"transmitted: {[os.path.basename(f) for f in files]}\n\n" + out, encoding="utf-8")
                # r17 gate-integrity(IMP-01): 검토 산출물을 감사 로그에 해시-바인딩 기록.
                #   verdict 는 리뷰 본문의 마지막 verdict 행에서 추출(없으면 unparsed). 기록 실패해도 리뷰는 유효(fail-open).
                try:
                    import hashlib as _hl, subprocess as _sp
                    _v = "unparsed"
                    for _ln in reversed(out.strip().splitlines()):
                        if "verdict" in _ln.lower():
                            _v = _ln.strip()[:40]; break
                    _sp.run([sys.executable, str(Path(__file__).resolve().parent / "codex_review_log.py"),
                             "record", "--target", os.path.basename(str(candidate))[:200],
                             "--command", "gate-codex-review(scoped-direct)",
                             "--verdict", _v, "--review-file", str(out_path),
                             "--prompt-sha256", _hl.sha256(prompt.encode("utf-8")).hexdigest()],
                            timeout=15, capture_output=True)
                except Exception as _e:
                    sys.stderr.write(f"gate: codex_review_log 기록 실패({_e}) — 리뷰 자체는 유효\n")
                return {"status": "ok", "method": METHOD,
                        "transmitted": [os.path.basename(f) for f in files],
                        "review_path": out_path, "manifest": manifest_path,
                        "attempts": attempts, "exit_code": code, "timed_out": False}
    # 2회 모두 실패 → HOLD(가짜 결과 생성 금지)
    return {"status": "hold", "method": METHOD,
            "transmitted": [os.path.basename(f) for f in files],
            "attempts": attempts, **(last or {}),
            "reason": "codex 2회 실패(timeout/error) — 가짜 검토 생성 금지, HOLD"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--evidence", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default="")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--codex-bin", default="codex")
    a = ap.parse_args()
    try:
        res = review(a.candidate, a.evidence, a.out, a.manifest or None, a.timeout, a.retries, a.codex_bin)
    except ValueError as e:
        print(json.dumps({"status": "allowlist_violation", "error": str(e), "exit_code": 5}, ensure_ascii=False))
        sys.exit(5)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit({"ok": 0, "hold": 3, "secret_blocked": 4}.get(res["status"], 1))
