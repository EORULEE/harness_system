#!/usr/bin/env python3
"""absence_claim_guard.py — 부재·위치·상태 단정의 전제 evidence 검증 (detector).

목적: 최종 응답의 검증가능한 단정(부재/위치/상태 과장)이 **직전 턴의 실제 read/search/exec
      증거**(tool-use.jsonl)에 뒷받침되는지 대조한다. 증거 없으면 would_block 기록.

설계 원칙(사용자 승인 2026-06-30):
- 기본 모드 = **report-only** (절대 차단 안 함, exit 0). would_block 만 기록.
- soft-block: advisory 강화(여전히 exit 0). hard-block: 명시 활성 카테고리만 exit 2.
- 기존 stop-guard·secret·x-agent·destructive hard gate 는 **건드리지 않음**(독립 병렬).
- 코드블록·인용·backtick span 은 단정 추출에서 제외(FP 완화).
- 증거원 = scripts/tool_use_audit.py 가 쓴 .claude/runtime/tool-use.jsonl.

카테고리(soft-block/HOLD 후보):
  A absence        부재 단정 (없다/미구현/등록 안 됨/not found)
  B location       위치 단정 (cwd/HOME/history/launch dir/경로)
  C status_overclaim  상태 과장 (session_log→live-pass·static-pass→ACTIVE·registered→authenticated·uploaded→Published)
  D release_inclusion  release 포함 여부 단정 (manifest 미확인)

사용:
  echo "<assistant text>" | python3 absence_claim_guard.py --turn <id> [--mode report|soft|hard]
  python3 absence_claim_guard.py --text-file <f> --evidence-file <ledger.json> --format json
"""
from __future__ import annotations
import json, os, re, sys, argparse, subprocess
from datetime import datetime, timezone
from pathlib import Path

THIS = Path(__file__).resolve()
try:
    sys.path.insert(0, str(THIS.parent))
    from harness_common import CLAUDE_DIR  # type: ignore
except Exception:
    CLAUDE_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude"
RUNTIME = Path(CLAUDE_DIR) / "runtime"
REPORT = RUNTIME / "absence-claim-report.jsonl"
AUDIT = THIS.parent / "tool_use_audit.py"

# ── 단정 패턴(1인칭 사실 주장; 코드/인용 제외 후 적용) ──
ABSENCE = re.compile(r"(없습니다|없다|없음|존재하지\s*않|미구현|구현\s*안|등록\s*(안\s*됨|안\s*돼|되지\s*않)|"
                     r"not\s+found|no\s+such|doesn'?t\s+exist|does\s+not\s+exist|미설치|설치\s*안\s*(됨|돼)|"
                     # Codex V1 false-negative 보강:
                     r"찾지\s*못|찾을\s*수\s*없|보이지\s*않|확인되지\s*않|누락(됨|되었|이다|입니다)|"
                     r"\bmissing\b|\babsent\b|\bunavailable\b|not\s+installed|isn'?t\s+(there|present))", re.I)
LOCATION = re.compile(r"(cwd|현재\s*(디렉터?리|폴더|작업\s*폴더|위치)|작업\s*디렉터?리|\$?HOME\b|홈\s*디렉터?리|"
                      r"launch\s*dir|실행\s*(위치|폴더|디렉터?리)|history\s*(는|에|가|파일)|"
                      r"~/\.claude/projects|경로(는|가|는요)?\s*\S+\s*(이다|입니다|임|이야))", re.I)
# Codex V1: 위치는 '단정(assertion)' 문법일 때만 — 명령형(실행하세요/set/use)은 단정 아님 → 억제.
LOC_IMPERATIVE = re.compile(r"(하세요|하라|해라|하십시오|두세요|설정\s*(하|해)|\bset\b|\buse\b|\bconfigure\b|\bcd\b|\bexport\b|바꾸|옮기)", re.I)
# 상태 과장: (강한 주장 토큰, 약한 근거/모순 토큰) — 강+약 동시 또는 강+증거없음 → would_block
STATUS_RULES = [
    ("session_log→live-pass", re.compile(r"\blive[-_ ]?pass\b|라이브\s*패스", re.I),
     re.compile(r"session[-_ ]?log|observed[-_ ]?only|session_log-only", re.I), ("verdict", "live")),
    ("static-pass→ACTIVE", re.compile(r"\bACTIVE\b|액티브", re.I),
     re.compile(r"static[-_ ]?pass|스태틱|정적\s*통과", re.I), ("verdict", "ledger", "live")),
    ("registered→authenticated", re.compile(r"authenticated|인증\s*(됨|완료|성공)|auth\s*ok", re.I),
     re.compile(r"register(ed|ing|ation)?|등록\s*(됨|완료)|registration[-_ ]?pending", re.I), ("auth", "login", "token", "connected", "인증")),
    ("uploaded→Published", re.compile(r"\bPublished\b|게시\s*(됨|완료)|발행", re.I),
     re.compile(r"upload(ed|ing)?|업로드|Published\s*OFF|published[-_ ]?off|미게시|\bOFF\b|비활성|꺼\s*있", re.I), ("publish", "게시", "public")),
]
RELEASE_INCL = re.compile(r"(release\s*(에|에는|엔)?\s*(포함|미포함|들어\s*(있|간)|빠짐)|"
                          r"릴리스\s*(에|엔)?\s*(포함|미포함)|배포(본|판)?\s*(에|엔)?\s*(포함|미포함)|"
                          r"manifest\s*(에|엔)?\s*(있|없))", re.I)

