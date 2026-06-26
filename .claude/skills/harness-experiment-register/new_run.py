#!/usr/bin/env python3
"""harness-experiment-register — run 폴더 scaffold (등록 골격만 생성).
Experiments/runs/<exp_id>/ 표준 골격(data/logs/metrics/review + stub experiment.yaml·README) 생성.
⚠️ metric은 **에이전트가 원본에서 추출해 채움**(source-specific, 날조 금지) — 이 스크립트는 골격만.
원본 미접촉. 기존 run 있으면 거부(덮어쓰기 금지).

Usage: new_run.py <Experiments_dir> <exp_id> [project] [machine]
"""
import os, sys


def main():
    a = sys.argv[1:]
    if len(a) < 2: print("usage: new_run.py <Experiments_dir> <exp_id> [project] [machine]"); return 2
    exp_dir, exp_id = a[0], a[1]
    project = a[2] if len(a) > 2 else ""
    machine = a[3] if len(a) > 3 else ""
    run = os.path.join(exp_dir, "runs", exp_id)
    if os.path.exists(run):
        print("ERROR: 이미 존재 — 덮어쓰기 금지: %s" % run); return 1
    for sub in ["data", "logs", "metrics", "review"]:
        os.makedirs(os.path.join(run, sub), exist_ok=True)
    yaml = (
        "exp_id: %s\nproject: %s\nmachine: %s\ntitle: \"\"\nstatus: needs_fill\n"
        "created: \"\"\ngit:\n  commit: unknown\ndata:\n  location: \"\"   # 원본(link, 무이동)\n"
        "  raw_links: data/raw_links.yaml\nconfig:\n  model: \"\"\n  seed: unknown\n"
        "metrics:\n  primary: \"\"\n  metrics_file: metrics/metrics.csv   # 원본 추출(변경 0)\n  source: \"\"\n"
        "integrity:\n  in_sample: unknown\n  significance: not_computed   # 날조 금지\n"
        "provenance:\n  registered_scaffold: true   # metric 미충전 — 에이전트가 원본서 추출\n"
    ) % (exp_id, project, machine)
    open(os.path.join(run, "experiment.yaml"), "w", encoding="utf-8").write(yaml)
    open(os.path.join(run, "README.md"), "w", encoding="utf-8").write(
        "# Run %s\n\n> 골격 생성. metric은 원본서 추출해 metrics/·experiment.yaml 채울 것(날조 금지). 원본 무이동.\n" % exp_id)
    print("scaffold 생성: %s (metric 미충전 — 에이전트 채움)" % run)
    print("다음: ① 원본 metric→metrics/metrics.csv·json(변경0) ② experiment.yaml 채움 ③ EXP_INDEX append(indexer) ④ card·wiki")
    return 0


if __name__ == "__main__":
    sys.exit(main())
