#!/usr/bin/env python3
"""Evidence Index v1 — system-truth indexer.
source-map.yaml를 구동해 하네스 핵심 상태를 증분 index한다.
- index는 pointer/cache(SoT 아님). secret 원문 미저장. env/secret=presence만.
- 산출: .claude/runtime/system_truth_index.{json,sha256,log}
실행: python3 scripts/system_truth_indexer.py
"""
import os, sys, re, json, hashlib, glob, datetime
import yaml

SECRET_RE = re.compile(
    r"(AIza[0-9A-Za-z_\-]{10,}|sk-(proj-)?[A-Za-z0-9_\-]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}"
    r"|hf_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{15,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
# skillOverrides 값 화이트리스트(codex-MAJOR5: 'no secrets' 가정 대신 enum 검증)
SKILLOVERRIDE_ALLOWED = {"user-invocable-only", "disabled", "enabled", "auto", "default"}

def redact(s):
    return SECRET_RE.sub("[REDACTED]", s) if isinstance(s, str) else s

def redact_obj(o):
    if isinstance(o, str): return redact(o)
    if isinstance(o, list): return [redact_obj(x) for x in o]
    if isinstance(o, dict): return {k: redact_obj(v) for k, v in o.items()}
    return o

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # parent of scripts/
HOME = os.path.expanduser("~")
RUNTIME = os.path.join(ROOT, ".claude", "runtime")
WARN = []

def resolve(p):
    if p.startswith("~"): return os.path.expanduser(p)
    if os.path.isabs(p): return p
    return os.path.join(ROOT, p)

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""): h.update(c)
    return h.hexdigest()

def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")

def hm(p):  # hash+mtime for existing file
    return {"sha256": sha256_file(p), "mtime": mtime(p)}

def globs_of(spec):
    out = []
    if "glob" in spec: out += sorted(glob.glob(resolve(spec["glob"])))
    if "globs" in spec:
        for g in spec["globs"]: out += sorted(glob.glob(resolve(g)))
    if "file" in spec: out += [resolve(spec["file"])]
    if "files" in spec: out += [resolve(f) for f in spec["files"]]
    return out

def parse_fm(p):
    fm = {}
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception as e:
        WARN.append(f"frontmatter read fail {p}: {e}"); return fm
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end > 0:
            for line in txt[3:end].splitlines():
                m = re.match(r"^(name|description|disable-model-invocation|allowed-tools)\s*:\s*(.*)$", line)
                if m: fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm

FILES_HASH = {}  # map-path-or-resolved → {sha256,mtime} (staleness gate; no secrets)

def reg_hash(keypath, realpath):
    FILES_HASH[keypath] = hm(realpath)

# ---- collectors: return list/dict of items ----
def c_skill_frontmatter(spec):
    items = []
    for p in globs_of(spec):
        if not os.path.isfile(p): WARN.append(f"missing skill {p}"); continue
        fm = parse_fm(p)
        rel = os.path.relpath(p, ROOT)
        reg_hash(rel, p)
        items.append({"name": fm.get("name", os.path.basename(os.path.dirname(p))),
                      "path": rel, **hm(p),
                      "dmi": fm.get("disable-model-invocation", "(none)"),
                      "allowed_tools": fm.get("allowed-tools", "(unset=all)"),
                      "desc1": redact(fm.get("description", ""))[:160]})
    return items

def c_json_skilloverrides(spec):
    p = resolve(spec["file"]); rel = os.path.relpath(p, ROOT)
    if not os.path.isfile(p): WARN.append(f"missing {p}"); return {}
    reg_hash(rel, p)
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        WARN.append(f"settings json fail: {e}"); return {"path": rel, **hm(p)}
    so = d.get("skillOverrides", {})
    # 값 검증(codex-MAJOR5): 알려진 enum만 그대로, 그 외는 '(non-enum)'으로 마스킹(가정 제거)
    safe_so = {k: (v if v in SKILLOVERRIDE_ALLOWED else "(non-enum)") for k, v in so.items()}
    return {"path": rel, **hm(p), "model": d.get("model", "(unset)"),
            "override_count": len(so), "overrides": safe_so}

def c_file_hash_list(spec):
    items = []
    for p in globs_of(spec):
        if not os.path.exists(p): WARN.append(f"missing {p}"); continue
        rel = os.path.relpath(p, ROOT) if p.startswith(ROOT) else p
        reg_hash(rel, p)
        items.append({"path": rel, **hm(p)})
    return items

