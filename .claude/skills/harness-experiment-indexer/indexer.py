#!/usr/bin/env python3
"""harness-experiment-indexer — Experiments/runs reconcile (결정적·읽기 중심).
runs/*/ 스캔 → EXP_INDEX.csv 정합성 점검 + 누락/고아 리포트 + (옵션) 누락행 stub 추가.
pyyaml 불필요(dirname=exp_id, presence 검사, metrics.json 읽기).

Usage:
  indexer.py <Experiments_dir> [--check]          # 정합성 리포트(쓰기 0)
  indexer.py <Experiments_dir> --append-missing   # EXP_INDEX.csv에 누락 run stub 행 추가만(기존행 불변)
수치 변경·삭제 없음. --append-missing도 기존 행은 건드리지 않고 append만.
"""
import os, sys, csv, json

HDR = ["exp_id","project","machine","title","status","created","git_commit","dataset","model","seed",
       "primary_metric","primary_value","in_sample","checkpoint_sha","tensorboard","card","archived_nas"]


def runs_on_disk(exp_dir):
    rd = os.path.join(exp_dir, "runs")
    if not os.path.isdir(rd): return []
    out = []
    for d in sorted(os.listdir(rd)):
        p = os.path.join(rd, d)
        if not os.path.isdir(p) or d.startswith("."): continue
        out.append({
            "exp_id": d,
            "has_yaml": os.path.exists(os.path.join(p, "experiment.yaml")),
            "has_card": os.path.exists(os.path.join(p, "review", "experiment_card.md")),
            "has_metrics": os.path.exists(os.path.join(p, "metrics", "metrics.json")) or os.path.exists(os.path.join(p, "metrics", "metrics.csv")),
        })
    return out


def index_ids(exp_dir):
    f = os.path.join(exp_dir, "EXP_INDEX.csv")
    ids = set()
    if os.path.exists(f):
        for row in csv.reader(open(f, encoding="utf-8")):
            if row and not row[0].startswith("#") and row[0] != "exp_id":
                ids.add(row[0])
    return ids


def main():
    a = sys.argv[1:]
    if not a: print("usage: indexer.py <Experiments_dir> [--check|--append-missing]"); return 2
    exp_dir = a[0]
    runs = runs_on_disk(exp_dir)
    idx = index_ids(exp_dir)
    run_ids = {r["exp_id"] for r in runs}
    missing = [r for r in runs if r["exp_id"] not in idx]        # 디스크엔 있는데 INDEX 없음
    stale = sorted(idx - run_ids)                                 # INDEX엔 있는데 디스크 없음
    incomplete = [r["exp_id"] for r in runs if not (r["has_yaml"] and r["has_metrics"])]
    print("# Experiment Index Reconcile — %s" % exp_dir)
    print("- runs(디스크): %d · EXP_INDEX 행: %d" % (len(runs), len(idx)))
    print("- INDEX 누락(disk only): %s" % (", ".join(r["exp_id"] for r in missing) or "없음"))
    print("- stale(index only, 디스크 없음): %s" % (", ".join(stale) or "없음"))
    print("- 불완전 run(yaml/metrics 결손): %s" % (", ".join(incomplete) or "없음"))
    if "--append-missing" in a and missing:
        f = os.path.join(exp_dir, "EXP_INDEX.csv")
        new = not os.path.exists(f)
        with open(f, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new: w.writerow(HDR)
            for r in missing:
                row = {"exp_id": r["exp_id"], "card": "runs/%s/review/experiment_card.md" % r["exp_id"],
                       "status": "needs_fill"}
                w.writerow([row.get(h, "") for h in HDR])
        print("- append-missing: %d 행 stub 추가(기존행 불변, 값=needs_fill)" % len(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
