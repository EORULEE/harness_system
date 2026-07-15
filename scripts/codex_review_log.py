#!/usr/bin/env python3
"""codex_review_log.py — codex(교차모델) 검증 수행의 **구조화 감사 로그**.

배경: stop-guard 교차모델 게이트가 응답 자유텍스트("codex" 단어)만 보면 marker-stuffing 으로
      우회됨(codex 적대검토 FAIL 지적). → codex 를 실제 호출했다는 **구조화·타임스탬프 증거**를
      별도 파일에 남기고, 게이트는 그 파일의 최근 엔트리를 검사한다. 응답에 단어만 쓴다고 통과 안 됨.

사용:
  # codex 적대검토(codex exec CLI 직접) 실제 수행 직후 오케스트레이터가 호출:
  python3 codex_review_log.py record --target "<검토대상 요약>" --command "codex-exec-adversarial" --verdict "<PASS/CONDITIONAL/FAIL>"
  # 게이트/사용자가 최근 수행 확인:
  python3 codex_review_log.py recent [--window-sec 10800]   # 최근 3h 내 엔트리 있으면 exit 0, 없으면 exit 1

파일: .claude/runtime/codex-reviews.jsonl (append-only, 메타만 — 리뷰 본문 저장 안 함).
가용성 판정은 codex_probe.probe() 재사용(단일 출처).
"""
import argparse, hashlib, json, os, sys, time
from pathlib import Path

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))
try:
    from harness_common import CLAUDE_DIR  # type: ignore
except Exception:
    CLAUDE_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude"

LOG = Path(CLAUDE_DIR) / "runtime" / "codex-reviews.jsonl"


def _now():
    return time.time()


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_record(a) -> int:
    rec = {
        "ts": _now(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": (a.target or "")[:200],
        "command": (a.command or "")[:80],
        "verdict": (a.verdict or "")[:40],
        "turn": _read_turn(),
    }
    # r17 gate-integrity: 산출물 해시 바인딩(IMP-01). 본문은 여전히 미저장 — 해시·크기·경로만.
    #   위조 비용을 "한 줄 기록"에서 "실제 리뷰 파일 생성"으로 올린다(검증 = verify_entry_hash).
    if getattr(a, "review_file", None):
        try:
            rp = Path(a.review_file)
            rec["review_path"] = str(rp)[:300]
            rec["review_sha256"] = _sha256_file(rp)
            rec["review_bytes"] = rp.stat().st_size
        except Exception as e:
            # 파일 접근 실패 시에도 기록 자체는 남김(fail-open) — 단 해시 필드는 미기재(legacy 취급)
            sys.stderr.write(f"codex_review_log: review-file 해시 실패({e}) — 해시 필드 없이 기록\n")
    if getattr(a, "prompt_sha256", None):
        rec["prompt_sha256"] = (a.prompt_sha256 or "")[:64]
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"codex_review_log record 실패: {e}\n")
        return 0  # fail-open (기록 실패로 턴 막지 않음)
    sys.stdout.write("recorded\n")
    return 0


def _read_turn():
    try:
        p = Path(CLAUDE_DIR) / "runtime" / "_current_turn.txt"
        return p.read_text(encoding="utf-8").strip()[:80] if p.exists() else ""
    except Exception:
        return ""


def recent_entry(window_sec: int = 3 * 3600) -> dict | None:
    """최근 window_sec 내 codex 리뷰 엔트리(가장 최신) 반환, 없으면 None."""
    try:
        if not LOG.exists():
            return None
        lines = LOG.read_text(encoding="utf-8").splitlines()
        for ln in reversed(lines):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if _now() - float(r.get("ts", 0)) <= window_sec:
                return r
        return None
    except Exception:
        return None


def verify_entry_hash(entry: dict) -> dict:
    """r17: 엔트리의 review_sha256 를 실파일 재계산으로 검증.

    반환 status:
      verified      — 해시 일치(강한 증거)
      file_missing  — 엔트리에 해시 있으나 파일 부재 → advisory 강등 대상
      hash_mismatch — 파일 존재하나 해시 불일치 → advisory 강등 대상
      no_hash_fields— 구버전 엔트리(해시 필드 없음) → legacy 취급(기존 동작 유지)
    """
    if not entry or not entry.get("review_sha256"):
        return {"status": "no_hash_fields"}
    rp = Path(entry.get("review_path", ""))
    if not rp.is_file():
        return {"status": "file_missing", "path": str(rp)}
    try:
        actual = _sha256_file(rp)
    except Exception as e:
        return {"status": "file_missing", "path": str(rp), "error": str(e)}
    if actual != entry["review_sha256"]:
        return {"status": "hash_mismatch", "path": str(rp),
                "expected": entry["review_sha256"][:12], "actual": actual[:12]}
    return {"status": "verified", "path": str(rp)}


def cmd_verify_hash(a) -> int:
    r = recent_entry(a.window_sec)
    res = verify_entry_hash(r) if r else {"status": "no_entry"}
    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
    return 0 if res["status"] in ("verified", "no_hash_fields") else 1


def cmd_recent(a) -> int:
    r = recent_entry(a.window_sec)
    if r:
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
        return 0
    sys.stdout.write("none\n")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("record")
    r.add_argument("--target", default="")
    r.add_argument("--command", default="")
    r.add_argument("--verdict", default="")
    r.add_argument("--review-file", default="", help="r17: 리뷰 산출물 파일 — sha256/bytes 바인딩")
    r.add_argument("--prompt-sha256", default="", help="r17: 사용 프롬프트의 sha256(본문 미저장)")
    rc = sub.add_parser("recent")
    rc.add_argument("--window-sec", type=int, default=3 * 3600)
    vh = sub.add_parser("verify-hash")
    vh.add_argument("--window-sec", type=int, default=3 * 3600)
    a = ap.parse_args()
    if a.cmd == "record":
        return cmd_record(a)
    if a.cmd == "recent":
        return cmd_recent(a)
    if a.cmd == "verify-hash":
        return cmd_verify_hash(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
