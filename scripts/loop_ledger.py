#!/usr/bin/env python3
"""
loop_ledger.py — Loop Engineering Control Plane 결정적 원장(ledger) + verdict (r3 후보).

loop 1건의 상태를 디스크에 영속한다. **대화 컨텍스트를 loop 상태의 정본으로 쓰지 않는다** —
정본 = contract.yaml + events.jsonl + verdict.json.

상태 경로(프로젝트 루트 상대):
  contract : _claude/loops/<loop_id>/contract.yaml   (검증은 loop_contract_validator.py)
  ledger   : _claude/loops/<loop_id>/events.jsonl    (본 스크립트 — append-only)
  verdict  : _claude/loops/<loop_id>/verdict.json    (본 스크립트 finalize)
  artifact : _output/loops/<loop_id>/                (산출물 — 본 스크립트는 디렉토리만 보장)

사용법:
  python3 scripts/loop_ledger.py <loop_id> init      [--root .] [--data '{...}'] [--at YYYY-MM-DD]
  python3 scripts/loop_ledger.py <loop_id> append    --event <name> [--data '{...}'] [--at YYYY-MM-DD] [--root .]
  python3 scripts/loop_ledger.py <loop_id> finalize  --verdict <PASS|HOLD|CANCELLED|FAIL> [--reason <s>] [--at YYYY-MM-DD]
  python3 scripts/loop_ledger.py <loop_id> show      [--root .]

결정성: seq 는 기존 줄 수에서 증가, 시각은 --at(생략 시 오늘) — 같은 입력+같은 --at → 동일 바이트.
exit: 0=성공, 1=사용오류, 3=HOLD(finalize --verdict HOLD)
secret: --data 는 기록 전 secret_masking 으로 마스킹(있으면). 토큰/키 기록 안 함.
"""
import argparse, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOOP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _mask(obj):
    """dict/문자열 값을 secret_masking 으로 마스킹(있으면). 실패해도 원본 통과."""
    try:
        sys.path.insert(0, HERE)
        import secret_masking as sm  # type: ignore
    except Exception:
        return obj
    def walk(x):
        if isinstance(x, str):
            try:
                return sm.mask_secrets(x)
            except Exception:
                return x
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(obj)


def _today():
    return datetime.date.today().isoformat()


def _loop_dir(root, loop_id):
    return os.path.join(root, "_claude", "loops", loop_id)


def _artifact_dir(root, loop_id):
    return os.path.join(root, "_output", "loops", loop_id)


def _ledger_path(root, loop_id):
    return os.path.join(_loop_dir(root, loop_id), "events.jsonl")


def _next_seq(ledger_path):
    if not os.path.isfile(ledger_path):
        return 1
    n = 0
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n + 1


def _append_event(root, loop_id, event, data, at):
    # 설계 전제 = 단일 writer(주 orchestrator). 우발적 동시쓰기에 대비해 best-effort flock 으로
    # seq 산정+append 를 직렬화한다(POSIX). 비POSIX/미지원 환경은 단일 writer 전제로 진행.
    os.makedirs(_loop_dir(root, loop_id), exist_ok=True)
    os.makedirs(_artifact_dir(root, loop_id), exist_ok=True)
    lp = _ledger_path(root, loop_id)
    lock = open(lp + ".lock", "w")
    try:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        except Exception:
            pass
        seq = _next_seq(lp)
        rec = {"seq": seq, "loop_id": loop_id, "event": event, "at": at, "data": _mask(data or {})}
        # 결정적 직렬화(sort_keys=True, compact, ensure_ascii=False)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with open(lp, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    finally:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN)
        except Exception:
            pass
        lock.close()
    return rec


def _parse_data(s):
    if not s:
        return {}
    try:
        d = json.loads(s)
    except Exception:
        sys.stderr.write("사용오류: --data 는 JSON 이어야 함\n")
        sys.exit(1)
    if not isinstance(d, dict):
        sys.stderr.write("사용오류: --data 는 JSON object 여야 함\n")
        sys.exit(1)
    return d


def main():
    ap = argparse.ArgumentParser(description="Loop ledger (deterministic, append-only)")
    ap.add_argument("loop_id")
    ap.add_argument("cmd", choices=["init", "append", "finalize", "show"])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--event", default=None)
    ap.add_argument("--data", default=None)
    ap.add_argument("--verdict", default=None, choices=[None, "PASS", "HOLD", "CANCELLED", "FAIL"])
    ap.add_argument("--reason", default="")
    ap.add_argument("--at", default=None, help="YYYY-MM-DD (생략 시 오늘; 재현 테스트용 고정)")
    args = ap.parse_args()

    if not LOOP_ID_RE.match(args.loop_id):
        sys.stderr.write(f"사용오류: loop_id 형식 위반(경로 안전 문자만): {args.loop_id!r}\n")
        return 1
    root = args.root
    at = args.at or _today()

    if args.cmd == "init":
        rec = _append_event(root, args.loop_id, "start", _parse_data(args.data), at)
        print(json.dumps(rec, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd == "append":
        if not args.event:
            sys.stderr.write("사용오류: append --event <name> 필요\n")
            return 1
        rec = _append_event(root, args.loop_id, args.event, _parse_data(args.data), at)
        print(json.dumps(rec, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd == "finalize":
        if not args.verdict:
            sys.stderr.write("사용오류: finalize --verdict <PASS|HOLD|CANCELLED|FAIL> 필요\n")
            return 1
        data = _parse_data(args.data)
        data.update({"verdict": args.verdict, "reason": args.reason})
        _append_event(root, args.loop_id, "finalize", data, at)
        verdict = {
            "loop_id": args.loop_id,
            "status": args.verdict,
            "reason": args.reason,
            "at": at,
        }
        vpath = os.path.join(_loop_dir(root, args.loop_id), "verdict.json")
        # 원자적 쓰기(tmp → os.replace): 중단/동시 finalize 시 부분 파일 방지
        vtmp = vpath + ".tmp"
        with open(vtmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(_mask(verdict), ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        os.replace(vtmp, vpath)
        print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))
        return 3 if args.verdict == "HOLD" else 0

    if args.cmd == "show":
        lp = _ledger_path(root, args.loop_id)
        if not os.path.isfile(lp):
            sys.stderr.write(f"원장 없음: {lp}\n")
            return 1
        with open(lp, "r", encoding="utf-8") as f:
            sys.stdout.write(f.read())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
