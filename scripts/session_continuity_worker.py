#!/usr/bin/env python3
"""
session_continuity_worker.py — continuity queue 처리 → ACTIVE_CONTEXT atomic 갱신.

Memory Continuity v2:
- NO LLM / NO network. 순수 구조적 추출.
- queue 이벤트(session-end.mjs / post-compact.mjs 가 기록)를 읽음.
- 정보 우선순위: 최신 checkpoint > PostCompact compact_summary >
  SessionEnd 구조화 runtime metadata > transcript tail(bounded pointer 만, 사실 승격 X).
- failure-safe: MEMORY.md / checkpoint / 기존 유효 ACTIVE_CONTEXT 절대 손상 안 함.
- 실패 사유는 continuity_state.json 에 기록.
- ACTIVE_CONTEXT write 직전 secret_masking 적용.

경로 동적 해석(테스트용 env override):
  CONTINUITY_MEMORY_ROOT, CONTINUITY_RUNTIME_DIR, CONTINUITY_CWD, CONTINUITY_SKIP_CWD_CHECK
"""
import os, sys, json, re, time, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_active_context import write_active_context, will_truncate_lists, SCHEMA_VERSION
try:
    from secret_masking import mask_secrets
except Exception:
    def mask_secrets(t): return t

TRANSCRIPT_TAIL_LINES = 40
TRANSCRIPT_TAIL_CAP   = 500
LOCK_STALE_SEC        = 300

def now_iso(): return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
def sanitize(p): return re.sub(r'[^a-zA-Z0-9]', '-', p)
def cwd(): return os.environ.get("CONTINUITY_CWD") or os.getcwd()

# scope 식별(Node 훅과 동일 규칙: project_id=sanitize(cwd), platform=sys.platform, machine_id=sha256(hostname)[:12])
def project_id(): return sanitize(cwd())
def platform_id(): return sys.platform
def machine_id():
    import socket, hashlib
    try: hn = socket.gethostname() or ""
    except Exception: hn = ""
    return hashlib.sha256(hn.encode("utf-8")).hexdigest()[:12]   # hostname 원문 대신 안정적 짧은 hash(민감정보 X)

def memory_root():
    return os.environ.get("CONTINUITY_MEMORY_ROOT") or \
           os.path.expanduser(f"~/.claude/projects/{sanitize(cwd())}/memory")
def runtime_dir():
    # machine-local home 기반(= memory_root 와 동일 규칙). 공유 프로젝트 cwd/.claude/runtime 로 fallback 금지.
    env = os.environ.get("CONTINUITY_RUNTIME_DIR")
    if env:
        return env
    home = os.path.expanduser("~")
    if not home or home == "~" or not os.path.isabs(home):
        return None   # home 해석 실패 → 호출측 advisory 종료(shared fallback 금지)
    return os.path.join(home, ".claude", "projects", sanitize(cwd()), "runtime")

# ---------- state ----------
def load_state(rt):
    try: return json.load(open(os.path.join(rt, "continuity_state.json")))
    except Exception: return {"schema_version": "continuity_state/v2", "failures": []}
def save_state(rt, st):
    p = os.path.join(rt, "continuity_state.json"); tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(st, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)

