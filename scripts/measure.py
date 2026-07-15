#!/usr/bin/env python3
"""measure.py — typed measurement helper 3종 (v1.1 ADOPT #2, 설계=implementation_design_v1.1.md).

서브커맨드: mount | identity | import  (attempt/hash 는 REJECT — 자기인증 제조기 위험)

원칙(ChatGPT 리뷰 결함 #7·#8 + codex 교차 확정):
- argv 실행(shell=False), 원격 명령은 shlex.quote 고정 템플릿(사용자 문자열 보간 금지).
- probe 별 **개별 exit code** 기록 — 복합 명령의 마지막-명령-덮어쓰기 버그 원천 제거.
- LC_ALL=C 고정, probe 별 timeout, bounded raw output 저장(hash 만으론 감사자가 parser 검증 불가).
- 실패는 실패로 기록(ok=false receipt). 허위 성공 receipt 생성 금지.
- identity 는 관측 시점에 원격이 자기 identity 를 반환(hostname/boot_id) — 소급 alias 매칭 금지.
  hostkey_fp 는 known_hosts 조회(secondary attribute — ssh-keyscan 은 미인증이라 미사용).
- 고정 계약 1개: statfs.magic_family ⊬ mount.fstype (M1). 이 helper 는 kernel mount table 만 사용.

사용:
  measure.py mount    --path /data [--host server-a]
  measure.py identity [--host server-a]
  measure.py import   --module torch [--host server-a] [--python /usr/bin/python3]
출력: receipt JSON(stdout) + .claude/runtime/vgate/receipts.jsonl append.
"""
from __future__ import annotations
import argparse, json, re, shlex, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vgate_common import RECEIPTS, bounded, flock_append, gate_fingerprint, make_id, now

PROBE_TIMEOUT = 20
_MODULE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _run(argv: list[str], timeout: int = PROBE_TIMEOUT) -> dict:
    """단일 probe 실행 — 개별 rc/out/err/elapsed. 예외도 구조화(rc=-1)."""
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/local/bin"})
        return {"argv0": argv[0], "rc": p.returncode, "out": bounded(p.stdout.strip()),
                "err": bounded(p.stderr.strip(), 500),
                "elapsed_ms": int((time.monotonic() - t0) * 1000)}
    except subprocess.TimeoutExpired:
        return {"argv0": argv[0], "rc": -2, "timeout": True,
                "elapsed_ms": int((time.monotonic() - t0) * 1000)}
    except Exception as e:
        return {"argv0": argv[0], "rc": -1, "error": type(e).__name__,
                "elapsed_ms": int((time.monotonic() - t0) * 1000)}


def _remote_argv(host: str, remote_cmd: list[str]) -> list[str]:
    """원격 실행 argv. remote_cmd 는 이미 조각별로 quote 됨(문자열 보간 금지).
    ⚠️ '--' 는 destination **앞**(옵션 종결자) — 뒤에 두면 원격 명령이 '--'로 시작
    (codex 리뷰 M13; 원격 실증은 fleet smoke 대기 = Unverified)."""
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "--", host,
            shlex.join(remote_cmd)]


def _probe(host: str | None, remote_cmd: list[str]) -> dict:
    if host:
        return _run(_remote_argv(host, remote_cmd))
    return _run(remote_cmd)


def _identity_probes(host: str | None) -> dict:
    """관측 시점 원격 self-identity. 각 probe 개별 rc."""
    probes = {
        "hostname": _probe(host, ["hostname"]),
        "boot_id": _probe(host, ["cat", "/proc/sys/kernel/random/boot_id"]),
        "machine_id": _probe(host, ["cat", "/etc/machine-id"]),  # 기회수집(키결속 없음)
    }
    ident = {"requested_alias": host or "local"}
    if probes["hostname"]["rc"] == 0:
        ident["remote_hostname"] = probes["hostname"]["out"]
    if probes["boot_id"]["rc"] == 0:
        ident["boot_id"] = probes["boot_id"]["out"]
    if probes["machine_id"]["rc"] == 0:
        ident["machine_id"] = probes["machine_id"]["out"]
    if host:
        g = _run(["ssh", "-G", host])
        if g["rc"] == 0:
            kv = dict(line.split(None, 1) for line in g["out"].splitlines()
                      if " " in line and line.split()[0] in ("hostname", "port", "user"))
            ident["effective_host"] = kv.get("hostname", "")
            ident["effective_port"] = kv.get("port", "")
            # hostkey fp = known_hosts 조회(secondary — ssh-keyscan 미사용)
            f = _run(["ssh-keygen", "-F", ident["effective_host"], "-l"])
            if f["rc"] == 0 and f["out"]:
                m = re.search(r"(SHA256:[A-Za-z0-9+/=]+)", f["out"])
                if m:
                    ident["ssh_hostkey_fp"] = m.group(1)
        probes["ssh_G"] = {"rc": g["rc"]}
    return {"identity": ident, "probes": probes}


