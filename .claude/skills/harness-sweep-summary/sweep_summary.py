#!/usr/bin/env python3
"""harness-sweep-summary — sweep child runs → leaderboard + summary (결정적).
각 run/metrics.json의 primary(best/last) 읽어 정렬 + k-seed 평균/표준편차. 수치 추출만(변경 0).
유의성·다중검정은 **미산정 표기**(날조 금지) — 데이터 충분 시 사람/별도 통계.

Usage:
  sweep_summary.py <runs_parent_dir> --metric val_IoU_water [--goal max|min] [--use last|best]
metrics.json 스키마: {"primary":{"metric","best","last"}} 또는 {"validation":{<metric>:{best,last}}}.
"""
import os, sys, json, csv, statistics


def load_primary(run_dir, metric, use):
    f = os.path.join(run_dir, "metrics", "metrics.json")
    if not os.path.exists(f): return None
    try: d = json.load(open(f, encoding="utf-8"))
    except Exception: return None
    # primary 블록 우선, 없으면 validation[metric]
    blk = None
    if isinstance(d.get("primary"), dict) and d["primary"].get("metric") == metric:
        blk = d["primary"]
    elif isinstance(d.get("validation"), dict) and metric in d["validation"]:
        blk = d["validation"][metric]
    if not blk: return None
    return blk.get(use)


def seed_of(run_dir):
    # exp_id ...-s<seed> 또는 metrics.json seed
    name = os.path.basename(run_dir.rstrip("/"))
    if "-s" in name:
        tail = name.rsplit("-s", 1)[1]
        if tail.isdigit(): return tail
    return ""


def main():
    a = sys.argv[1:]
    if "--metric" not in a: print("usage: sweep_summary.py <dir> --metric M [--goal max|min] [--use last|best]"); return 2
    parent = a[0]; metric = a[a.index("--metric")+1]
    goal = a[a.index("--goal")+1] if "--goal" in a else "max"
    use = a[a.index("--use")+1] if "--use" in a else "best"
    rows = []
    for d in sorted(os.listdir(parent)):
        rd = os.path.join(parent, d)
        if not os.path.isdir(rd) or d.startswith("."): continue
        v = load_primary(rd, metric, use)
        if v is not None: rows.append({"exp_id": d, "value": v, "seed": seed_of(rd)})
    rows.sort(key=lambda r: r["value"], reverse=(goal == "max"))
    # k-seed 집계(같은 base, seed만 다른 것)
    groups = {}
    for r in rows:
        base = r["exp_id"].rsplit("-s", 1)[0] if r["seed"] else r["exp_id"]
        groups.setdefault(base, []).append(r["value"])
    out = os.path.join(parent, "leaderboard.csv")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank","exp_id","metric","value","seed","k_seed_mean","k_seed_std","significant"])
        for i, r in enumerate(rows, 1):
            base = r["exp_id"].rsplit("-s",1)[0] if r["seed"] else r["exp_id"]
            g = groups[base]
            mean = round(statistics.mean(g), 6) if g else ""
            std = round(statistics.pstdev(g), 6) if len(g) > 1 else ""
            w.writerow([i, r["exp_id"], metric, r["value"], r["seed"], mean, std, "not_computed"])
    print("# Sweep Summary — %s" % parent)
    print("- metric=%s(%s, %s) · runs=%d · k-seed 그룹=%d" % (metric, goal, use, len(rows), len(groups)))
    print("- leaderboard: %s" % out)
    print("- ⚠️ significant=not_computed (유의성·다중검정 미산정 — 날조 금지)")
    for i, r in enumerate(rows[:5], 1):
        print("  %d. %s = %.5f (seed %s)" % (i, r["exp_id"], r["value"], r["seed"] or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