def c_hookify_action(spec):
    items = []
    for p in globs_of(spec):
        if not os.path.isfile(p): continue
        rel = os.path.relpath(p, ROOT); reg_hash(rel, p)
        txt = open(p, encoding="utf-8", errors="replace").read()
        def g(key):
            m = re.search(rf"^{key}\s*:\s*(.*)$", txt, re.M); return m.group(1).strip() if m else "(unset)"
        items.append({"rule": os.path.basename(p).replace("hookify.", "").replace(".local.md", ""),
                      "path": rel, **hm(p),
                      "event": g("event"), "action": g("action"), "enabled": g("enabled")})
    return items

def c_grep_anchor(spec):
    p = resolve(spec["file"]);
    if not os.path.isfile(p): WARN.append(f"missing anchor target {p}"); return {}
    rel = os.path.relpath(p, ROOT) if p.startswith(ROOT) else spec["file"]
    reg_hash(rel, p)
    lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
    anchors = []
    for pat in spec.get("patterns", []):
        for i, line in enumerate(lines, 1):
            if pat in line:
                anchors.append({"pattern": pat, "line": i, "snippet": redact(line.strip())[:120]})
                if sum(1 for a in anchors if a["pattern"] == pat) >= 6: break
    return {"file": rel, **hm(p), "anchor_count": len(anchors), "anchors": anchors}

def c_presence_list(spec):
    items = []
    for p in globs_of(spec):
        ex = os.path.exists(p); isd = os.path.isdir(p)
        rel = os.path.relpath(p, ROOT) if p.startswith(ROOT) else p
        e = {"path": rel, "exists": ex, "is_dir": isd}
        if ex:
            e["mtime"] = mtime(p)
            if isd: e["child_count"] = len(os.listdir(p))
            else: e.update(hm(p)); reg_hash(rel, p)
        items.append(e)
    return items

def c_glob_exists(spec):
    matches = sorted(glob.glob(resolve(spec["glob"])))
    return {"pattern": spec["glob"], "exists": len(matches) > 0,
            "count": len(matches), "matches": [os.path.relpath(m, ROOT) for m in matches]}

def c_presence_only(spec):  # secrets: stat only, NO read, NO hash
    items = []
    for p in globs_of(spec):
        ex = os.path.exists(p)
        rel = os.path.relpath(p, ROOT) if p.startswith(ROOT) else p
        items.append({"path": rel, "exists": ex, "mtime": (mtime(p) if ex else None)})
    return items

COLLECTORS = {"skill_frontmatter": c_skill_frontmatter, "json_skilloverrides": c_json_skilloverrides,
              "file_hash_list": c_file_hash_list, "hookify_action": c_hookify_action,
              "grep_anchor": c_grep_anchor, "presence_list": c_presence_list,
              "glob_exists": c_glob_exists, "presence_only": c_presence_only}

def needs_rebuild(smpath, jpath):
    """--if-stale 가벼운 판단(mtime 게이트). 변경 있으면 True."""
    if not os.path.isfile(jpath): return True, "index 없음"
    try:
        prev = json.load(open(jpath, encoding="utf-8"))
    except Exception:
        return True, "index 손상"
    # source-map 변경(codex-MAJOR1: mtime 아닌 sha256)
    try:
        if sha256_file(smpath) != prev.get("source_map_sha256"):
            return True, "source-map 변경"
    except Exception:
        return True, "source-map 읽기실패"
    # content 변경(sha256, codex#1) + 삭제 감지
    fh = prev.get("files_hash", {})
    for path, rec in fh.items():
        rp = resolve(path)
        if not os.path.exists(rp): return True, f"파일 삭제 {path}"
        try:
            if sha256_file(rp) != rec.get("sha256"): return True, f"파일 변경 {path}"
        except Exception:
            return True, f"파일 읽기실패 {path}"
    # 새 파일 추가 감지(codex#2): 모든 glob 도메인 현재 매치 수 vs index item 수
    try:
        sm = yaml.safe_load(open(smpath, encoding="utf-8"))
    except Exception:
        return True, "source-map 파싱 실패"
    for name, spec in sm.get("domains", {}).items():
        if not ("glob" in spec or "globs" in spec):
            continue   # file/files 기반(grep_anchor 등)은 위 sha256 루프가 커버
        cur = len(globs_of(spec))
        items = prev.get("domains", {}).get(name, {}).get("items")
        if isinstance(items, list):
            idx_n = len(items)                       # 파일당 item 리스트(skills·hooks·hookify…)
        elif isinstance(items, dict) and "count" in items:
            idx_n = items["count"]                   # glob_exists(mode_c_cycles): 매치 수
        else:
            continue                                 # 비교 불가 도메인 skip
        if cur != idx_n:
            return True, f"{name} 파일 수 변경 {idx_n}->{cur}"
    # presence_only/presence_list freshness(codex-MAJOR2,3): stat만(secret 내용 안 읽음)
    for name, spec in sm.get("domains", {}).items():
        if spec.get("collector") not in ("presence_only", "presence_list"):
            continue
        rec_items = prev.get("domains", {}).get(name, {}).get("items", [])
        rec = {it.get("path"): it for it in rec_items if isinstance(it, dict)}
        cur_n = 0
        for p in globs_of(spec):
            rel = os.path.relpath(p, ROOT) if p.startswith(ROOT) else p
            cur_n += 1
            it = rec.get(rel)
            ex = os.path.exists(p)
            if it is None:
                return True, f"{name} 새 항목 {rel}"
            if it.get("exists") != ex:
                return True, f"{name} 존재변경 {rel}"
            if ex:
                if it.get("mtime") != mtime(p):
                    return True, f"{name} mtime변경 {rel}"
                if os.path.isdir(p) and it.get("child_count") != len(os.listdir(p)):
                    return True, f"{name} dir내용변경 {rel}"
        if cur_n != len(rec_items):
            return True, f"{name} 항목수 변경"
    return False, "fresh"