# ---------- lock ----------
def acquire_lock(qdir):
    lock = os.path.join(qdir, ".worker.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode()); os.close(fd); return lock
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(lock) > LOCK_STALE_SEC:
                os.unlink(lock); return acquire_lock(qdir)
        except Exception: pass
        return None
def release_lock(lock):
    try:
        if lock and os.path.exists(lock): os.unlink(lock)
    except Exception: pass

# ---------- sources ----------
def read_checkpoint(mem):
    p = os.path.join(mem, "project_session_checkpoint.md")
    if not os.path.isfile(p): return None
    try:
        return {"path": p, "mtime": os.path.getmtime(p), "text": open(p, encoding="utf-8").read()}
    except Exception:
        return None

def newest_block(text):
    """체크포인트는 최신 블록이 최상단(append-newest-at-top). 블록 경계 =
    '<!-- 세션 체크포인트 ...' HTML 주석. 최상단(최신) 블록 텍스트만 반환.
    → 옛 블록으로의 무음 fallthrough 차단(2026-07-15 block-drift 버그 수정).
    - 마커 0개(구형 체크포인트) → 전체 텍스트(하위호환).
    - 마커 1개 → 그 지점부터 끝까지.
    """
    if not text:
        return text or ""
    hits = [m.start() for m in re.finditer(r'(?m)^<!--\s*세션\s*체크포인트', text)]
    if not hits:
        # HTML 마커 없는 구형/외부 체크포인트: 블록 '선두' 헤더(작업 목표 | 현재 상태)를
        # 2차 블록 경계로. 신형(작업 목표)·구형(현재 상태) 블록리더 모두 커버 (codex F4).
        # ⚠️ 한계: 블록이 '## 완료' 같은 하위섹션으로 시작하는 malformed markerless 는
        #    선두헤더가 없어 under-scope 가능(HTML 마커 사용 시 무관 — 실사용 경로).
        hits = [m.start() for m in re.finditer(r'(?m)^##\s*(?:작업\s*목표|현재\s*상태)', text)]
    if len(hits) >= 2:
        return text[hits[0]:hits[1]]
    if len(hits) == 1:
        return text[hits[0]:]
    return text

def extract_from_checkpoint(ck):
    """Heuristic VERBATIM 추출(추론 금지). 최신(최상단) 블록으로 스코프. 못 찾으면 빈 dict."""
    if not ck: return {}
    t, out = newest_block(ck["text"]), {}
    m = re.search(r'다음\s*첫\s*행동[^\n:：]*[:：]?\s*(.+)', t)
    if not m:
        m = re.search(r'(?:^|\n)[-*\s>]*다음\s*=\s*(.+)', t)
    if m: out["next_action"] = re.sub(r'[*`]', '', m.group(1)).strip()[:280]
    # 작업 목표: 날짜접미사 '(2026-..-x)' 소비 후 → (a) 인라인 목표('—'/'-'/':' 구분)
    #   또는 (b) 다음 '비헤더' 줄(구형 줄바꿈 포맷). 개행이 헤더('##')·빈줄로 넘어가 오취하지 않게
    #   수평공백([ \t])만 소비하고, 다음줄 캡처는 (?!#) 로 헤더 배제 (codex F1).
    #   ⚠️ 다음줄 캡처는 '\n' 하나만(빈줄 넘지 않음) — 빈 목표섹션 뒤 무관 문단 오취 방지(codex 2차 NEW).
    obj = None
    m = re.search(r'##\s*작업\s*목표[ \t]*(?:\([^)]*\))?[ \t]*'
                  r'(?:[—:\-][ \t]*(\S[^\n]*)|\n[ \t]*(?!#)(\S[^\n]*))', t)
    if m:
        obj = m.group(1) or m.group(2)
    else:
        m = re.search(r'##\s*현재\s*상태[^\n]*\n[ \t]*>?[ \t]*(?!#)(\S[^\n]*)', t)
        if m: obj = m.group(1)
    if obj: out["current_objective"] = re.sub(r'[*>`]', '', obj).strip()[:280]
    return out


# completed / locked_facts — 명시적 라벨 섹션에서 bullet verbatim 추출 (no inference)
COMPLETED_LABELS = {"완료", "완료 항목", "완료 사항", "completed", "done"}
LOCKED_LABELS    = {"고정 사실", "잠금 사실", "잠금 사실(locked)", "locked facts", "locked"}
MAX_BULLETS      = 10

def _norm_label(s):
    return re.sub(r'\s+', ' ', re.sub(r'[*`#]', '', s)).strip().lower()

def _label_base(header):
    """헤더에서 날짜접미사/부가설명만 제거한 기본 라벨(정확일치용).
    예: '완료 (2026-07-14-c)' → '완료' · '완료 (2026-07-14-a) — ★ r53 ...' → '완료'.
    ⚠️ ASCII 하이픈/붙은 문자열은 분리하지 않음 — '완료-아님'·'locked-facts-to-review' 오매칭 방지(codex F5).
    → 헤더 포맷이 날짜접미사로 진화해도 라벨 섹션을 인식(2026-07-15 block-drift 버그 수정)."""
    n = _norm_label(header)
    # (a) ' — 설명' / ' – 설명' / ': 설명' 분리 — 구분자는 반드시 공백으로 감싼 대시 또는 ': '
    n = re.split(r'\s+[—–-]\s+|:\s', n, 1)[0].strip()
    # (b) 끝의 '(날짜)' 접미사만 제거 — 반드시 YYYY-MM-DD 로 시작하는 괄호만.
    #     ⚠️ '(아님)'·'(검토중)'·'(미정)' 같은 비날짜 괄호는 제거 안 함(오매칭 방지, codex r54 #4).
    n = re.sub(r'\s*\(\s*\d{4}-\d{2}-\d{2}[^()]*\)\s*$', '', n).strip()
    return n

def extract_labeled_bullets(ck_text, labels):
    """`## <label>` 헤딩(라벨 정확 일치) 아래의 명시적 bullet(- / *)만 verbatim 추출.
    - 다른 문단/인라인/제목내 키워드에서 추론하지 않음(헤딩 텍스트가 label과 일치할 때만 capture).
    - dedupe(안정적), MAX_BULLETS cap. 반환: (bullets[:10], truncated, matched_labels)."""
    out, matched, capturing = [], [], False
    for ln in ck_text.split("\n"):
        h = re.match(r'^##\s+(.*\S)\s*$', ln)
        if h:
            if _label_base(h.group(1)) in labels:
                capturing = True
                lbl = re.sub(r'[*`#]', '', h.group(1)).strip()
                if lbl not in matched:
                    matched.append(lbl)
            else:
                capturing = False
            continue
        if capturing:
            b = re.match(r'^\s*[-*]\s+(.+)$', ln)
            if b:
                item = b.group(1).strip()        # verbatim(요약·재작성 X)
                if item and item not in out:     # stable dedupe
                    out.append(item)
    truncated = len(out) > MAX_BULLETS
    return out[:MAX_BULLETS], truncated, matched

def read_runtime_meta(rt):
    out = {}
    for name, key in [("_prev_mode.txt", "prev_mode"), ("_current_turn.txt", "current_turn")]:
        try: out[key] = open(os.path.join(rt, name)).read().strip()[:80]
        except Exception: pass
    return out

def transcript_tail_hint(tp):
    """마지막 user 메시지 bounded+masked 힌트만. 전체 transcript 저장 안 함, 사실 승격 안 함."""
    if not tp or not os.path.isfile(tp): return None
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2); size = f.tell(); back = min(size, 200000)
            f.seek(size - back); tail = f.read().decode("utf-8", "ignore")
        for l in reversed([x for x in tail.splitlines() if x.strip()][-TRANSCRIPT_TAIL_LINES:]):
            try:
                o = json.loads(l)
                if o.get("type") == "user" or o.get("role") == "user":
                    msg = o.get("message") if isinstance(o.get("message"), dict) else {}
                    c = msg.get("content")
                    if isinstance(c, str) and c.strip():
                        return mask_secrets(re.sub(r'\s+', ' ', c)[:TRANSCRIPT_TAIL_CAP])
            except Exception:
                continue
    except Exception:
        return None
    return None

