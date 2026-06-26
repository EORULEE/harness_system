#!/usr/bin/env python3
"""
update_active_context.py — render + atomic-write the single ACTIVE_CONTEXT file.

Memory Continuity v2 (보강, 기존 대체 아님):
- ONE file: <project memory root>/_active_context.md  (MEMORY.md 옆, MEMORY.md 절대 미접근)
- secret_masking 을 write 직전에 적용
- 크기: 목표 <=1KB, HARD CAP 2KB (가변 필드 truncate 로 맞춤)
- atomic replace (같은 dir temp -> os.replace), append 없음(항상 전체 덮어쓰기)
- LLM/네트워크 없음. 순수 포매팅.
"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from secret_masking import mask_secrets, residual_count
except Exception:
    def mask_secrets(t): return t
    def residual_count(t): return 0

SCHEMA_VERSION = "active_context/v2"
HARD_CAP = 2048
TARGET = 1024

FIELDS = ["schema_version","project_id","source_session_id","source_event","updated_at",
          "status","current_objective","completed","next_action","open_loops","blockers",
          "locked_facts","changed_files","relevant_wiki_notes","latest_checkpoint",
          "confidence","needs_review",
          # 추적성(라벨 추출, Memory Continuity v2 보강)
          "source_checkpoint","source_checkpoint_sha256","extracted_sections","truncated"]

def _scalar(v):
    if v is None: return '""'
    if isinstance(v, bool): return 'true' if v else 'false'
    s = str(v).replace('\\','\\\\').replace('"','\\"').replace('\n',' ').strip()
    return '"' + s + '"'

def _list(v, cap, itemcap):
    if not v: return " []"
    out = "\n"
    for it in v[:cap]:
        out += "  - " + _scalar(str(it).replace('\n',' ').strip()[:itemcap]) + "\n"
    return out.rstrip("\n")

def render(d, listcap=6, itemcap=160):
    data = {k: d.get(k) for k in FIELDS}
    data["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    lines = ["---"]
    for k in FIELDS:
        v = data.get(k)
        if isinstance(v, list):
            lines.append(f"{k}:" + _list(v, listcap, itemcap))
        else:
            lines.append(f"{k}: " + _scalar(v))
    lines += ["---", "", f"# ACTIVE CONTEXT — {data.get('project_id','')}", "",
              f"**current_objective**: {data.get('current_objective') or '(none)'}",
              f"**next_action**: {data.get('next_action') or '(unverified — needs_review)'}"]
    if data.get("needs_review") in (True, "true"):
        lines += ["", "> needs_review=true — 근거 불명확. checkpoint/transcript 로 확인 후 사용."]
    return "\n".join(lines) + "\n"

def _fit(d):
    # listcap 10 부터 시작 — completed/locked 최대 10개 표시, 2KB 초과 시에만 축소
    for listcap, itemcap in [(10,160),(8,140),(6,120),(4,100),(2,80),(1,60),(0,40)]:
        txt = render(d, listcap, itemcap)
        if len(txt.encode("utf-8")) <= HARD_CAP:
            return txt
    # last resort: hard-trim long scalars
    d = dict(d)
    d["current_objective"] = (d.get("current_objective") or "")[:120]
    d["next_action"] = (d.get("next_action") or "")[:120]
    return render(d, 0, 40)

def will_truncate_lists(d, max_list=10):
    """완료/locked 등 list 가 2KB 때문에 max_list 미만으로 잘릴지 사전 추정(truncated 정확화용)."""
    longest = max((len(d.get(k) or []) for k in
                   ("completed","locked_facts","open_loops","blockers","changed_files","relevant_wiki_notes")),
                  default=0)
    if longest == 0:
        return False
    for listcap, itemcap in [(10,160),(8,140),(6,120),(4,100),(2,80),(1,60),(0,40)]:
        if len(render(d, listcap, itemcap).encode("utf-8")) <= HARD_CAP:
            return listcap < longest      # 표시 가능한 cap 이 실제 항목수보다 작으면 잘림
    return True

def write_active_context(memory_root, data):
    os.makedirs(memory_root, exist_ok=True)
    txt = _fit(data)
    txt = mask_secrets(txt)                       # mask JUST before write
    b = txt.encode("utf-8")
    if len(b) > HARD_CAP:
        txt = b[:HARD_CAP].decode("utf-8", "ignore")
    resid = residual_count(txt)
    path = os.path.join(memory_root, "_active_context.md")
    fd, tmp = tempfile.mkstemp(dir=memory_root, prefix="._active_context.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(txt)
        os.replace(tmp, path)                      # atomic
    finally:
        if os.path.exists(tmp):
            try: os.unlink(tmp)
            except Exception: pass
    return path, len(txt.encode("utf-8")), resid

if __name__ == "__main__":
    mem = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    data = json.load(sys.stdin)
    p, sz, resid = write_active_context(mem, data)
    print(json.dumps({"path": p, "bytes": sz, "residual_secrets": resid}, ensure_ascii=False))