def _emit(observable: str, subject: dict, value, ok: bool, probes: dict, t0: float) -> int:
    rec = {"ts": now(), "kind": "measure", "observable": observable, "ok": bool(ok),
           "subject": subject, "value": value, "probes": probes,
           "elapsed_ms": int((time.monotonic() - t0) * 1000), "gate_fp": gate_fingerprint()}
    rec["receipt_id"] = make_id("obs", {k: rec[k] for k in ("ts", "observable", "subject", "value")})
    flock_append(RECEIPTS, rec)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_mount(args) -> int:
    t0 = time.monotonic()
    idn = _identity_probes(args.host)
    # kernel mount table 고정(findmnt -J 기본 = kernel). --fstab 미사용.
    fm = _probe(args.host, ["findmnt", "-J", "--target", args.path])
    rp = _probe(args.host, ["realpath", args.path])
    probes = {**idn["probes"], "findmnt": fm, "realpath": rp}
    value, ok = None, False
    if fm["rc"] == 0:
        try:
            fs = json.loads(fm["out"])["filesystems"][0]
            value = {"fstype": fs.get("fstype"), "source": fs.get("source"),
                     "target": fs.get("target"),
                     "resolved_path": rp["out"] if rp["rc"] == 0 else None}
            ok = bool(value["fstype"])
        except Exception:
            probes["findmnt"]["parse_error"] = True
    subject = {**idn["identity"], "path": args.path}
    return _emit("linux.mount.fstype", subject, value, ok, probes, t0)


def cmd_identity(args) -> int:
    t0 = time.monotonic()
    idn = _identity_probes(args.host)
    ok = idn["probes"]["hostname"]["rc"] == 0
    return _emit("host.identity", idn["identity"],
                 {k: v for k, v in idn["identity"].items() if k != "requested_alias"},
                 ok, idn["probes"], t0)


def cmd_import(args) -> int:
    t0 = time.monotonic()
    if not _MODULE_RE.match(args.module):
        print(json.dumps({"error": "invalid module name"})); return 2
    idn = _identity_probes(args.host)
    py = args.python or "python3"
    code = ("import time,importlib;t=time.monotonic();"
            f"importlib.import_module({args.module!r});"
            "print(f'{time.monotonic()-t:.3f}')")
    im = _probe(args.host, [py, "-c", code])
    probes = {**idn["probes"], "import": im, "interpreter": _probe(args.host, [py, "--version"])}
    value, ok = None, False
    if im["rc"] == 0:
        try:
            value = {"import_seconds": float(im["out"].splitlines()[-1]), "module": args.module,
                     "python": py}
            ok = True
        except Exception:
            probes["import"]["parse_error"] = True
    subject = {**idn["identity"], "module": args.module, "python": py}
    return _emit("python.module.import_latency", subject, value, ok, probes, t0)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mount"); m.add_argument("--path", required=True); m.add_argument("--host")
    i = sub.add_parser("identity"); i.add_argument("--host")
    p = sub.add_parser("import"); p.add_argument("--module", required=True)
    p.add_argument("--host"); p.add_argument("--python")
    args = ap.parse_args()
    if args.host and not _HOST_RE.match(args.host):
        print(json.dumps({"error": "invalid host"})); return 2
    return {"mount": cmd_mount, "identity": cmd_identity, "import": cmd_import}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