DETECTOR_VERSION = "r15-coverage"   # E. telemetry detector_version

# A. agent file ≠ valid Pair (유형5) — AGENT 토큰 + PAIR-VALID 토큰 동시 = 과장 후보
AGENT_TOKEN = re.compile(r"(c[-_]?agent|x[-_]?agent|에이전트\s*(파일|수|개수)?|agent\s*(파일|file|count|수|개수)|"
                         r"파일\s*\d+\s*개|\d+\s*개\s*(의\s*)?(에이전트|agent))", re.I)
PAIR_VALID = re.compile(r"(valid\s*pair|유효(한)?\s*(페어|pair|쌍)|페어\s*(\d+\s*쌍|유효|valid|쌍)|"
                        r"pair[-_ ]?live[-_ ]?pass|pair\s*(가|는|수)?\s*(유효|valid)|valid_pairs|\d+\s*쌍\s*유효)", re.I)
# B. deploy-readiness (유형6b)
DEPLOY_READY = re.compile(r"(배포\s*(가능|해도\s*(됨|된다|돼|되|좋)|준비\s*(완료|됨|끝)|OK)|바로\s*배포|"
                          r"release\s*준비\s*(완료|됨|끝)|current\s*에?\s*포함(됐|됨|되어|돼)|"
                          r"manifest\s*(문제\s*없|이상\s*없|\bok\b|통과)|다른\s*서버에?\s*적용\s*가능|"
                          r"deploy\s*(ready|가능)|ready\s*to\s*(deploy|ship|promote)|승격\s*가능|배포해도\s*(됨|좋))", re.I)

# 억제: 일반론·미래·조건·질문·예시 → 단정 아님(FP 완화)
SUPPRESS_SENT = re.compile(r"(보통|일반적으로|대개|예를?\s*들|might|could|would|if\b|\?$|"
                           r"없으면|없다면|없을\s*(때|경우)|있으면|확인\s*(해야|필요|할까요|할게요)|"
                           r"없는지\s*(확인|볼게|보겠)|있는지\s*(확인|볼게|보겠))", re.I)
