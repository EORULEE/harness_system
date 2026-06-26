#!/usr/bin/env python3
"""
publish_shared_context.py — _active_context.md → vault/wiki/_system/ 공유 미러 발행.

Memory Continuity v2 + 모델 공유지식층(canary):
- SHARED_CONTEXT.md = `_active_context.md`의 **생성형 읽기 전용 미러**(source of truth 아님).
- AGENT_MEMORY_INDEX.yaml = 정본·미러·checkpoint·관련 노트로의 **포인터만**(내용 사본 X).
- NO LLM / NO network. 순수 추출·포매팅.
- 정본(MEMORY.md / _active_context.md / project_session_checkpoint.md)은 **읽기만**, 절대 수정 안 함.
- transcript 원문 미포함(목표/완료/다음행동/고정사실/Wiki링크만).
- secret_masking 적용 후 저장 · 최대 2KB · atomic replace.
- _active_context 가 stale(또는 부재/project 불일치)이면 미러도 stale=true 로 표기.

경로 override(테스트/canary용 인자):
  --active <path>  --out-dir <dir>  --project-id <id>  --checkpoint <path>
"""
import os, sys, re, json, hashlib, tempfile, datetime, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from secret_masking import mask_secrets, residual_count
except Exception:
    def mask_secrets(t): return t
    def residual_count(t): return 0

HARD_CAP = 2048
SHARED_NAME = "SHARED_CONTEXT.md"
INDEX_NAME  = "AGENT_MEMORY_INDEX.yaml"

def now_iso(): return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
def sanitize(p): return re.sub(r'[^a-zA-Z0-9]', '-', p)

def parse_active_context(path):
    """update_active_context.py 가 렌더한 frontmatter 파싱(scalar + bullet list)."""
    if not os.path.isfile(path):
        return None, None
    raw = open(path, encoding="utf-8").read()
    m = re.search(r'^---\n(.*?)\n---', raw, re.S)
    if not m:
        return None, raw
    fm, cur = {}, None
    for ln in m.group(1).splitlines():
        h = re.match(r'([a-z_]+):\s*(.*)$', ln)
        if h:
            k, v = h.group(1), h.group(2).strip()
            if v == "[]":
                fm[k] = []
            elif v == "":
                fm[k] = []                       # 비어있지 않은 list(다음 줄 bullet)
            else:
                fm[k] = v.strip('"')
            cur = k
        else:
            b = re.match(r'\s*-\s*"?(.*?)"?\s*$', ln)
            if b and isinstance(fm.get(cur), list):
                fm[cur].append(b.group(1))
    return fm, raw

def detect_stale(fm, target_project):
    """stale 판정 + 사유. _emit_active_context_core 의 stale 규칙과 정합."""
    if fm is None:
        return True, "no_active_context"
    if fm.get("project_id") != target_project:
        return True, "project_mismatch"
    if fm.get("status") in ("failed", "stale"):
        return True, "status_" + str(fm.get("status"))
    if fm.get("needs_review") in ("true", "True", True):
        return True, "needs_review"
    return False, "ok"

def _bullets(items, cap):
    items = [str(x) for x in (items or []) if str(x).strip()]
    if not items:
        return "- (없음)"
    return "\n".join("- " + x for x in items[:cap])

def render_shared(fm, raw, src_rel, src_sha, target_project, stale, reason):
    obj  = fm.get("current_objective") or "(none)"
    nxt  = fm.get("next_action") or "(unverified)"
    done = fm.get("completed") or []
    lock = fm.get("locked_facts") or []
    wiki = fm.get("relevant_wiki_notes") or []
    status = fm.get("status", "?")
    head = [
        "---",
        "shared_context_schema: shared_context/v1",
        f'generated_at: "{now_iso()}"',
        f'project_id: "{target_project}"',
        f'source_active_context: "{src_rel}"',
        f'source_sha256: "{src_sha}"',
        f'source_status: "{status}"',
        f'stale: {"true" if stale else "false"}',
        f'stale_reason: "{reason}"',
        "---", "",
        "# 🔗 SHARED_CONTEXT (생성형 읽기 전용 미러)", "",
        "> ⚠️ **이 문서는 source of truth가 아닙니다.** `_active_context.md`(Claude 세션 연속성 정본)의",
        "> **자동 생성 읽기 전용 미러**입니다. 사람·모델 모두 **직접 편집 금지**(다음 publish 시 덮어씀).",
        "> 정본: `MEMORY.md`(장기 규칙·반복 사실) · `_active_context.md`(현재 작업) · `project_session_checkpoint.md`(정식 인계).",
        "> 수치·인용·사실의 최종 정본 = Experiments / kb / Data / Code.",
    ]
    if stale:
        head.append(f"> 🟥 **stale=true ({reason})** — 이 미러를 신뢰하지 말고 정본을 재확인하세요.")
    body = [
        "",
        f"- **현재 목표**: {obj}",
        f"- **다음 행동**: {nxt}",
        "",
        "## 완료",
        _bullets(done, 10),
        "",
        "## 고정 사실",
        _bullets(lock, 10),
        "",
        "## 관련 Wiki 링크",
        _bullets(wiki, 10),
        "",
    ]
    return "\n".join(head + body)