def main():
    smpath = os.path.join(ROOT, ".claude", "skills", "_evidence-core", "system-source-map.yaml")
    jpath0 = os.path.join(ROOT, ".claude", "runtime", "system_truth_index.json")
    if "--if-stale" in sys.argv:
        need, why = needs_rebuild(smpath, jpath0)
        if not need:
            print(f"[if-stale] fresh — 갱신 생략 ({why})"); return 0
        print(f"[if-stale] 갱신 필요: {why}")
    sm = yaml.safe_load(open(smpath, encoding="utf-8"))
    os.makedirs(RUNTIME, exist_ok=True)
    prev = {}
    jpath = os.path.join(RUNTIME, "system_truth_index.json")
    if os.path.isfile(jpath):
        try: prev = json.load(open(jpath, encoding="utf-8")).get("files_hash", {})
        except Exception: prev = {}

    out_domains = {}
    for name, spec in sm.get("domains", {}).items():
        col = spec.get("collector")
        fn = COLLECTORS.get(col)
        if not fn: WARN.append(f"unknown collector {col} ({name})"); continue
        items = fn(spec)
        out_domains[name] = {"collector": col, "risk": spec.get("risk"),
                             "answers": spec.get("answers", []), "items": items}

    index = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "harness": sm.get("harness", "?"),
        "source_map_sha256": sha256_file(smpath),
        "domain_count": len(out_domains),
        "rules": "pointer/cache · hash 변경=stale · 위험claim=read source · secret 미저장 · env=presence만",
        "domains": out_domains,
        "files_hash": FILES_HASH,
    }
    index = redact_obj(index)  # 최종 secret redaction 패스 (rule §4)

    # 증분 diff (vs prev files_hash)
    changed = [k for k, v in FILES_HASH.items() if k in prev and prev[k].get("sha256") != v["sha256"]]
    new = [k for k in FILES_HASH if k not in prev]
    unchanged = [k for k in FILES_HASH if k in prev and prev[k].get("sha256") == FILES_HASH[k]["sha256"]]

    body = json.dumps(index, ensure_ascii=False, indent=2)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    # 원자적 쓰기(codex-MINOR9): temp→fsync→os.replace (concurrent probe/SessionStart 부분읽기 방지)
    def atomic_write(path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    atomic_write(jpath, body)
    atomic_write(os.path.join(RUNTIME, "system_truth_index.sha256"),
                 sha + "  system_truth_index.json\n")
    # secret 잔존 자기점검
    resid = len(SECRET_RE.findall(body))
    log = [
        f"[{index['generated_at']}] system_truth_indexer run",
        f"  source-map sha256: {index['source_map_sha256'][:12]}",
        f"  domains: {len(out_domains)} · hashed files: {len(FILES_HASH)}",
        f"  diff vs prev: changed={len(changed)} new={len(new)} unchanged={len(unchanged)}",
        f"  changed: {changed}" if changed else "  changed: []",
        f"  secret residual in index: {resid} (0 expected)",
        f"  warnings({len(WARN)}): " + ("; ".join(WARN) if WARN else "none"),
    ]
    open(os.path.join(RUNTIME, "system_truth_index.log"), "a", encoding="utf-8").write("\n".join(log) + "\n")
    print("\n".join(log))
    print(f"  → {jpath}")
    return 1 if resid else 0

if __name__ == "__main__":
    sys.exit(main())
