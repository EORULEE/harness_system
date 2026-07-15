#!/usr/bin/env python3
"""skill_shadow_check.py — 스킬 이원화 shadow/drift 검사 (fail-closed 분류 + parity)

계약: _output/contracts/contract-skill-dualization-20260708.md (AC2·AC12·AC13·AC14)
정본 config: .claude/skills-ownership.yaml

모드:
  classify  — 분류 무결성만: 실측 dir == 3부류 disjoint union. 미분류/중복 = exit 2 (fail-closed).
  check     — classify + sync_subset parity(제외규칙 후 md5). drift 있으면 exit 1 (수동/CI).
  report    — check 와 동일 계산이나 **항상 exit 0** + 사람용 경고(session-start advisory 훅용).

원칙:
  - repo = SoT. parity 비교는 exclude_patterns(.claude/runtime·memory·*.bak*·__pycache__·*.tmp·*~) 제외 후.
  - global_only_personal(개인도구)·project_only 는 sync/parity 대상 아님(무변경).
  - drift 방향(global-ahead/repo-ahead/both-changed)은 mtime+내용 휴리스틱(AC14).
"""
import argparse
import hashlib
import os
import sys
from fnmatch import fnmatch

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML 필요: pip install pyyaml\n")
    sys.exit(3)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG = os.path.join(REPO_ROOT, ".claude", "skills-ownership.yaml")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    classes = cfg.get("classes", {})
    for k in ("sync_subset", "global_only_personal", "project_only", "excluded"):
        classes.setdefault(k, [])
    cfg["classes"] = classes
    paths = cfg.get("paths", {})
    repo_skills = os.path.join(REPO_ROOT, paths.get("repo_skills", ".claude/skills"))
    global_skills = os.path.expanduser(paths.get("global_skills", "~/.claude/skills"))
    cfg["_repo_skills"] = os.path.abspath(repo_skills)
    cfg["_global_skills"] = os.path.abspath(global_skills)
    cfg["_exclude"] = cfg.get("exclude_patterns", [])
    cfg["_allow_divergence"] = set(cfg.get("allow_divergence", []) or [])
    return cfg


def list_dirs(p):
    if not os.path.isdir(p):
        return set()
    return {d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))}


def is_excluded(relpath, patterns):
    """relpath(posix)가 제외 대상인가."""
    rel = relpath.replace(os.sep, "/")
    base = rel.rsplit("/", 1)[-1]
    for pat in patterns:
        if "*" in pat:
            if fnmatch(base, pat) or fnmatch(rel, pat):
                return True
        else:
            # 경로 세그먼트 매칭 (.claude/runtime, __pycache__)
            if rel == pat or rel.startswith(pat + "/") or ("/" + pat + "/") in ("/" + rel + "/"):
                return True
    return False


