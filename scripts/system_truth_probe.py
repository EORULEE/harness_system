#!/usr/bin/env python3
"""Evidence Index v1 — probe (fast path + 신선도 게이트).
index는 pointer/cache. 답하기 전 hash 신선도 검사 → STALE/must_read면 실제 파일 read 지시.
사용:
  python3 scripts/system_truth_probe.py --list            # 도메인 목록
  python3 scripts/system_truth_probe.py <domain>          # 도메인 항목 + 신선도 + read 지시
  python3 scripts/system_truth_probe.py --stale           # 전 파일 신선도 감사
"""
import os, sys, json, hashlib, shutil, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JPATH = os.path.join(ROOT, ".claude", "runtime", "system_truth_index.json")  # 기본; --index로 override
AGBIN = shutil.which("ast-grep") or os.path.expanduser("~/.npm-global/bin/ast-grep")
SGCONF = os.path.join(ROOT, ".claude", "skills", "_evidence-core", "astgrep", "sgconfig.yml")

def astgrep_anchors(paths):
    """must_read 코드 도메인의 구조 anchor(실호출/정의만, 주석·문자열 제외) 자동 추출.
    ast-grep 미설치/실패 시 None(graceful — rg+read로 진행). 필수 의존 아님."""
    if not (AGBIN and os.path.exists(AGBIN) and os.path.exists(SGCONF)):
        return None
    cps = [p for p in paths if p and os.path.isfile(p)
           and p.rsplit(".", 1)[-1] in ("py", "mjs", "js", "ts", "cjs")]
    if not cps:
        return []
    try:
        r = subprocess.run([AGBIN, "scan", "-c", SGCONF, "--json"] + cps,
                           capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout or "[]")
    except Exception:
        return None

def show_astgrep(items):
    paths = []
    for it in items:
        fp = it.get("path") or it.get("file")
        if fp: paths.append(resolve(fp))
    res = astgrep_anchors(paths)
    if res is None:
        print("  🔬 ast-grep: 미설치/불가 → rg + 파일 Read로 진행(필수 아님)"); return
    if not res:
        print("  🔬 ast-grep: 해당 도메인에 코드(.py/.mjs) 없음 → 파일 Read"); return
    byrule = {}
    for m in res: byrule.setdefault(m.get("ruleId"), []).append(m)
    print("  🔬 ast-grep 구조 anchor (주석/문자열 제외 — 실 호출/정의만):")
    for rid, ms in byrule.items():
        if len(ms) > 8:
            print(f"     {rid}: {len(ms)}건(다수) — `ast-grep -p '<패턴>' -l <lang> <file>`로 좁히기")
        else:
            for m in ms[:8]:
                ln = m.get("range", {}).get("start", {}).get("line", 0) + 1
                f = m.get("file", "")
                rel = os.path.relpath(f, ROOT) if f.startswith(ROOT) else f
                print(f"     {rid}  {rel}:{ln}  {(m.get('text') or '')[:46]}")

def resolve(p):
    if p.startswith("~"): return os.path.expanduser(p)
    if os.path.isabs(p): return p
    return os.path.join(ROOT, p)

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""): h.update(c)
    return h.hexdigest()

INDEXER = os.path.join(ROOT, "scripts", "system_truth_indexer.py")

def ensure_fresh():
    """조회 전 indexer --if-stale 자동 호출. 실패 시 **경고 표시**(codex-MAJOR4: 무음 실패 금지 —
    구 index를 fresh인 양 제시하면 anti-hallucination 취지 훼손). 항목별 sha256(fresh())이 안전망."""
    try:
        r = subprocess.run([sys.executable, INDEXER, "--if-stale"],
                           capture_output=True, timeout=30, cwd=ROOT, text=True)
        if r.returncode != 0:
            print(f"⚠️ index 자동갱신 실패(rc={r.returncode}) — index가 stale일 수 있음. "
                  "항목별 sha256 검사로 진행하되 index_ok 답도 신중히(의심 시 파일 Read).")
            return False
        return True
    except Exception as e:
        print(f"⚠️ index 자동갱신 예외({type(e).__name__}) — index stale 가능. 항목별 sha256로 진행.")
        return False