# ---------- build ----------
def build_state(event, mem, rt):
    proj = sanitize(cwd())
    ck = read_checkpoint(mem)
    d = {"schema_version": SCHEMA_VERSION, "project_id": proj,
         "source_session_id": event.get("session_id"), "source_event": event.get("event_type"),
         "updated_at": now_iso(), "status": "active",
         "current_objective": None, "completed": [], "next_action": None,
         "open_loops": [], "blockers": [], "locked_facts": [], "changed_files": [],
         "relevant_wiki_notes": [], "latest_checkpoint": None,
         "confidence": "low", "needs_review": False,
         # 추적성(라벨 추출)
         "source_checkpoint": None, "source_checkpoint_sha256": None,
         "extracted_sections": [], "truncated": False}
    # 1) checkpoint (verbatim, 최우선)
    if ck:
        import hashlib
        d["latest_checkpoint"] = os.path.basename(ck["path"]) + " @ " + \
            datetime.datetime.fromtimestamp(ck["mtime"]).strftime("%Y-%m-%d %H:%M")
        d["source_checkpoint"] = os.path.basename(ck["path"])
        d["source_checkpoint_sha256"] = hashlib.sha256(ck["text"].encode("utf-8")).hexdigest()
        # completed / locked_facts — 최신 블록의 명시적 라벨 섹션 bullet verbatim (섹션 없으면 빈 배열)
        _nb = newest_block(ck["text"])
        comp, comp_tr, comp_lbl = extract_labeled_bullets(_nb, COMPLETED_LABELS)
        lock, lock_tr, lock_lbl = extract_labeled_bullets(_nb, LOCKED_LABELS)
        d["completed"] = comp
        d["locked_facts"] = lock
        d["extracted_sections"] = comp_lbl + lock_lbl
        d["truncated"] = bool(comp_tr or lock_tr)
    cfrom = extract_from_checkpoint(ck)
    if cfrom.get("next_action"):
        d["next_action"] = cfrom["next_action"]; d["confidence"] = "medium"
    if cfrom.get("current_objective"):
        d["current_objective"] = cfrom["current_objective"]
    # 1-b) 관측성: checkpoint 는 있는데 구조 추출이 전무하면 파서 미스매치 의심 → needs_review
    #      (정상 공백 블록 vs 포맷 드리프트 파싱 실패를 소비자가 구분 못 하는 문제 — codex F6)
    if ck and not (d["completed"] or d["locked_facts"]
                   or cfrom.get("current_objective") or cfrom.get("next_action")):
        d["needs_review"] = True
        d["open_loops"].append("checkpoint_present_but_no_structured_extract "
                               "(format drift 의심 — 파서/헤더 포맷 확인)")
        if d["status"] == "active": d["status"] = "needs_review"
    # 2) compact_summary (objective 보충)
    cs = event.get("compact_summary")
    if cs and not d["current_objective"]:
        d["current_objective"] = mask_secrets(re.sub(r'\s+', ' ', cs)[:280]); d["confidence"] = "medium"
    # 3) runtime metadata (맥락만, 사실 아님)
    rm = read_runtime_meta(rt)
    if rm.get("prev_mode"): d["open_loops"].append("prev_mode=" + rm["prev_mode"])
    # 4) transcript tail (low-confidence, needs_review)
    if not d["next_action"]:
        hint = transcript_tail_hint(event.get("transcript_path"))
        if hint: d["open_loops"].append("last_user_hint: " + hint)
        d["needs_review"] = True; d["status"] = "needs_review"; d["confidence"] = "low"
    if not d["source_session_id"]:
        d["needs_review"] = True; d["status"] = "needs_review"
    # truncated: 10-cap(comp/lock) 또는 2KB 로 인한 list 축소를 사전 추정해 정확화
    d["truncated"] = bool(d.get("truncated")) or will_truncate_lists(d)
    return d

