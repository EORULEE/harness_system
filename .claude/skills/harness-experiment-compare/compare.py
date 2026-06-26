#!/usr/bin/env python3
"""harness-experiment-compare — 여러 run의 metrics.json 횡단 비교표 (결정적·읽기전용).
모델/seed별 지표 비교. 수치 추출만(변경 0). "우위" 단정·유의성 날조 금지(차이만 표기).

Usage:
  compare.py <run_dir1> <run_dir2> ... [--metrics m1,m2]   # 지정 run 비교
  compare.py --parent <dir> [--metrics m1,m2]              # dir 내 모든 run
metrics.json: {"validation":{<m>:{best,last}}, "primary":{...}}.
"""
import os, sys, json


def metrics_of(run_dir):
    f = os.path.join(run_dir, "metrics", "metrics.json")
    if not os.path.exists(f): return {}
    try: d = json.load(open(f, encoding="utf-8"))
    except Exception: return {}
    flat = {}
    for k, v in (d.get("validation") or {}).items():
        if isinstance(v, dict): flat[k] = v.get("best", v.get("last"))
    p = d.get("primary")
    if isinstance(p, dict) and p.get("metric"): flat[p["metric"]] = p.get("best", p.get("last"))
    return flat


def main():
    a = sys.argv[1:]
    if not a: print("usage: compare.py <run_dir...> | --parent <dir> [--metrics m1,m2]"); return 2
    want = None
    if "--metrics" in a:
        want = a[a.index("--metrics")+1].split(","); a = a[:a.index("--metrics")]
    if a[0] == "--parent":
        parent = a[1]; runs = [os.path.join(parent, d) for d in sorted(os.listdir(parent))
                               if os.path.isdir(os.path.join(parent, d)) and not d.startswith(".")]
    else:
        runs = a
    data = {os.path.basename(r.rstrip("/")): metrics_of(r) for r in runs}
    keys = want or sorted({k for m in data.values() for k in m})
    print("# Experiment Compare (%d runs)" % len(data))
    print("| run | " + " | ".join(keys) + " |")
    print("|---|" + "---|"*len(keys))
    for name, m in data.items():
        cells = []
        for k in keys:
            v = m.get(k)
            cells.append("%.5f" % v if isinstance(v, (int, float)) else "-")
        print("| %s | %s |" % (name, " | ".join(cells)))
    print("\n⚠️ 차이 표기만 — 통계근거 없는 '우위' 단정·유의성 날조 금지(k-seed/검정은 sweep-summary).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