def load(path=None):
    p = path or JPATH
    if not os.path.isfile(p):
        print("⚠️ index 없음 — 먼저 `python3 scripts/system_truth_indexer.py` 실행"); sys.exit(2)
    return json.load(open(p, encoding="utf-8"))

def fresh(path, recorded_sha):
    rp = resolve(path)
    if not os.path.exists(rp): return "MISSING"
    try:
        return "fresh" if sha256_file(rp) == recorded_sha else "STALE"
    except Exception:
        return "ERR"

def cmd_list(idx):
    print(f"index: {idx['generated_at']} · {idx['domain_count']} domains")
    for n, d in idx["domains"].items():
        print(f"  {n:28s} risk={d['risk']:14s} collector={d['collector']}")

def cmd_stale(idx):
    fh = idx.get("files_hash", {})
    stale = []
    for p, v in fh.items():
        st = fresh(p, v.get("sha256"))
        if st != "fresh": stale.append((p, st))
    if not stale:
        print(f"✅ 전 {len(fh)} 파일 fresh (index 신선)")
    else:
        print(f"⚠️ STALE/MISSING {len(stale)}/{len(fh)} — 해당 파일은 index 신뢰 말고 read:")
        for p, st in stale: print(f"  {st}: {p}")
    return 1 if stale else 0

def cmd_domain(idx, name):
    d = idx["domains"].get(name)
    if not d:
        print(f"도메인 '{name}' 없음. --list 참고."); sys.exit(2)
    risk = d["risk"]
    print(f"# {name}  (risk={risk})")
    print(f"  답 가능: {', '.join(d.get('answers', [])) or '-'}")
    items = d["items"]
    # 신선도 검사 (item에 path+sha256 있으면)
    def chk(it):
        p = it.get("path") or it.get("file")
        s = it.get("sha256")
        return fresh(p, s) if (p and s) else "n/a"
    if isinstance(items, dict): items = [items]
    any_stale = False
    for it in items:
        st = chk(it)
        if st in ("STALE", "MISSING"): any_stale = True
        label = it.get("name") or it.get("rule") or it.get("path") or it.get("file") or it.get("pattern") or str(it)[:40]
        extra = ""
        if "dmi" in it: extra = f"dmi={it['dmi']} tools={it.get('allowed_tools','')[:30]}"
        elif "action" in it: extra = f"event={it.get('event')} action={it['action']} enabled={it.get('enabled')}"
        elif "anchor_count" in it: extra = f"anchors={it['anchor_count']} (위치만 — 답은 그 line read)"
        elif "exists" in it: extra = f"exists={it['exists']}"
        elif "override_count" in it: extra = f"overrides={it['override_count']} model={it.get('model')}"
        print(f"  [{st}] {label}  {extra}")
    print("-" * 40)
    if risk == "must_read":
        show_astgrep(items)   # 자동 ast-grep 구조 anchor (graceful)
        print("➡️ risk=must_read: 위 anchor는 **위치만**. 정확값/로직은 반드시 해당 파일을 Read.")
    elif any_stale:
        print("➡️ STALE 항목 존재: 그 파일은 index 신뢰 말고 Read 후 답.")
    elif risk == "presence_only":
        print("➡️ secret/env: 존재 여부만. 내용은 읽지 않음.")
    else:
        print("➡️ fresh + index_ok: 존재/메타 질문은 index로 답 가능('index 기준' 명시). 내용/동작 질문은 Read.")
    return 0

def main():
    args = sys.argv[1:]
    idxpath = None
    if "--index" in args:
        i = args.index("--index"); idxpath = args[i + 1]; del args[i:i + 2]
    no_refresh = "--no-refresh" in args
    if no_refresh: args.remove("--no-refresh")
    if not args:
        print(__doc__); return 2
    if not idxpath and not no_refresh:
        ensure_fresh()   # 조회 전 자동 갱신(--if-stale, hook/settings 무수정)
    idx = load(idxpath)
    a = args[0]
    if a == "--list": cmd_list(idx); return 0
    if a == "--stale": return cmd_stale(idx)
    return cmd_domain(idx, a)

if __name__ == "__main__":
    sys.exit(main())