def dir_file_map(root, patterns):
    """{relpath: (md5, mtime)} — 제외규칙 적용."""
    out = {}
    if not os.path.isdir(root):
        return out
    # 루트 자체가 symlink 면 역참조하지 않고 토큰만('verified copy, symlink 아님' 원칙)
    if os.path.islink(root):
        out["<self>"] = (f"<symlink:{os.readlink(root)}>", 0.0)
        return out
    for dp, dns, fns in os.walk(root):  # followlinks=False(기본) — symlink dir 내부 미추적
        # 디렉터리 레벨 제외 (성능 + __pycache__/.claude/runtime 하위 스킵) + symlink dir 토큰화
        rel_dir = os.path.relpath(dp, root)
        pruned = []
        for dn in dns:
            reld = (os.path.join(rel_dir, dn) if rel_dir != "." else dn)
            if is_excluded(reld, patterns):
                continue
            full = os.path.join(dp, dn)
            if os.path.islink(full):
                # symlink 디렉터리: 조용히 스킵되지 않게 토큰 기록 후 prune(내부 미추적)
                out[reld.replace(os.sep, "/") + "/"] = (f"<symlink:{os.readlink(full)}>", 0.0)
                continue
            pruned.append(dn)
        dns[:] = pruned
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root)
            if is_excluded(rel, patterns):
                continue
            fp = os.path.join(dp, fn)
            key = rel.replace(os.sep, "/")
            # symlink 은 역참조하지 않고 별도 토큰으로 기록('verified copy, symlink 아님' 원칙:
            # symlink 가 있으면 parity 에서 구분되어 드러나야 함, 조용히 대상내용 해시 금지)
            if os.path.islink(fp):
                out[key] = (f"<symlink:{os.readlink(fp)}>", 0.0)
                continue
            try:
                h = hashlib.md5()
                with open(fp, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                out[key] = (h.hexdigest(), os.path.getmtime(fp))
            except OSError:
                out[key] = ("<unreadable>", 0.0)
    return out


def validate_classification(cfg):
    """실측 dir == disjoint union 검증. 반환: (ok, errors[list], warnings[list]).

    fail-closed = **실측에 있는데 미분류**(관리 안 되는 스킬 = shadow 위험) → error.
    config엔 있으나 실측에 없음(stale-absent) = shadow 위험 없음(없는 걸 못 가림) → warning
    (특히 global_only_personal 은 머신별 부재가 정상일 수 있음 — codex MINOR 반영).
    """
    c = cfg["classes"]
    errors, warnings = [], []
    from collections import Counter
    all_named = c["sync_subset"] + c["global_only_personal"] + c["project_only"]
    dup = [n for n, k in Counter(all_named).items() if k > 1]
    if dup:
        errors.append(f"중복분류(2+ class): {sorted(dup)}")

    repo = list_dirs(cfg["_repo_skills"])
    glob = list_dirs(cfg["_global_skills"])
    excluded = set(c["excluded"])

    expect_repo = set(c["sync_subset"]) | set(c["project_only"])
    expect_glob = set(c["sync_subset"]) | set(c["global_only_personal"])

    # 실측에 있는데 미분류 → hard error (fail-closed, shadow 위험)
    repo_unclassified = sorted((repo - excluded) - expect_repo)
    glob_unclassified = sorted((glob - excluded) - expect_glob)
    if repo_unclassified:
        errors.append(f"repo 미분류 dir(fail-closed): {repo_unclassified}")
    if glob_unclassified:
        errors.append(f"global 미분류 dir(fail-closed): {glob_unclassified}")

    # config엔 있으나 실측에 없음(stale-absent) → warning (shadow 위험 아님)
    repo_missing = sorted(expect_repo - repo)
    glob_missing = sorted(expect_glob - glob)
    if repo_missing:
        warnings.append(f"config엔 있으나 repo에 없음(stale-absent): {repo_missing}")
    if glob_missing:
        warnings.append(f"config엔 있으나 global에 없음(stale-absent): {glob_missing}")

    return (len(errors) == 0, errors, warnings)


def parity_scan(cfg):
    """sync_subset 각 dir parity. 반환: list of dict(name, status, direction, detail)."""
    c = cfg["classes"]
    patterns = cfg["_exclude"]
    allow = cfg["_allow_divergence"]
    results = []
    for name in sorted(c["sync_subset"]):
        rroot = os.path.join(cfg["_repo_skills"], name)
        groot = os.path.join(cfg["_global_skills"], name)
        rmap = dir_file_map(rroot, patterns)
        gmap = dir_file_map(groot, patterns)
        rkeys, gkeys = set(rmap), set(gmap)

        def _allowed(rel):
            return f"{name}/{rel}" in allow
        # allow_divergence 는 '내용 상이(differ)'만 허용한다. 파일의 추가/삭제(한쪽에만 존재)는
        # 여전히 drift 로 잡는다 — codex MAJOR 반영(divergence 가 '내용 전체 방치'로 번지지 않게).
        only_repo = sorted(rkeys - gkeys)
        only_glob = sorted(gkeys - rkeys)
        differ = sorted(k for k in (rkeys & gkeys)
                        if rmap[k][0] != gmap[k][0] and not _allowed(k))
        known_div = sorted(k for k in (rkeys & gkeys)
                           if rmap[k][0] != gmap[k][0] and _allowed(k))
        if not only_repo and not only_glob and not differ:
            r = {"name": name, "status": "clean"}
            if known_div:
                r["known_divergence"] = known_div
            results.append(r)
            continue
        # 방향 휴리스틱: 각 side 고유/변경 파일의 최신 mtime
        repo_side = [rmap[k][1] for k in only_repo] + [rmap[k][1] for k in differ]
        glob_side = [gmap[k][1] for k in only_glob] + [gmap[k][1] for k in differ]
        rmax = max(repo_side) if repo_side else 0.0
        gmax = max(glob_side) if glob_side else 0.0
        if only_repo and only_glob:
            direction = "both-changed"
        elif gmax > rmax + 1.0:
            direction = "global-ahead"
        elif rmax > gmax + 1.0:
            direction = "repo-ahead"
        else:
            direction = "both-changed"
        results.append({
            "name": name, "status": "drift", "direction": direction,
            "only_repo": only_repo, "only_global": only_glob, "differ": differ,
            "known_divergence": known_div,
        })
    return results


def integrity_scan(cfg):
    """AC18: global sync_subset tree 에 예기치 않은 오염(bak/runtime/staging/lock) 스캔.
    반환: (stray_root[list], contaminated[list of (dir, [files])])."""
    patterns = cfg["_exclude"]
    groot_base = cfg["_global_skills"]
    # skills 루트의 sync staging/bak/lock 잔여
    stray = []
    if os.path.isdir(groot_base):
        for e in os.listdir(groot_base):
            if "sync-stage" in e or "sync-bak" in e or e == ".skill-sync.lock":
                stray.append(e)
    # 각 sync_subset dir 안의 exclude-pattern 파일(정상 스킬엔 없어야).
    # __pycache__ 는 파이썬 import 시 자동재생성 = 양성 → 무결성 FAIL 로 세지 않음(codex 과엄격 회피).
    benign = ("__pycache__",)
    contaminated = []
    for name in cfg["classes"]["sync_subset"]:
        d = os.path.join(groot_base, name)
        if not os.path.isdir(d):
            continue
        hits = []
        for dp, dns, fns in os.walk(d):
            for fn in fns:
                rel = os.path.relpath(os.path.join(dp, fn), d).replace(os.sep, "/")
                if is_excluded(rel, patterns) and not any(b in rel for b in benign):
                    hits.append(rel)
        if hits:
            contaminated.append((name, sorted(set(hits))))
    return sorted(stray), contaminated


def print_parity(results, verbose=True):
    drift = [r for r in results if r["status"] == "drift"]
    clean = len(results) - len(drift)
    kdiv = sum(len(r.get("known_divergence") or []) for r in results)
    for r in drift:
        print(f"  DRIFT [{r['direction']}] {r['name']}")
        if verbose:
            if r["only_global"]:
                print(f"      global-only 파일: {r['only_global']}")
            if r["only_repo"]:
                print(f"      repo-only 파일:   {r['only_repo']}")
            if r["differ"]:
                print(f"      내용상이:        {r['differ']}")
    print(f"--- sync_subset {len(results)}개: clean={clean} · drift={len(drift)} "
          f"· known-divergence 파일={kdiv} ---")
    return drift


def main():
    ap = argparse.ArgumentParser(description="스킬 이원화 shadow/drift 검사")
    ap.add_argument("mode", choices=["classify", "check", "report", "integrity"])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        sys.stderr.write(f"config 없음: {args.config}\n")
        sys.exit(3)
    cfg = load_config(args.config)

    ok, errors, warnings = validate_classification(cfg)
    if not args.quiet:
        print("=== skill_shadow_check: 분류 무결성 (fail-closed) ===")
        if ok:
            c = cfg["classes"]
            print(f"  OK — sync_subset={len(c['sync_subset'])} "
                  f"global_only={len(c['global_only_personal'])} "
                  f"project_only={len(c['project_only'])} excluded={len(c['excluded'])}")
        else:
            for e in errors:
                print(f"  FAIL — {e}")
        for w in warnings:
            print(f"  WARN — {w}")

    if args.mode == "classify":
        sys.exit(0 if ok else 2)

    if args.mode == "integrity":
        stray, contaminated = integrity_scan(cfg)
        if not args.quiet:
            print("=== global tree 무결성 (AC18) ===")
        # FAIL 조건 = sync 가 남긴 잔여(staging/bak/lock at root). 이게 있으면 sync 원자성 위반.
        if stray:
            print(f"  FAIL STRAY(sync 잔여): {stray}")
        # 기존 .bak 등 클러터 = advisory(sync 유래 아님, hygiene). FAIL 아님.
        for name, hits in contaminated:
            print(f"  advisory 클러터 {name}: {hits}")
        if not args.quiet:
            ncl = sum(len(h) for _, h in contaminated)
            print(f"--- 무결성: {'FAIL(sync 잔여)' if stray else 'OK(sync 잔여 0)'}"
                  f" · advisory 클러터 파일={ncl} ---")
        sys.exit(1 if stray else 0)

    # classify 실패는 check/report 에서도 치명(fail-closed) — 단 report 는 exit0 유지
    if not args.quiet:
        print("=== parity (sync_subset, 제외규칙 적용) ===")
    results = parity_scan(cfg)
    drift = print_parity(results, verbose=not args.quiet)

    if args.mode == "report":
        # advisory: 항상 exit 0. global-ahead 는 특별 경고(편집이 repo 아닌 global 서 남).
        ga = [r["name"] for r in drift if r.get("direction") == "global-ahead"]
        if ga:
            print(f"⚠️ global-ahead drift(글로벌서 직접편집 의심 → repo 로 흡수 필요): {ga}")
        sys.exit(0)

    # check: 분류 실패 or drift 있으면 nonzero
    if not ok:
        sys.exit(2)
    sys.exit(1 if drift else 0)


if __name__ == "__main__":
    main()