def _move(src, dstdir):
    """archive 하면서 masking(defense-in-depth: processed/failed 에도 raw secret 잔존 금지)."""
    dst = os.path.join(dstdir, os.path.basename(src))
    try:
        content = open(src, "r", encoding="utf-8", errors="ignore").read()
        masked = mask_secrets(content)
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(masked)
        os.replace(tmp, dst)
        os.unlink(src)
        return
    except Exception:
        pass
    try:
        os.replace(src, dst)
    except Exception:
        try: os.unlink(src)
        except Exception: pass

# ---------- main process ----------
def process(bounded=False):
    mem, rt = memory_root(), runtime_dir()
    if not rt:
        # home/project_id 해석 실패 → shared fallback 금지, advisory 종료(기존 상태 무손상)
        print(json.dumps({"status": "advisory", "reason": "runtime_unresolved"})); return 0
    qdir = os.path.join(rt, "continuity_queue")
    for d in (qdir, os.path.join(qdir, "processed"), os.path.join(qdir, "failed")):
        os.makedirs(d, exist_ok=True)
    st = load_state(rt)
    lock = acquire_lock(qdir)
    if not lock:
        st["last_status"] = "locked"; st["last_run"] = now_iso(); save_state(rt, st)
        print(json.dumps({"status": "locked"})); return 0
    result = {"processed": 0, "failed": 0, "status": "ok"}
    try:
        events = sorted(glob.glob(os.path.join(qdir, "*.json")), key=os.path.getmtime)
        mycwd, skip = cwd(), os.environ.get("CONTINUITY_SKIP_CWD_CHECK")
        my_scope = (project_id(), platform_id(), machine_id())
        valid = []
        for ep in events:
            try:
                ev = json.load(open(ep))
            except Exception:
                _move(ep, os.path.join(qdir, "failed")); result["failed"] += 1
                st.setdefault("failures", []).append(
                    {"file": os.path.basename(ep), "reason": "malformed_json", "at": now_iso()})
                continue
            if skip:
                valid.append((ep, ev)); continue
            es = (ev.get("project_id"), ev.get("platform"), ev.get("machine_id"))
            if all(x is not None for x in es):
                # scope(project_id+platform+machine_id) 일치만 처리. 불일치=다른 환경 →
                # 조용히 archive 금지. failed/quarantine 으로 격리 + 원인 기록.
                if es == my_scope:
                    valid.append((ep, ev))
                else:
                    _move(ep, os.path.join(qdir, "failed")); result["failed"] += 1
                    st.setdefault("failures", []).append(
                        {"file": os.path.basename(ep), "reason": "scope_mismatch",
                         "event_scope": {"project_id": es[0], "platform": es[1], "machine_id": es[2]},
                         "at": now_iso()})
            else:
                # legacy 이벤트(scope 필드 없음) → cwd 하위호환. 불일치도 failed 격리(조용한 archive 금지).
                if ev.get("cwd") == mycwd:
                    valid.append((ep, ev))
                else:
                    _move(ep, os.path.join(qdir, "failed")); result["failed"] += 1
                    st.setdefault("failures", []).append(
                        {"file": os.path.basename(ep), "reason": "legacy_cwd_mismatch", "at": now_iso()})
        if valid:
            # 최신 유효 이벤트만 ACTIVE_CONTEXT 를 결정(나머지는 archive)
            _, latest_ev = valid[-1]
            data = build_state(latest_ev, mem, rt)
            path, size, resid = write_active_context(mem, data)
            result["active_context"] = {"path": path, "bytes": size, "residual_secrets": resid}
            if resid > 0:
                st.setdefault("failures", []).append(
                    {"reason": "residual_secret", "count": resid, "at": now_iso()})
            for ep, _ in valid:
                _move(ep, os.path.join(qdir, "processed")); result["processed"] += 1
        st["last_status"] = result["status"]; st["last_run"] = now_iso(); st["last_result"] = result
        save_state(rt, st)
    except Exception as e:
        result["status"] = "error"
        st["last_status"] = "error"; st["last_run"] = now_iso()
        st.setdefault("failures", []).append(
            {"reason": "worker_exception", "detail": str(e)[:200], "at": now_iso()})
        save_state(rt, st)   # 기존 ACTIVE_CONTEXT/MEMORY/checkpoint 는 손대지 않음
    finally:
        release_lock(lock)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1