def _fit(text):
    """2KB 초과 시 list bullet 점진 축소(목표/다음행동/배너는 보존)."""
    if len(text.encode("utf-8")) <= HARD_CAP:
        return text, False
    truncated = False
    lines = text.split("\n")
    # 뒤에서부터 '- ' bullet 제거(관련 Wiki → 고정 → 완료 순으로 잘림)
    while len("\n".join(lines).encode("utf-8")) > HARD_CAP:
        idx = None
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r'^- ', lines[i]) and lines[i] != "- (없음)":
                idx = i; break
        if idx is None:
            break
        lines.pop(idx); truncated = True
    out = "\n".join(lines)
    if len(out.encode("utf-8")) > HARD_CAP:
        out = out.encode("utf-8")[:HARD_CAP].decode("utf-8", "ignore"); truncated = True
    return out, truncated

def render_index(fm, target_project, out_dir, active_path, checkpoint_path, memory_dir):
    wiki = fm.get("relevant_wiki_notes") or [] if fm else []
    def yl(items):
        items = [str(x) for x in items if str(x).strip()]
        return "\n".join('    - "' + x.replace('"', "'") + '"' for x in items[:10]) if items else "    []"
    lines = [
        "# AGENT_MEMORY_INDEX — 포인터 전용(내용 사본 아님). 모델 공유 진입점.",
        "# 생성: scripts/publish_shared_context.py · 직접 편집 금지(자동 갱신·덮어씀).",
        "# source of truth 아님 — 정본은 pointers.* 가 가리키는 파일.",
        "schema: agent_memory_index/v1",
        f'generated_at: "{now_iso()}"',
        f'current_project: "{target_project}"',
        "pointers:",
        f'  active_context_truth: "{active_path}"        # 현재 작업 정본',
        f'  latest_checkpoint: "{checkpoint_path}"        # 정식 세션 인계 정본',
        f'  memory_index: "{os.path.join(memory_dir, "MEMORY.md")}"  # 장기 규칙·반복 사실',
        f'  latest_shared_context: "{os.path.join(out_dir, SHARED_NAME)}"  # 생성형 읽기 미러',
        "  related_project_pages:",
        yl(wiki),
        "  related_experiment_cards:",
        "    []        # 큐레이션 대상(Experiments 정본 링크) — 자동 생성 안 함",
        "  related_decision_claim_notes:",
        "    []        # 큐레이션 대상(decisions/claims 정본 링크) — 자동 생성 안 함",
        'notes: "pointers only; no content copies; not source of truth"',
        "",
    ]
    return "\n".join(lines)

def _atomic_write(path, text):
    d = os.path.dirname(path); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try: os.unlink(tmp)
            except Exception: pass

def publish(active_path, out_dir, target_project, checkpoint_path):
    memory_dir = os.path.dirname(active_path)
    fm, raw = parse_active_context(active_path)
    # source sha256 = active_context 파일 바이트 해시(부재 시 빈 문자열)
    src_sha = hashlib.sha256(open(active_path, "rb").read()).hexdigest() if os.path.isfile(active_path) else ""
    stale, reason = detect_stale(fm, target_project)
    src_rel = active_path
    shared = render_shared(fm or {}, raw or "", src_rel, src_sha, target_project, stale, reason)
    shared = mask_secrets(shared)                       # mask BEFORE write
    shared, truncated = _fit(shared)
    resid = residual_count(shared)
    sp = os.path.join(out_dir, SHARED_NAME)
    _atomic_write(sp, shared)
    # index(포인터 전용)
    idx = render_index(fm or {}, target_project, out_dir, active_path, checkpoint_path, memory_dir)
    idx = mask_secrets(idx)
    ip = os.path.join(out_dir, INDEX_NAME)
    _atomic_write(ip, idx)
    return {"shared_context": sp, "index": ip,
            "bytes": len(shared.encode("utf-8")), "truncated": truncated,
            "stale": stale, "stale_reason": reason, "source_sha256": src_sha,
            "residual_secrets": resid + residual_count(idx)}

if __name__ == "__main__":
    cwd = os.environ.get("CONTINUITY_CWD") or os.getcwd()
    default_proj = sanitize(cwd)
    default_mem = os.environ.get("CONTINUITY_MEMORY_ROOT") or \
                  os.path.expanduser(f"~/.claude/projects/{default_proj}/memory")
    ap = argparse.ArgumentParser()
    ap.add_argument("--active", default=os.path.join(default_mem, "_active_context.md"))
    ap.add_argument("--out-dir", default=os.path.join(cwd, "vault", "wiki", "_system"))
    ap.add_argument("--project-id", default=default_proj)
    ap.add_argument("--checkpoint", default=os.path.join(default_mem, "project_session_checkpoint.md"))
    a = ap.parse_args()
    res = publish(a.active, a.out_dir, a.project_id, a.checkpoint)
    print(json.dumps(res, ensure_ascii=False))
