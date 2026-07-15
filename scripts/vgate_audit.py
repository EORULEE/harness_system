#!/usr/bin/env python3
"""vgate_audit.py — 최소 지속가능 감사 루프 (v1.1 ADOPT #6).

스트림(codex 축소안 — 3-stream 자동화는 DEFER):
  AB_would_block   : would_block 전건 감사(gate 폐기 방지 — false-block 정밀도의 유일 소스)
  C_random_passed  : 통과 턴 무작위 표본(miss 를 볼 유일한 stream)

규칙(ChatGPT P2 수정 반영):
- 선정된 item 은 **전부 판정하거나 UNRESOLVED 로 명시 보고**(cherry-picking 금지).
- reviewer 패키지에는 detector 결과가 없음(orchestrator 가 블라인딩 상태로 생성).
- label: CONFIRMED_MATCH | WRONG_AT_CLAIM_TIME | DRIFT_POSSIBLE | NOT_COMPARABLE | UNRESOLVED
  (재측정 불일치 ≠ 원주장 오류 — state drift 분리)
- summary 는 분모 포함(무의미한 '3 misses' 금지) + gate 버전별 구분(freeze 식별).

사용:
  vgate_audit.py status                 # 큐/판정 현황(분모 포함)
  vgate_audit.py list                   # 미판정 item
  vgate_audit.py show <package_id>      # 판정용 패키지 출력(블라인딩됨)
  vgate_audit.py adjudicate <package_id> --label WRONG_AT_CLAIM_TIME [--notes ..] [--minutes 5]
  vgate_audit.py summary                # 주간 보고 1줄 표
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vgate_common import (AUDIT_LABELS, AUDIT_QUEUE, FINDINGS, VGATE_DIR, flock_append,
                          gate_fingerprint, load_jsonl, now)

LABELS = {"CONFIRMED_MATCH", "WRONG_AT_CLAIM_TIME", "DRIFT_POSSIBLE",
          "NOT_COMPARABLE", "UNRESOLVED", "FALSE_BLOCK"}
DONE_DIR = AUDIT_QUEUE / "done"
QUEUE_INDEX = VGATE_DIR / "queue-index.jsonl"   # M8: stream 사이드카(리뷰어 비노출)


def _stream_of(package_id: str) -> str:
    for r in load_jsonl(QUEUE_INDEX):
        if r.get("package_id") == package_id:
            return r.get("stream", "?")
    return "?"


def _pending() -> list[Path]:
    if not AUDIT_QUEUE.exists():
        return []
    return sorted(p for p in AUDIT_QUEUE.glob("*.json") if p.is_file())


def cmd_status(_args) -> int:
    pend = _pending()
    labels = load_jsonl(AUDIT_LABELS)
    by_label: dict[str, int] = {}
    for r in labels:
        by_label[r.get("label", "?")] = by_label.get(r.get("label", "?"), 0) + 1
    finds = load_jsonl(FINDINGS)
    turns = [f for f in finds if "findings" in f]
    wb = [f for f in turns if f.get("would_block_count", 0) > 0]
    print(json.dumps({
        "gate_fp": gate_fingerprint(),
        "total_evaluated_turns": len(turns),                    # 분모
        "would_block_turns": len(wb),
        "baseline_sampled": sum(1 for f in turns if f.get("sampled_baseline")),
        "cap_overridden": sum(1 for f in finds if f.get("metric") == "stop_gate_overridden_after_cap"),
        "audit_pending": len(pend),
        "audit_adjudicated": by_label,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_list(_args) -> int:
    # M8: stream 미표시(리뷰어 블라인딩 — 판정 후 adjudicate 가 index 에서 결속).
    for p in _pending():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            print(f"{p.stem}  ts={d.get('ts')}")
        except Exception:
            print(f"{p.stem}  (unreadable)")
    return 0


def cmd_show(args) -> int:
    p = AUDIT_QUEUE / f"{args.package_id}.json"
    if not p.exists():
        print(json.dumps({"error": "package 미존재", "id": args.package_id})); return 1
    print(p.read_text(encoding="utf-8"))
    return 0


def cmd_adjudicate(args) -> int:
    if args.label not in LABELS:
        print(json.dumps({"error": f"label 은 {sorted(LABELS)} 중 하나"})); return 1
    p = AUDIT_QUEUE / f"{args.package_id}.json"
    if not p.exists():
        print(json.dumps({"error": "package 미존재(이미 판정?)", "id": args.package_id})); return 1
    stream = _stream_of(args.package_id)  # M8: 판정 후에만 index 에서 stream 결속
    rec = {"ts": now(), "package_id": args.package_id, "stream": stream,
           "label": args.label, "notes": (args.notes or "")[:300],
           "operator_minutes": args.minutes, "gate_fp": gate_fingerprint()}
    flock_append(AUDIT_LABELS, rec)
    # 정정 프로토콜(2026-07-15 사용자 지적: 틀린 '불가'는 사용자 믿음을 오염 — 능동 정정 의무):
    # 오판 확정 시 corrections 큐 적재. user_notified 는 실제 정정 보고 후 별도로 갱신.
    if args.label == "WRONG_AT_CLAIM_TIME":
        flock_append(VGATE_DIR / "corrections.jsonl",
                     {"ts": now(), "package_id": args.package_id,
                      "notes": rec["notes"], "user_notified": False})
        print("⚠️ 사용자 정정 보고 필요 — 이 오판으로 사용자가 틀린 믿음을 가졌을 수 있음. "
              "다음 응답에서 '정정: …' 명시 후 corrections.jsonl user_notified 갱신.")
    try:
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        p.rename(DONE_DIR / p.name)
    except Exception:
        pass
    print(json.dumps({"adjudicated": True, **rec}, ensure_ascii=False, indent=2))
    return 0


def cmd_summary(_args) -> int:
    """주간 1줄 표 — 분모·unknown 필수(ChatGPT P2-6)."""
    labels = load_jsonl(AUDIT_LABELS)
    pend = _pending()
    ab = [r for r in labels if r.get("stream") == "AB_would_block"]
    c = [r for r in labels if r.get("stream") == "C_random_passed"]
    false_blocks = sum(1 for r in ab if r.get("label") == "FALSE_BLOCK")
    misses = sum(1 for r in c if r.get("label") == "WRONG_AT_CLAIM_TIME")
    unresolved = sum(1 for r in labels if r.get("label") == "UNRESOLVED")
    minutes = sum(r.get("operator_minutes") or 0 for r in labels)
    pending_corr = sum(1 for r in load_jsonl(VGATE_DIR / "corrections.jsonl")
                       if not r.get("user_notified"))
    if pending_corr:
        print(f"🔔 미보고 사용자 정정 {pending_corr}건 — corrections.jsonl 확인 후 정정 보고 필요")
    print(f"| gate_fp {gate_fingerprint()} | selected {len(labels)+len(pend)} "
          f"| adjudicated {len(labels)} | unresolved {unresolved} | pending {len(pend)} "
          f"| false_blocks {false_blocks}/{len(ab)} (would_block 판정분) "
          f"| confirmed_misses {misses}/{len(c)} (random 표본분) "
          f"| operator_min {minutes} |")
    if len(ab) < 20:
        ub = min(100.0, (3 / max(len(ab), 1)) * 100)
        print(f"⚠️ would_block 판정 표본 {len(ab)}건 — 0 false-block 이어도 FP 상한 "
              f"~{ub:.0f}% (95%). hard 승격 판단 불가 수준이면 표본 축적 계속.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status"); sub.add_parser("list"); sub.add_parser("summary")
    s = sub.add_parser("show"); s.add_argument("package_id")
    a = sub.add_parser("adjudicate"); a.add_argument("package_id")
    a.add_argument("--label", required=True); a.add_argument("--notes")
    a.add_argument("--minutes", type=int, default=0)
    args = ap.parse_args()
    return {"status": cmd_status, "list": cmd_list, "show": cmd_show,
            "adjudicate": cmd_adjudicate, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