# ---------- stale predicate (SessionStart 주입 판단용; 이번 단계는 호출 측 미배선) ----------
def parse_active_context(mem):
    p = os.path.join(mem, "_active_context.md")
    if not os.path.isfile(p): return None
    try:
        t = open(p, encoding="utf-8").read()
        fm = {}
        m = re.search(r'^---\n(.*?)\n---', t, re.S)
        if m:
            for line in m.group(1).splitlines():
                mm = re.match(r'([a-z_]+):\s*(.*)', line)
                if mm: fm[mm.group(1)] = mm.group(2).strip().strip('"')
        fm["_path"] = p
        return fm
    except Exception:
        return None

def check_stale(mem, current_project):
    ac = parse_active_context(mem)
    if not ac: return {"inject": False, "reason": "no_active_context"}
    if ac.get("project_id") != current_project:
        return {"inject": False, "reason": "project_mismatch", "stale": True}
    if not ac.get("source_session_id") or ac.get("source_session_id") in ('""', "None", ""):
        return {"inject": True, "needs_review": True, "reason": "no_source_session"}
    ck = read_checkpoint(mem)
    if ck:
        try:
            ac_t = datetime.datetime.strptime(ac.get("updated_at", "1970-01-01T00:00:00"), "%Y-%m-%dT%H:%M:%S").timestamp()
            if ck["mtime"] > ac_t:
                return {"inject": True, "checkpoint_priority": True, "reason": "checkpoint_newer"}
        except Exception:
            pass
    if ac.get("status") in ("failed", "stale"):
        return {"inject": False, "reason": "status_" + ac.get("status")}
    return {"inject": True, "needs_review": ac.get("needs_review") in ("true", True), "reason": "ok"}

if __name__ == "__main__":
    if "--check-stale" in sys.argv:
        i = sys.argv.index("--check-stale")
        mem = sys.argv[i + 1] if len(sys.argv) > i + 1 else memory_root()
        proj = sys.argv[i + 2] if len(sys.argv) > i + 2 else sanitize(cwd())
        print(json.dumps(check_stale(mem, proj), ensure_ascii=False)); sys.exit(0)
    # --once/--latest/--bounded: 최신 유효 이벤트 1개만 ACTIVE_CONTEXT 에 반영(기본 동작과 동일, SessionStart 용)
    bounded = any(f in sys.argv for f in ("--bounded", "--once", "--latest"))
    sys.exit(process(bounded=bounded))