# Codex V1: 양성(benign) "이상 없음/문제 없음/오류 없음/변경 없음/no errors" 류는 부재단정 아님 → 억제.
BENIGN_ABSENCE = re.compile(r"(문제\s*(가\s*)?없|오류\s*없|에러\s*없|이상\s*없|차이\s*없|변경\s*(사항\s*)?없|"
                            r"추가\s*(변경|작업)?\s*없|남은\s*(것|작업)?\s*없|이의\s*없|"
                            r"no\s+(errors?|issues?|problems?|changes?|action|diff|warnings?)|"
                            r"nothing\s+(to|left|wrong)|회귀\s*(가\s*)?(0|없))", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_noncommit(text: str) -> str:
    """코드펜스·인라인 backtick·blockquote 제거(단정 추출 대상에서 제외)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
    return text


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。\n])\s+|[\n]", text)
    return [s.strip() for s in parts if s.strip()]


def load_evidence(turn: str, evidence_file: str | None) -> tuple[list[dict], bool]:
    """(events, unavailable). Codex V5: 로드 실패를 '증거 없음'과 구분 — unavailable=True."""
    if evidence_file:
        try:
            d = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
            return (d.get("events", d) if isinstance(d, dict) else d), False
        except Exception:
            return [], True
    try:
        r = subprocess.run([sys.executable, str(AUDIT), "query", "--turn", turn or "",
                            *([] if turn else ["--since-current"])],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return [], True
        return json.loads(r.stdout or "{}").get("events", []), False
    except Exception:
        return [], True


def tokens_of(sentence: str) -> list[str]:
    """단정 문장에서 매칭 가능한 식별자 토큰(파일명·심볼·프로젝트명) 추출."""
    toks = re.findall(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]{3,}|[가-힣A-Za-z0-9_]{2,}", sentence)
    skip = {"없습니다", "없다", "없음", "않습니다", "그리고", "그러나", "this", "that", "there",
            "exist", "found", "registered", "authenticated", "published", "active", "static",
            "missing", "absent", "unavailable", "release", "manifest"}
    return [t for t in toks if t.lower() not in skip and len(t) >= 3][:8]


def _basename(p: str) -> str:
    return re.split(r"[\\/]", p.strip().rstrip("/"))[-1]


def event_index(events: list[dict]) -> list[dict]:
    """이벤트별 매칭 필드(target 만 — cwd 제외 = Codex V2 scoped). path/pattern/verb."""
    idx = []
    for e in events:
        t = e.get("target", {}) or {}
        paths = []
        for k in ("path", "glob", "relative_path"):
            if t.get(k):
                paths.append(str(t[k]))
        paths += [str(x) for x in (t.get("paths") or [])]
        idx.append({
            "kind": e.get("kind", ""),
            "verb": str(t.get("verb", "")).lower(),
            "paths": [p.lower() for p in paths],
            "pattern": str(t.get("pattern") or t.get("name_path") or t.get("query")
                           or t.get("substring_pattern") or "").lower(),
            "turn": str(e.get("turn", "")),
            "cwd": str(e.get("cwd", "")).lower(),
            "ts": str(e.get("ts", "")),
        })
    return idx


def scope_filter(idx: list[dict], allowed_turns: set, project_cwd: str | None) -> tuple[list[dict], dict]:
    """D. cross-turn evidence window — allowed_turns(최근 N턴) + cwd scope 만 인정.
    반환: (필터된 idx, telemetry{evidence_window_used·evidence_turn_ids·evidence_scope_match·evidence_stale})."""
    pc = (project_cwd or "").lower()
    kept, turn_ids, scope_mismatch, stale = [], set(), False, False
    for e in idx:
        # cwd scope: project_cwd 지정 시 다른 cwd evidence 거부
        if pc and e["cwd"] and e["cwd"] != pc:
            scope_mismatch = True
            continue
        # window: allowed_turns 지정 시 그 밖의 turn = stale 거부
        if allowed_turns and e["turn"] and e["turn"] not in allowed_turns:
            stale = True
            continue
        kept.append(e)
        if e["turn"]:
            turn_ids.add(e["turn"])
    tel = {
        "evidence_window_used": (len(allowed_turns) if allowed_turns else None),
        "evidence_turn_ids": sorted(turn_ids),
        "evidence_scope_match": (not scope_mismatch) if pc else None,
        "evidence_stale": stale,
    }
    return kept, tel


def claim_evidenced(toks: list[str], idx: list[dict], kinds: set) -> bool:
    """claim 토큰이 *지정 kind* 이벤트의 target path basename / search pattern 과 매칭(scoped, 부분문자열 금지)."""
    tl = [t.lower() for t in toks]
    if not tl:
        return False  # 식별 토큰 없는 막연한 단정 = 검증 불가 → 미증거(would_block)
    for e in idx:
        if e["kind"] not in kinds:
            continue
        for p in e["paths"]:
            segs = set(re.split(r"[\\/]", p)) | {_basename(p), _basename(p).split(".")[0]}
            if any(t in segs for t in tl):
                return True
        if e["pattern"] and any(t == e["pattern"] or t in e["pattern"].split() for t in tl):
            return True
    return False


def location_evidenced(idx: list[dict]) -> bool:
    """cwd/HOME/경로 단정은 명시적 pwd/getcwd/realpath/readlink/dirname 또는 LS 도구만 증거로 인정(Codex V2)."""
    LOC_VERBS = {"pwd", "getcwd", "realpath", "readlink", "dirname"}
    for e in idx:
        if e["kind"] == "list":
            return True
        if e["kind"] == "exec":
            if e["verb"] in LOC_VERBS:
                return True
            if e["verb"] == "echo" and any("home" in p or "$home" in p for p in e["paths"]):
                return True
    return False


def status_evidenced(idx: list[dict], ev_kw: tuple) -> bool:
    """상태 과장은 target(path/pattern/verb) 에 근거 키워드가 있을 때만(cwd 제외 = scoped)."""
    for e in idx:
        hay = " ".join(e["paths"]) + " " + e["pattern"] + " " + e["verb"]
        if any(k.lower() in hay for k in ev_kw):
            return True
    return False


READ_KINDS = {"read", "search", "glob", "list", "exec", "mcp-read"}


def _path_evidenced(idx: list[dict], kws: tuple) -> bool:
    """ledger 이벤트 path/pattern 에 지정 키워드(파일/디렉토리류)가 있으면 True."""
    for e in idx:
        hay = " ".join(e["paths"]) + " " + e["pattern"]
        if any(k in hay for k in kws):
            return True
    return False


def agent_pair_evidenced(idx: list[dict]) -> bool:
    """유형5 필수 evidence: PAIR_TOPOLOGY / routing / pair_router / 실제 agent 파일 read."""
    return _path_evidenced(idx, ("pair_topology", "pair-topology", "topology", "routing",
                                 "pair_router", "routing_matrix", ".claude/agents", "agents/"))


def deploy_ready_evidenced(idx: list[dict]) -> bool:
    """유형6b 필수 evidence: current release_id / manifest / deploy_gate / acceptance read."""
    return _path_evidenced(idx, ("system_release", "manifest.sha256", "manifest", "deploy_gate",
                                 "release/current", "acceptance", "preflight"))


def analyze(text: str, events: list[dict], unavailable: bool = False,
            allowed_turns: set | None = None, project_cwd: str | None = None) -> tuple[list[dict], dict]:
    clean = strip_noncommit(text)
    raw_idx = event_index(events)
    idx, window_tel = scope_filter(raw_idx, allowed_turns or set(), project_cwd)  # D. cross-turn window+scope
    findings = []

    def add(cls, sent, scoped_ok, why, hard=False, soft=False):
        ev = (not unavailable) and scoped_ok
        findings.append(_mk(cls, sent, ev, why + (" [evidence_unavailable]" if unavailable else ""),
                            hard_candidate=hard, soft_candidate=soft))

    for sent in sentences(clean):
        if SUPPRESS_SENT.search(sent):
            continue
        toks = tokens_of(sent)

        # 유형7 absence (benign 억제) — soft 후보(교차턴 window 적용됨)
        if ABSENCE.search(sent) and not BENIGN_ABSENCE.search(sent):
            add("absence", sent, claim_evidenced(toks, idx, READ_KINDS),
                "부재 단정 — read/grep/glob 증거 필요(최근 N턴 scope)", soft=True)
        # 유형8 location (명령형 억제) — soft 후보
        if LOCATION.search(sent) and not LOC_IMPERATIVE.search(sent):
            ok = location_evidenced(idx) or claim_evidenced(toks, idx, {"read", "list", "exec"})
            add("location", sent, ok, "위치 단정 — pwd/getcwd/realpath/ls 증거 필요", soft=True)
        # 유형1-4 status — C. contradiction isolation
        for name, strong, weak, ev_kw in STATUS_RULES:
            if strong.search(sent):
                contradict = bool(weak.search(sent))
                if contradict:
                    # 자기모순(강+약 동시) = FP~0 → hard_candidate=true(이번 RC는 적용 X, 플래그만)
                    add("contradiction_status_overclaim", sent, False,
                        f"상태 자기모순({name}) — 강한 상태 + 약한 진실 동시. hard 후보", hard=True)
                else:
                    # bare 단정 = evidence 없으면 soft, hard 금지
                    ok = status_evidenced(idx, ev_kw)
                    add("bare_status_overclaim", sent, ok,
                        f"상태 단정({name}) — evidence 부족. soft 후보(hard 금지)", soft=True)
        # 유형6 release_inclusion
        if RELEASE_INCL.search(sent):
            ok = deploy_ready_evidenced(idx) or claim_evidenced(toks, idx, READ_KINDS)
            add("release_inclusion", sent, ok, "release 포함 단정 — manifest/파일목록 증거 필요", soft=True)
        # 유형6b deploy_readiness (신규)
        if DEPLOY_READY.search(sent):
            add("deploy_readiness_overclaim", sent, deploy_ready_evidenced(idx),
                "배포가능 단정 — release_id/manifest/deploy_gate preflight 증거 필요")
        # 유형5 agent→valid Pair (신규)
        if AGENT_TOKEN.search(sent) and PAIR_VALID.search(sent):
            add("agent_pair_overclaim", sent, agent_pair_evidenced(idx),
                "agent 파일 존재 ≠ valid Pair — PAIR_TOPOLOGY/routing/x-write0 증거 필요")
    return findings, window_tel


# claim 텍스트(응답 발췌)를 report/stderr 에 남기기 전 secret 마스킹(통합테스트 V14 — report 유출 차단).
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{12,}|gh[opsu]_[A-Za-z0-9]{12,}|AKIA[0-9A-Z]{12,}|"
    r"Bearer\s+[A-Za-z0-9._-]{8,}|(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+)", re.I)


def _redact(s: str) -> str:
    return _SECRET_RE.sub("[REDACTED_SECRET]", s)


def _mk(cls: str, sent: str, evidenced: bool, why: str,
        hard_candidate: bool = False, soft_candidate: bool = False) -> dict:
    # category(하위호환) = 대분류, claim_class(E telemetry) = 세분류.
    coarse = {"contradiction_status_overclaim": "status_overclaim",
              "bare_status_overclaim": "status_overclaim"}.get(cls, cls)
    return {"category": coarse, "claim_class": cls, "claim": _redact(sent)[:200],
            "evidenced": bool(evidenced), "would_block": (not evidenced), "why": why,
            "hard_candidate": bool(hard_candidate), "soft_candidate": bool(soft_candidate)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file")
    ap.add_argument("--turn", default="")
    ap.add_argument("--evidence-file")
    ap.add_argument("--mode", default="report", choices=["report", "soft", "hard"])
    ap.add_argument("--hard-categories", default="",
                    help="hard 모드에서 exit2 할 카테고리(쉼표). 기본 없음(전 카테고리 report).")
    ap.add_argument("--format", default="text", choices=["text", "json"])
    # D. cross-turn window + scope
    ap.add_argument("--turns", default="", help="허용 window turn id 쉼표(최근 N턴). 비면 window 미적용")
    ap.add_argument("--window-turns", type=int, default=3, help="기본 window 크기(기록용)")
    ap.add_argument("--project-cwd", default="", help="claim scope cwd(다른 cwd evidence 거부)")
    # E. organic telemetry labeling
    ap.add_argument("--source-kind", default="unknown",
                    choices=["synthetic", "smoke", "canary", "deployment", "organic", "unknown"])
    ap.add_argument("--project-id", default="")
    ap.add_argument("--cwd-hash", default="")
    ap.add_argument("--session-id-hash", default="")
    args = ap.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else sys.stdin.read()
    events, unavailable = load_evidence(args.turn, args.evidence_file)
    allowed = {t.strip() for t in args.turns.split(",") if t.strip()}
    findings, window_tel = analyze(text, events, unavailable, allowed, args.project_cwd or None)
    blocked = [f for f in findings if f["would_block"]]

    summary = {
        "mode": args.mode, "detector_version": DETECTOR_VERSION, "turn": args.turn,
        "evidence_events": len(events), "evidence_unavailable": unavailable,
        "findings": len(findings), "would_block": len(blocked),
        # E. telemetry labels (원문 prompt/response/credential 미저장)
        "source_kind": args.source_kind,
        "project_id": args.project_id, "cwd_hash": args.cwd_hash, "session_id_hash": args.session_id_hash,
        "false_positive_label": None,
        "operator_review_needed": any(f["hard_candidate"] for f in findings),
        "hard_candidate_count": sum(1 for f in findings if f["hard_candidate"]),
        "soft_candidate_count": sum(1 for f in findings if f["soft_candidate"]),
        "evidence_window": {"window_turns": args.window_turns, **window_tel},
        "details": findings,
    }

    # 기록(report-only 라도 항상 원장에 남김)
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), **summary}, ensure_ascii=False) + "\n")
    except Exception:
        pass

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if blocked:
            print(f"⚠️ absence_claim_guard [{args.mode}]: 전제 미검증 단정 {len(blocked)}건", file=sys.stderr)
            for f in blocked[:8]:
                print(f"   [{f['category']}] {f['claim'][:90]}  → {f['why']}", file=sys.stderr)
            print("   → 근거(grep/read/search)를 제시하거나 'Unverified/확실치 않음'으로 표기.", file=sys.stderr)

    # mode 별 exit. report/soft = 항상 0(차단 안 함). hard = 지정 카테고리만 2.
    if args.mode == "hard" and args.hard_categories:
        hard = {c.strip() for c in args.hard_categories.split(",") if c.strip()}
        if any(f["would_block"] and f["category"] in hard for f in findings):
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
