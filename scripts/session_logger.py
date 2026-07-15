#!/usr/bin/env python3
"""session_logger.py — 세션 감사 로그 + 메타 블록 검증 + Stop guard.

핵심 역할
- UserPromptSubmit / PreToolUse(Task) / SubagentStop / Stop 훅 이벤트를 append-only JSONL로 기록
- 현재 턴의 mode(A0/A1/B) 힌트와 override를 런타임 상태로 유지
- 메타 블록의 참여 페어 / Task 호출 수 / iteration 주장을 실제 Task 분기 로그와 대조
- Stop hook 시점에 메타 블록과 감사 로그가 모순되면 응답을 차단

주의
- audit log는 "있었으면 하는 일"이 아니라 "실제로 있었던 일"만 기록한다.
- A0는 메타 블록이 없어야 한다.
- A1/B는 Task 분기와 메타 블록이 반드시 있어야 한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(THIS_DIR))

try:
    from harness_common import file_lock, atomic_write, now_iso, CLAUDE_DIR
except Exception:  # pragma: no cover
    CLAUDE_DIR = Path(".claude")
    from contextlib import contextmanager

    @contextmanager
    def file_lock(_path, timeout=5.0):
        yield

    def atomic_write(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")


RUNTIME_DIR = CLAUDE_DIR / "runtime"
LOG_FILE = RUNTIME_DIR / "session_log.jsonl"
CURRENT_TURN_FILE = RUNTIME_DIR / "_current_turn.txt"
PREV_MODE_FILE = RUNTIME_DIR / "_prev_mode.txt"  # Fix 3 (B2): sticky mode 이전 턴 모드 캐시

# Fix 3 (B2): Sticky mode 설정
STICKY_PROMPT_MAX_LEN = 20          # 짧은 프롬프트 기준 (글자 수)
STICKY_TTL_SECONDS = 4 * 3600       # 이전 모드 유효 시간 (4시간)

PAIR_FROM_AGENT_RE = re.compile(r"^[cx]-(?P<kind>[a-z][a-z0-9-]+)(?:\.md)?$")
PAIR_KIND_MAP = {
    "lead": "PAIR-LEAD",
    "dev": "PAIR-DEV",
    "vis": "PAIR-VIS",
    "res": "PAIR-RES",
    "qa": "PAIR-QA",
    "methods": "PAIR-METHODS",
    "domain-a": "PAIR-A",
    "domain-b": "PAIR-B",
    "domain-c": "PAIR-C",
    "a": "PAIR-A",
    "b": "PAIR-B",
    "c": "PAIR-C",
}
PAIR_LINE_RE = re.compile(r"참여\s*페어\s*:\s*(.+)")
PAIR_TOKEN_RE = re.compile(r"PAIR-[A-Z0-9-]+")
ITER_RE = re.compile(r"Iteration\s*:\s*(\d+)회")
TASK_CALLS_RE = re.compile(r"Task\s*호출\s*:\s*(\d+)회")
META_BLOCK_RE = re.compile(r"📌\s*하네스 처리 요약|참여\s*페어\s*:", re.MULTILINE)

# ── 시크릿 마스킹 (공용 모듈 secret_masking 재사용) ──
# turn-start 캡처(prompt_preview/prompt_full) 기록 전 자격증명을 마스킹한다.
# capture_worker 와 **동일 로직**을 공유(secret_masking.mask_secrets). keyfile(예:
# ~/.claude/gemini.env)의 정당한 키는 대상 아님 — 로그 복제본만 마스킹. (import 실패 시 no-op)
try:
    from secret_masking import mask_secrets as _mask_secrets
except Exception:  # pragma: no cover
    def _mask_secrets(text):
        return text


MODE_A0 = "A0"
MODE_A1 = "A1"
MODE_B = "B"
VALID_MODES = {MODE_A0, MODE_A1, MODE_B}

MODE_B_HINTS = [
    # 강한 B 신호: 파일·명시 트리거·B 동사 (단독으로 B 확정)
    "research.md", "plan.md", "계획서", "atbd",
    "구현해", "구현해줘",
    "[시작]", "[계속]", "[저장]", "[중단]",
    "진행해줘",
    "재검증", "재감사",
    "위임해",
    # 거부된 광범위 키워드: "계속", "시작", "qa", "pair-", "페어", "처리해" 등은 false positive 과다로 제외
    # (Sticky mode + user explicit set-mode 로 대응)
]
# 약한 B 명사: 단독이면 A0/A1 로 흘려보내고, **생성/작성 동사와 동반될 때만** B 로 승격.
#   (#6 수정: "논문/프로젝트/산출물/phase/campaign" 단독이 조사·상태조회를 B 로 오흡수하던 문제)
MODE_B_WEAK_NOUNS = ["논문", "초안", "산출물", "deliverable", "artifact",
                     "phase", "프로젝트", "campaign", "checkpoint"]
MODE_B_CREATE_VERBS = ["작성", "만들", "생성", "구현", "준비해", "write", "create", "draft"]

# "논문" 등 산출물 문서는 단독으론 B 아님("논문이 뭐야"=A0, "논문 조사/찾기"=A1).
#   아래 **문서 작업어**(작성·편집 계열)와 동반될 때만 B 로 승격.
#   (요청 보정: 논문 작성/초안/수정/편집/문단/양식/투고자료 → B. "수정/편집"이 기존
#    CREATE_VERBS 에 없어 "논문 수정해줘"가 A0 로 빠지던 문제를 직격.)
MODE_B_DOC_NOUNS = ["논문"]
MODE_B_DOC_WORK = ["작성", "초안", "수정", "편집", "문단", "양식", "투고",
                   "만들", "생성", "써줘", "써 줘", "쓰기"]

MODE_A1_HINTS = [
    # Fix 4 (B2): 명사 false positive 제거 — 동사형으로 제한
    "리뷰해", "검토해", "디버그해", "디버깅해",
    "bug 찾", "버그 찾", "원인 찾",
    # 기존 유지 (동사 또는 명확한 작업 지시어)
    "조사", "설계",
    # 문헌·선행연구·논문 검색은 A1(조사) — 논문 '작업어'가 아니라 '찾기/조사'이므로 B 아님
    "선행연구", "문헌", "논문 찾",
    "refactor", "compare", "experiment", "실험", "가설",
    # "비교"·"review"·"debug" 는 substring 오탐(비교적·preview·debugging) 때문에 경계매치로 이동(아래)
]
# substring 오탐 방지용 경계매치 A1 신호.
MODE_A1_BOUNDARY = [
    re.compile(r"비교(?!적)"),   # "비교"(comparison)는 매치, "비교적"(comparatively)은 제외
    re.compile(r"\breview\b"),    # "preview" 제외
    re.compile(r"\bdebug\b"),     # "debugging" 등은 디버그해/디버깅해가 커버
]


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def read_json_stdin() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


_META_BRACKET_TOKENS = ("[저장]", "[중단]", "[계속]", "[시작]", "[다음]")
_META_AFTER_MARKERS = (
    "은 ", "는 ", "이 ", "가 ", "에 대해", "에대해",
    "은?", "는?", "은\n", "는\n",
    "이 뭐", "은 뭐", "는 뭐", "이뭐",
    "이란", "라는", "이라는",
)


def _is_meta_question(prompt: str) -> bool:
    """v2.5.5: bracket + meta marker → 메타 질문 (A0 분류 대상)."""
    for b in _META_BRACKET_TOKENS:
        idx = prompt.find(b)
        if idx == -1:
            continue
        after = prompt[idx + len(b):]
        if any(after.startswith(m) for m in _META_AFTER_MARKERS):
            return True
    return False


def classify_mode(prompt: str) -> str:
    p = (prompt or "").lower()
    # 2026-07-02: 명시 모드 라벨(A0:/A1:/B:/C:) — 사용자 명시 선언은 휴리스틱·메타질문 판정보다 우선.
    #   mode-label-advisory.mjs 와 동일 정규식 계열. C(자율 실험 루프)는 경계 판단이 A1급 검증 대상이라 A1 매핑.
    _lbl = re.match(r"^\s*[>*_`\-\s]{0,4}(a0|a1|b|c)\s*[:：]", p)
    if _lbl:
        return {"a0": MODE_A0, "a1": MODE_A1, "b": MODE_B, "c": MODE_A1}[_lbl.group(1)]
    # v2.5.5: bracket meta question 은 B 트리거에 우선해서 A0 처리
    if _is_meta_question(prompt or ""):
        return MODE_A0
    # 강한 B 신호
    if any(k in p for k in MODE_B_HINTS):
        return MODE_B
    # 약한 B 명사는 생성/작성 동사와 동반될 때만 B (#6: 단독 명사의 B 오흡수 차단)
    if any(n in p for n in MODE_B_WEAK_NOUNS) and any(v in p for v in MODE_B_CREATE_VERBS):
        return MODE_B
    # "논문" + 문서 작업어(작성/초안/수정/편집/문단/양식/투고) 조합만 B.
    #   "논문" 단독·"논문 조사/찾기"는 아래 A1 로 흐름(이 검사는 작업어가 있을 때만 발동).
    if any(n in p for n in MODE_B_DOC_NOUNS) and any(w in p for w in MODE_B_DOC_WORK):
        return MODE_B
    # A1 (substring 신호 + 경계매치 신호)
    if any(k in p for k in MODE_A1_HINTS):
        return MODE_A1
    if any(rx.search(p) for rx in MODE_A1_BOUNDARY):
        return MODE_A1
    return MODE_A0


def read_current_turn() -> str | None:
    if not CURRENT_TURN_FILE.exists():
        return None
    content = CURRENT_TURN_FILE.read_text(encoding="utf-8").strip()
    return content or None


def set_current_turn(turn_id: str) -> None:
    ensure_runtime()
    atomic_write(CURRENT_TURN_FILE, turn_id)


def clear_current_turn() -> None:
    if CURRENT_TURN_FILE.exists():
        CURRENT_TURN_FILE.unlink()


def append_event(event: str, payload: dict[str, Any], turn_id: str | None = None) -> None:
    ensure_runtime()
    if turn_id is None:
        turn_id = read_current_turn() or "no-turn"
    record = {"ts": now_iso(), "turn": turn_id, "event": event, "payload": payload}
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with file_lock(LOG_FILE, timeout=3.0):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)


def extract_pair_from_agent_id(agent_id: str) -> str:
    m = PAIR_FROM_AGENT_RE.match(agent_id)
    if not m:
        return agent_id
    kind = m.group("kind")
    return PAIR_KIND_MAP.get(kind, f"PAIR-{kind.upper()}")


def _read_prev_mode() -> tuple[str | None, bool]:
    """Fix 3 (B2): 이전 턴 모드를 읽어 sticky 후보 반환. TTL 초과 시 무효.

    Returns:
        (mode, is_valid): mode 는 "A0"/"A1"/"B" 중 하나 또는 None.
        is_valid 는 TTL 범위 내면 True.
    """
    if not PREV_MODE_FILE.exists():
        return None, False
    try:
        content = PREV_MODE_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return None, False
        # 형식: "MODE|ISO_TIMESTAMP" (예: "A1|2026-04-20T14:30:05")
        parts = content.split("|", 1)
        if len(parts) != 2:
            return None, False
        mode, ts_str = parts
        if mode not in VALID_MODES:
            return None, False
        # TTL 체크
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(ts_str)
            age = (datetime.now() - ts).total_seconds()
            if age > STICKY_TTL_SECONDS:
                return mode, False
            return mode, True
        except Exception:
            return mode, False
    except Exception:
        return None, False


def _write_prev_mode(mode: str) -> None:
    """Fix 3 (B2): 현재 턴 종료 시 mode 저장."""
    if mode not in VALID_MODES:
        return
    try:
        ensure_runtime()
        atomic_write(PREV_MODE_FILE, f"{mode}|{datetime.now().isoformat(timespec='seconds')}")
    except Exception:
        pass


def cmd_turn_start() -> None:
    data = read_json_stdin()
    prompt = data.get("prompt", "") or data.get("user_prompt", "")
    prompt_str = str(prompt)
    mode_hint = data.get("mode_hint") or classify_mode(prompt_str)
    if mode_hint not in VALID_MODES:
        mode_hint = classify_mode(prompt_str)

    # Fix 3 (B2): Sticky mode — 짧은 프롬프트가 기본 A0 로 분류되면 이전 턴의 A1/B 를 상속
    stickied = False
    sticky_source = None
    if mode_hint == MODE_A0 and len(prompt_str.strip()) <= STICKY_PROMPT_MAX_LEN:
        prev_mode, prev_valid = _read_prev_mode()
        if prev_valid and prev_mode in (MODE_A1, MODE_B):
            mode_hint = prev_mode
            stickied = True
            sticky_source = prev_mode

    turn_id = f"turn-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    set_current_turn(turn_id)
    # 기록 전 시크릿 마스킹 — 트리거([계속] 등)·모드분류는 위에서 원문으로 이미 처리됨.
    masked = _mask_secrets(prompt_str)
    payload = {
        "prompt_length": len(prompt),
        "prompt_preview": masked[:200],
        # v2.5.4 (M1 fix): bracket trigger endswith 검사용. preview 200자 절단으로
        # 긴 프롬프트 끝의 [계속] 누락 방지. 4000자 상한 (privacy/storage 균형).
        "prompt_full": masked[:4000],
        "mode_hint": mode_hint,
    }
    if stickied:
        payload["sticky_inherited"] = True
        payload["sticky_source"] = sticky_source
    append_event("turn-start", payload, turn_id=turn_id)


def cmd_set_mode(args) -> None:
    mode = args.mode
    if mode not in VALID_MODES:
        sys.stderr.write(f"❌ 지원하지 않는 mode: {mode}\n")
        sys.exit(1)
    append_event("mode-override", {"mode": mode})


def cmd_task_call() -> None:
    data = read_json_stdin()
    tool_input = data.get("tool_input", {}) or {}
    subagent_type = str(tool_input.get("subagent_type", "unknown"))
    append_event("task-call", {"subagent_type": subagent_type, "pair_inferred": extract_pair_from_agent_id(subagent_type), "description": (tool_input.get("description") or "")[:200]})


def cmd_task_end() -> None:
    data = read_json_stdin()
    append_event("task-end", {"transcript_path": data.get("transcript_path"), "stop_hook_active": data.get("stop_hook_active", False)})


def cmd_subagent_audit() -> None:
    data = read_json_stdin()
    if data:
        append_event("subagent-audit", data)


def cmd_turn_end(args) -> None:
    data = read_json_stdin()
    turn_id = read_current_turn() or "no-turn"
    append_event("turn-end", {"stop_hook_active": data.get("stop_hook_active", False), "guard_exit": int(getattr(args, "guard_exit", 0) or 0)}, turn_id=turn_id)
    # Fix 3 (B2): Sticky mode — 이번 턴의 effective_mode 를 다음 턴 상속용으로 저장
    try:
        if turn_id and turn_id != "no-turn":
            summary = summarize_turn(turn_id)
            effective_mode = summary.get("effective_mode")
            if effective_mode in VALID_MODES:
                _write_prev_mode(effective_mode)
    except Exception:
        pass
    clear_current_turn()


def _iter_log_events() -> list[dict[str, Any]]:
    if not LOG_FILE.exists():
        return []
    events = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def read_turn_events(turn_id: str) -> list[dict[str, Any]]:
    return [e for e in _iter_log_events() if e.get("turn") == turn_id]


def summarize_turn(turn_id: str) -> dict[str, Any]:
    events = read_turn_events(turn_id)
    task_calls = [e for e in events if e.get("event") == "task-call"]
    task_ends = [e for e in events if e.get("event") == "task-end"]
    audits = [e for e in events if e.get("event") == "subagent-audit"]
    pairs = sorted({e.get("payload", {}).get("pair_inferred", "?") for e in task_calls})
    started = next((e for e in events if e.get("event") == "turn-start"), None)
    ended = next((e for e in events if e.get("event") == "turn-end"), None)
    mode_overrides = [e for e in events if e.get("event") == "mode-override"]
    started_payload = (started or {}).get("payload", {}) if started else {}
    mode_hint = started_payload.get("mode_hint")
    mode_override = mode_overrides[-1]["payload"].get("mode") if mode_overrides else None
    effective_mode = mode_override or mode_hint or MODE_A0
    return {
        "turn_id": turn_id,
        "started_at": started.get("ts") if started else None,
        "ended_at": ended.get("ts") if ended else None,
        "task_calls": len(task_calls),
        "task_ends": len(task_ends),
        "pairs_seen": pairs,
        "mode_hint": mode_hint,
        "mode_override": mode_override,
        "effective_mode": effective_mode,
        "subagent_audits": len(audits),
        "is_closed": ended is not None,
        # v2.5.4: 트리거 매칭·sticky chain 해제 판단을 위한 메타 노출
        "sticky_inherited": bool(started_payload.get("sticky_inherited", False)),
        "prompt_length": int(started_payload.get("prompt_length", 0) or 0),
        "prompt_preview": started_payload.get("prompt_preview", ""),
        # v2.5.4 (M1 fix): bracket trigger endswith 검사용 full prompt (4000자)
        "prompt_full": started_payload.get("prompt_full", ""),
    }


def summarize_recent(n: int) -> dict[str, Any]:
    """최근 N개 turn 의 task-call/pair 집계. 비동기 서브에이전트 완료가 별도 알림 턴으로 와서
    현재 턴엔 task-call 이 0 이어도, 직전 spawn 턴의 페어 증거를 정직하게 인용할 수 있게 한다."""
    events = _iter_log_events()
    seen: list[str] = []
    for e in events:
        t = e.get("turn")
        if t and t != "no-turn" and t not in seen:
            seen.append(t)
    recent = seen[-n:] if n > 0 else seen
    rset = set(recent)
    tcs = [e for e in events if e.get("event") == "task-call" and e.get("turn") in rset]
    pairs = sorted({e.get("payload", {}).get("pair_inferred", "?") for e in tcs})
    return {
        "turns_scanned": recent,
        "task_calls": len(tcs),
        "pairs_seen": pairs,
        "note": f"최근 {len(recent)}개 턴 집계 (비동기 페어 완료가 별도 알림 턴으로 온 경우 포함).",
    }


def cmd_verify(args) -> None:
    if getattr(args, "recent", 0):
        result = summarize_recent(args.recent)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2)) ; return
        print(f"━━━ 최근 {len(result['turns_scanned'])}개 턴 집계 ━━━")
        print(f"  Task 호출:     {result['task_calls']}회")
        print(f"  관찰된 페어:    {result['pairs_seen']}")
        print(f"  💡 {result['note']}")
        return
    turn_id = args.turn or read_current_turn()
    if not turn_id:
        result = {"turn_id": None, "task_calls": 0, "pairs_seen": [], "warning": "현재 턴에 등록된 turn 이 없음. (이 verify 가 spawn 턴이 아닌 후속/알림 턴에서, 또는 spawn 전에 실행됐을 수 있음. 비동기 서브에이전트 완료는 별도 알림 턴으로 옴 → `verify --turn <spawn-turn>` 또는 `verify --recent N` 으로 직전 spawn 턴을 확인하라. UPS 훅 배선이 정상이어도 발생할 수 있음.)"}
    else:
        result = summarize_turn(turn_id)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"━━━ 턴 감사 요약: {result.get('turn_id', '(없음)')} ━━━")
    if "warning" in result:
        print(f"  ⚠️  {result['warning']}")
        return
    print(f"  시작:          {result['started_at']}")
    print(f"  종료:          {result['ended_at'] or '(진행 중)'}")
    print(f"  mode:         {result.get('effective_mode', '-')}")
    print(f"  Task 호출:     {result['task_calls']}회")
    print(f"  Task 완료:     {result['task_ends']}회")
    print(f"  관찰된 페어:    {result['pairs_seen']}")
    if result["task_calls"] == 0:
        print() ; print("  💡 이 턴에 task-call 이 없습니다. (비동기 페어는 직전 spawn 턴에 있을 수 있음 → `verify --recent 3` 확인)")
        print("     → 직전 spawn 턴에도 task-call 이 0 이면, 메타 블록의 '참여 페어' 주장은 허위 준수입니다.")
        print("     → A0 모드라면 메타 블록 자체를 생략하세요.")


def _collect_strings(obj: Any, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out)


def _extract_assistant_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    _collect_strings(payload, texts)
    best = ""
    for t in texts:
        if META_BLOCK_RE.search(t) and len(t) > len(best):
            best = t
    return best or (max(texts, key=len) if texts else "")


def _parse_claimed_pairs(text: str) -> list[str]:
    line_match = PAIR_LINE_RE.search(text)
    if not line_match:
        return []
    return sorted(set(PAIR_TOKEN_RE.findall(line_match.group(1))))


def _parse_claimed_iteration(text: str) -> int | None:
    m = ITER_RE.search(text)
    return int(m.group(1)) if m else None


def _parse_claimed_task_calls(text: str) -> int | None:
    m = TASK_CALLS_RE.search(text)
    return int(m.group(1)) if m else None


def _has_cx_pairs() -> bool:
    """프로젝트에 c-*/x-* 에이전트 페어가 존재하는지. 둘 다 있어야 2-pass 가능.

    없으면 글로벌 규율상 1-pass 프로젝트 → 2-pass(페어 호출) 강제 부적용.
    (CLAUDE.md: "페어가 없는 프로젝트는 1-pass 유지")
    """
    agents = CLAUDE_DIR / "agents"
    try:
        has_c = any(agents.glob("c-*.md"))
        has_x = any(agents.glob("x-*.md"))
    except OSError:
        return False
    return has_c and has_x


def _is_background_inflight(payload: dict[str, Any]) -> bool:
    """Stop payload 의 background_tasks 가 비어있지 않으면 = **작업 진행 중(in-flight) 대기 Stop**.
    ⚠️ 실측(canary): background_tasks 는 작업 *진행 중('running')* 일 때만 채워지고, **완료 notification
    턴에는 비어 있다**. 따라서 이 신호는 '완료 notification' 식별이 아니라 'in-flight 대기' 라벨 전용이다.
    완료 notification 식별은 _is_completed_task_notification(transcript) 가 담당(역할 분리).
    필드 부재(구버전)·빈 배열 → False (no-op, 회귀 0)."""
    try:
        bt = payload.get("background_tasks")
        return isinstance(bt, list) and len(bt) > 0
    except Exception:
        return False


# 완료 notification 의 실관측 status (canary: completed·killed; 명세 허용: + failed·stopped)
_NOTIF_DONE_STATUS = {"completed", "failed", "killed", "stopped"}


def _read_transcript_tail(path: str, max_bytes: int = 65536, max_records: int = 50) -> list[dict]:
    """transcript_path 의 *마지막 제한 구간만* 읽어 JSONL 레코드(최대 max_records) 반환.
    전체 파일 미적재(최대 64KB 또는 마지막 50 레코드). 없음/손상/대용량 → 안전하게 부분/[] 반환."""
    try:
        import os
        if not path or not os.path.isfile(path):
            return []
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # 잘린 첫 라인 폐기
            tail = f.read().decode("utf-8", "ignore")
        recs = []
        for line in tail.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue  # 부분/손상 라인 skip
        return recs[-max_records:]
    except Exception:
        return []


def _nb_el(name: str, txt: str):
    import re as _re
    mm = _re.search(rf"<{name}>(.*?)</{name}>", txt or "", _re.S)
    return mm.group(1).strip() if mm else None


def _is_completed_task_notification(payload: dict[str, Any], current_prompt=None) -> tuple[bool, str, str]:
    """Stop payload.transcript_path 의 bounded tail 에서, 이번 턴을 트리거한 최신 user 레코드가
    *구조화된 완료 task notification* 인지 판정. (실측 STEP1: 완료 notification 은 fresh turn-start 로 전달됨)
      - 트리거 = tail 역방향 최초의 promptSource 보유 user 레코드(tool_result 는 promptSource 부재 → skip).
      - **spoof 방지**: 트리거의 promptSource == 'system' 필수. 사용자 입력은 'queued'/부재라 위조 불가.
      - 블록: content(str) 가 '<task-notification>' 로 시작 + task-id·status·summary 보유, status∈완료군.
      - **현재 turn 동일성**: current_prompt 주어지면(=fresh turn) 그 prompt 도 동일 task-id+status 의
        notification 블록이어야 함(현재 turn 이 곧 그 notification 임을 확정 — 과거 notification 오재사용 방지).
        current_prompt=None(=null turn) 이면 transcript 트리거만으로 판정.
      - transcript 부재/손상/판별불가 → (False,...) → 기존 동작 유지(추정 금지).
    transcript 내용은 로그에 저장하지 않음. 반환: (is_notif, status, task_id_sha8)."""
    import hashlib
    try:
        recs = _read_transcript_tail(payload.get("transcript_path"))
        if not recs:
            return (False, "", "")
        trigger = None
        for r in reversed(recs):
            m = r.get("message")
            if (r.get("type") == "user" and isinstance(m, dict) and m.get("role") == "user"
                    and r.get("promptSource")):           # promptSource 보유 = 턴 트리거(tool_result 아님)
                trigger = r
                break
        if trigger is None or trigger.get("promptSource") != "system":
            return (False, "", "")                        # 사용자('queued')/부재 → notification 아님(spoof 차단)
        c = trigger.get("message", {}).get("content")
        if not isinstance(c, str):
            return (False, "", "")
        cs = c.strip()
        if not cs.startswith("<task-notification>"):
            return (False, "", "")
        tid, status, summary = _nb_el("task-id", cs), _nb_el("status", cs), _nb_el("summary", cs)
        if not (tid and status and summary):
            return (False, "", "")
        if status not in _NOTIF_DONE_STATUS:
            return (False, "", "")
        # fresh turn 동일성: 현재 turn prompt 의 task-id+status 가 transcript notification 과 일치해야 함.
        if current_prompt is not None:
            cp = str(current_prompt).strip()
            if not cp.startswith("<task-notification>"):
                return (False, "", "")
            if _nb_el("task-id", cp) != tid or _nb_el("status", cp) != status:
                return (False, "", "")
        return (True, status, hashlib.sha256(tid.encode("utf-8")).hexdigest()[:8])
    except Exception:
        return (False, "", "")


def cmd_stop_guard() -> None:
    """v2.5.4: B/A1 의 task=0, 메타 블록 누락, 허위 주장을 모두 BLOCKING.

    이전 v2.5.1_B2_HYBRID 는 형식 검사를 advisory(exit 0)로 두었으나, 결과적으로
    "토큰 비용 압박 시 퇴보 → B 모드인데 task 분기 0회" 같은 허위 준수가 빈발.
    v2.5.4 는 모든 치명 위반을 exit(2)로 격상하고, 정상 대화 패턴이 차단되지 않도록
    트리거 분류 (workflow / admin / true_conv) + retry detection 으로 false positive 방어.
    """
    payload = read_json_stdin()
    assistant_text = _extract_assistant_text(payload)
    has_meta = bool(assistant_text and META_BLOCK_RE.search(assistant_text))
    is_bg_inflight = _is_background_inflight(payload)           # 작업 진행 중(in-flight) 대기 — 완료 notification 아님
    turn_id = read_current_turn()
    summary = summarize_turn(turn_id) if turn_id else None
    cur_prompt = summary.get("prompt_full") if summary else None   # 현재 turn 프롬프트(turn-start 기록)
    is_notif, notif_status, notif_hash = _is_completed_task_notification(payload, current_prompt=cur_prompt)

    # ── 완료 task notification carve-out (transcript promptSource=='system' + 현재 turn 동일성) ──
    # 실측: 완료 notification 은 fresh turn-start(prompt=<task-notification>)로 전달됨 → fresh/closed 무관 인정.
    # spoof 차단: 사용자 입력은 promptSource='queued' → detector False(우회 불가).
    # 직전 turn 의 task_calls/mode/pairs 미귀속, 현재 notification turn 의 task_calls=0 을 B 누락으로 보지 않음.
    if is_notif:
        append_event("guard-decision", {
            "result": "task-notification-advisory", "status": notif_status,
            "task_id_sha8": notif_hash, "turn_id": turn_id,
            "turn_closed": bool(summary and summary.get("is_closed")),
        }, turn_id="bgprobe")
        sys.stderr.write(
            f"ℹ️  Stop guard: 완료 task notification turn (status={notif_status}, task#{notif_hash}) — "
            "검증 스킵(platform notification·이전 turn task_calls/mode/pairs 미귀속).\n"
        )
        sys.exit(0)

    if not turn_id:
        # v2.4.7+ (S3 이슈): 설치 직후 또는 SessionStart 미실행 상태에서는 turn 추적 불가.
        # exit 2 면 새 턴 트리거 → 다시 Stop → 무한 루프 → graceful degrade(exit 0).
        if is_bg_inflight:
            sys.stderr.write(
                "ℹ️  Stop guard: background 작업 진행 중(in-flight) 대기 Stop · turn 미추적 — 검증 스킵.\n"
            )
        else:
            sys.stderr.write(
                "ℹ️  Stop guard: 현재 턴 미추적 — 검증 스킵 "
                "(설치 직후 또는 SessionStart 미실행 상태)\n"
            )
        sys.exit(0)
    # 여기 도달 = turn_id 존재(summary 위에서 계산됨).
    mode = summary.get("effective_mode", MODE_A0)
    task_calls = int(summary["task_calls"])
    actual_pairs = set(summary["pairs_seen"])

    # A0 모드: Task 분기·메타 블록 위반은 advisory 유지 (A0 허용 범위 느슨)
    if mode == MODE_A0:
        if task_calls > 0:
            sys.stderr.write(f"⚠️ Stop guard (advisory): A0인데 Task 분기 {task_calls}회가 있었습니다.\n")
            sys.exit(0)
        if has_meta:
            sys.stderr.write("⚠️ Stop guard (advisory): A0 응답에 메타 블록이 있습니다.\n")
            sys.exit(0)
        return

    # ── v2.5.4 트리거 분류 (false positive 방어) ──
    preview = str(summary.get("prompt_preview", "")).strip()

    # B 워크플로우 진행 트리거: B 유지, task=0 시 차단 (STEP 팬아웃 강제)
    _B_WORKFLOW_TRIGGERS = {
        "[계속]", "[시작]", "[다음]",
        "계속", "시작", "다음", "go", "start",
    }
    # B 행정 관리 트리거: B 유지, task=0 허용 (campaign_manager 호출만 허용)
    _B_ADMIN_TRIGGERS = {
        "[저장]", "[중단]",
        "저장", "중단", "stop", "save", "checkpoint",
    }
    # 순수 대화형: A0 강등 + sticky 해제
    _TRUE_CONVERSATIONAL = {
        "고마워", "감사", "감사합니다", "ok", "OK", "응", "그래",
        "넵", "네", "좋아", "알겠어", "ㅇㅋ",
    }

    # v2.5.5 (Option A): bracket 부분 매칭 (어디든) + meta-question pattern 예외.
    # 한국어 자연 발화: "이제 [저장]하고 ...", "그러면 [계속]하고 ..." 처럼
    # 부사·접속사가 트리거 앞에 옴. anchor 만으로는 매칭 실패 → false negative 다발.
    # 대신 bracket 뒤 패턴으로 admin/meta 구분:
    #   - 뒤에 "은", "는", "이", "가", "에 대해", "은 뭐", "는 뭐" → meta question (A0)
    #   - 그 외 (하고, 해줘, 후, 도, 공백+동사 등) → admin/workflow intent
    full_prompt = str(summary.get("prompt_full", "")).strip() or preview

    # Meta-question 마커 — bracket 뒤에 이런 패턴이 오면 트리거 매칭 제외
    _META_QUESTION_AFTER = (
        "은 ", "는 ", "이 ", "가 ",
        "은\n", "는\n", "이\n", "가\n",
        "에 대해", "에대해",
        "은?", "는?", "이?", "가?",
        "이 뭐", "은 뭐", "는 뭐", "이뭐",
        "이란", "라는", "이라는",
    )

    def _matches_trigger(text_preview: str, text_full: str, trigger_set: set) -> bool:
        """Bracket: anywhere in prompt with meta-question 예외. Bare: exact (case-insensitive)."""
        ts_preview = text_preview.strip()
        ts_full = text_full.strip()
        ts_norm = ts_preview.lower()
        bracket_subset = {t for t in trigger_set if t.startswith("[") and t.endswith("]")}
        bare_subset = trigger_set - bracket_subset
        # Bracket: 부분 매칭 + meta-question 예외
        search_text = ts_full or ts_preview
        for t in bracket_subset:
            idx = search_text.find(t)
            if idx == -1:
                continue
            after = search_text[idx + len(t):]
            is_meta = any(after.startswith(p) for p in _META_QUESTION_AFTER)
            if not is_meta:
                return True
        # Bare: preview 완전 일치 (대소문자 무시) — false positive ("재저장소") 방지
        if ts_preview in bare_subset or ts_norm in {t.lower() for t in bare_subset}:
            return True
        return False

    is_b_admin = _matches_trigger(preview, full_prompt, _B_ADMIN_TRIGGERS)
    is_b_workflow = _matches_trigger(preview, full_prompt, _B_WORKFLOW_TRIGGERS)
    is_true_conv = _matches_trigger(preview, full_prompt, _TRUE_CONVERSATIONAL)
    # (2026-06-10 포렌식 ①수정) 진행/승인/조종/빠른확인 = 새 c-/x- 팬아웃 불필요 turn.
    #   forensic(this-project 11/11 · coin 65/67 차단이 이 범주): A1/B 키워드는 있으나 실제론
    #   진행지시·승인·조종·단순확인이라 2-pass 강제가 오발화. substring 매칭(긴 프롬프트 내 포함도 인정).
    _LIGHT_STEER_SUBSTR = (
        # 진행/계속/이어서
        "진행해", "계속 진행", "계속해서 진행", "그대로 진행", "이어서 진행", "계속해줘",
        # 승인/선택/순서/번호
        "권장", "순서로 진행", "순서로 해", "번으로 해", "번으로 진행", "번으로 가", "번으로",
        "대로 해", "대로 진행", "대로 가", "로 처리해", "처리해줘", "로 진행해", "로 해서", "로 해줘",
        # 빠른 확인/비교/검토 (단순 조회성)
        "다시 확인", "재확인", "맞는지 확인", "왜 다른", "어떻게 달라", "동일한지", "비교해", "검토해봐",
        # 조회/상태/알림성 (팬아웃 불필요) — status 질의.
        # (완료 task notification 의 문자열 매치는 제거: spoofable. → _is_completed_task_notification 로 promptSource=system 검증)
        "알려줘", "보여줘", "보고싶", "현황", "상황도", "어디까지",
    )
    _full_lower = (full_prompt or preview or "").lower()
    is_light_steer = any(k in _full_lower for k in _LIGHT_STEER_SUBSTR)

    # Stop hook feedback 재진입 탐지 — Claude Code 재시도 시 무한 루프 방지
    is_retry_from_block = (
        "Stop hook feedback" in preview
        or "Stop guard" in preview
        or preview.startswith("❌ Stop")
    )

    # 분기 순서: retry → conv → admin(workflow 아닌 경우만) → 그 외 task=0 차단
    # workflow 가 admin 보다 우선인 이유: "[계속]하고 [저장]도" 시 STEP 팬아웃 강제

    # (1) Stop hook feedback 재진입 → 무한 루프 방지 (최우선)
    if task_calls == 0 and is_retry_from_block:
        sys.stderr.write(
            "ℹ️  Stop guard: Stop hook feedback 재진입 탐지 — "
            "무한 루프 방지 위해 통과 (sticky 해제, 다음 턴 재평가)\n"
        )
        _write_prev_mode(MODE_A0)
        sys.exit(0)

    # (2) 순수 대화형 → A0 강등 + sticky 해제
    if task_calls == 0 and is_true_conv:
        sys.stderr.write(
            f"ℹ️  Stop guard: 순수 대화형('{preview[:30]}') → A0 자동 강등\n"
        )
        _write_prev_mode(MODE_A0)
        sys.exit(0)

    # (3) admin 단독 (workflow 안 잡힘) → B 유지, task=0 허용
    if task_calls == 0 and is_b_admin and not is_b_workflow:
        sys.stderr.write(
            f"ℹ️  Stop guard: B 행정 트리거('{preview[:30]}') 통과 "
            "(sticky B 보존, 다음 [계속]에서 워크플로우 복귀)\n"
        )
        sys.exit(0)

    # (3.7) c-/x- 페어가 없는 프로젝트 = 1-pass (글로벌 규율). 2-pass 강제 부적용 → advisory.
    #   페어 보유 프로젝트(00_KMA 등)는 _has_cx_pairs()=True 라 이 분기 미적용 → 기존대로 차단.
    if task_calls == 0 and not _has_cx_pairs():
        sys.stderr.write(
            f"ℹ️  Stop guard (advisory): {mode} 작업이나 이 프로젝트에 c-*/x-* 페어가 없어 "
            "1-pass 유지 (글로벌 규율 '페어 없는 프로젝트는 1-pass'). 2-pass 강제 스킵 — "
            "메타 블록의 페어/Task 주장은 생략하세요.\n"
        )
        sys.exit(0)

    # (3.8 NEW 2026-06-10, 포렌식 ①수정) 진행/승인/조종/빠른확인/워크플로우-계속 = 2-pass 불필요 → advisory.
    #   블록 캐스케이드(task=0·A1<2·메타블록) *앞에서* 한 번에 면제. 차단의 97~100%(forensic)가 이 범주였음.
    #   필요한 실제 분석은 "진행"이 가리키는 작업 step에서 수행됨(이 steering turn 자체는 팬아웃 불필요).
    if is_light_steer or (task_calls == 0 and is_b_workflow):
        sys.stderr.write(
            f"ℹ️  Stop guard (advisory): 진행/승인/조종/확인 turn('{preview[:30]}') — "
            "c-/x- 2-pass 강제 스킵(필요 시 실제 작업 step에서 수행). 메타 블록 페어/Task 주장 생략 가능.\n"
        )
        sys.exit(0)

    # (3.9 NEW 2026-06-10) A1 팬아웃 부족(task<2) = advisory (hard-block 제거).
    #   forensic: A1 hard-block은 100% false positive(조사·검토·비교·확인 turn). 키워드론 "심층분석(2-pass 필요)"
    #   과 "빠른 조회"를 구분 불가 → A1은 advisory(경고)로 강등, 사용자 실시간 감독으로 대체. (B/메타-허위주장은 hard 유지)
    if mode == MODE_A1 and task_calls < 2 and _has_cx_pairs():
        sys.stderr.write(
            f"ℹ️  Stop guard (advisory): A1 Task {task_calls}회(c-/x- 페어 2회 미만) — 통과. "
            "심층 분석이면 c-*/x-* 교차검증 권장(연구는 research-agent 1회로 충분).\n"
        )
        sys.exit(0)

    # (4) 그 외 task=0 (workflow trigger 포함) → BLOCKING
    if task_calls == 0:
        sys.stderr.write(
            f"❌ Stop guard: {mode}인데 Task 분기가 0회.\n"
            "⚡ 자동 복구 지시: 지금 즉시 관련 c-*/x-* 페어를 Task 도구로 호출하여 "
            "실제 분석을 수행하세요. 완료 후 `python3 scripts/session_logger.py verify --format json` "
            "결과의 task_calls와 pairs_seen을 메타 블록에 그대로 기재하세요. "
            "Task 호출 없이 메타 블록만 수정하는 것은 허위 준수입니다.\n"
        )
        sys.exit(2)

    # A1 2-pass 최소 강제: c-/x- 쌍 = 2회 호출 필수 (페어 있는 프로젝트만)
    #   (task=1 은 위 (3.9)에서 advisory 처리됨 → 여기 도달 시 task=0 케이스는 (4)서 이미 처리)
    if mode == MODE_A1 and task_calls < 2 and _has_cx_pairs():
        sys.stderr.write(
            f"❌ Stop guard: A1 인데 Task 호출 {task_calls}회.\n"
            "⚡ 자동 복구 지시: A1 2-pass는 최소 c-*(1회) + x-*(1회) 쌍 호출이 필수입니다. "
            "지금 즉시 누락된 x-* 페어를 Task 도구로 호출하여 교차검증하세요. "
            "완료 후 verify 결과로 메타 블록을 작성하세요.\n"
        )
        sys.exit(2)

    # B 모드에서 단일 페어로만 호출 — 경고 (차단 안 함, PAIR-LEAD 단독 정당 케이스 존재)
    if len(actual_pairs) == 1 and task_calls >= 2 and mode == MODE_B:
        sys.stderr.write(
            f"⚠️ Stop guard: B 모드인데 참여 페어가 1개뿐 ({sorted(actual_pairs)}). "
            "다중 페어 권장.\n"
        )

    # 메타 블록 검증 (허위 준수 차단) — 모두 BLOCKING + 자동 복구 지시
    if not has_meta:
        sys.stderr.write(
            f"❌ Stop guard: {mode}인데 메타 블록이 없습니다.\n"
            "⚡ 자동 복구 지시: `python3 scripts/session_logger.py verify --format json` 실행 후 "
            "결과의 task_calls, pairs_seen 값을 메타 블록에 그대로 기재하여 응답 끝에 추가하세요.\n"
        )
        sys.exit(2)
    claimed_pairs = _parse_claimed_pairs(assistant_text)
    claimed_iteration = _parse_claimed_iteration(assistant_text)
    claimed_task_calls = _parse_claimed_task_calls(assistant_text)
    if not claimed_pairs:
        # (2026-06-12 카브아웃, 사용자 승인) 페어 미보유 프로젝트는 PAIR-토큰을 정직하게
        # 쓸 방법이 없음("참여 페어: 없음" → 토큰 0 → 차단 / 가짜 토큰 → 허위주장 차단 = catch-22).
        # A1의 _has_cx_pairs() 기준과 동일하게 — 페어 보유 프로젝트만 강제, 미보유는 advisory.
        if not _has_cx_pairs():
            sys.stderr.write(
                "⚠️ Stop guard (advisory): 페어 미보유 프로젝트 — '참여 페어' PAIR-토큰 검증 생략 "
                "(task_calls/메타 정합 검증은 계속 적용).\n"
            )
        else:
            sys.stderr.write(
                "❌ Stop guard: 메타 블록에 '참여 페어:' 라인이 없습니다.\n"
                "⚡ 자동 복구 지시: `python3 scripts/session_logger.py verify --format json` 실행 후 "
                "pairs_seen 값을 '참여 페어:' 라인에 기재하세요.\n"
            )
            sys.exit(2)
    if set(claimed_pairs) != actual_pairs and not _has_cx_pairs():
        # (2026-06-12 카브아웃 4/4) 페어 미보유 프로젝트: generic 에이전트가 actual에
        # 'claude' 등으로 기록되나 PAIR-토큰 문법으로는 주장 불가(구조적 불일치) → advisory.
        sys.stderr.write(
            f"⚠️ Stop guard (advisory): 페어 미보유 프로젝트 — claimed={claimed_pairs} vs actual={sorted(actual_pairs)} "
            "불일치는 PAIR-토큰 문법 한계로 차단하지 않음 (task_calls 수치 검증은 계속).\n"
        )
    elif set(claimed_pairs) != actual_pairs:
        missing = sorted(set(claimed_pairs) - actual_pairs)
        sys.stderr.write(
            "❌ Stop guard (허위 주장): 메타 블록의 참여 페어가 감사 로그와 일치하지 않습니다. "
            f"claimed={claimed_pairs}, actual={sorted(actual_pairs)}\n"
            f"⚡ 자동 복구 지시: 이전 응답을 처음부터 다시 쓰지 마세요. "
            f"누락 페어 {missing} 만 지금 Task 도구로 호출하고, "
            "그 결과를 기존 분석에 추가하여 응답하세요. "
            "메타 블록은 verify 결과로 갱신하세요. "
            "필요 없는 페어였으면 처음부터 적지 마세요.\n"
        )
        sys.exit(2)
    if claimed_task_calls is None:
        sys.stderr.write(
            "❌ Stop guard: 메타 블록에 'Task 호출: N회'가 없습니다.\n"
            f"⚡ 자동 복구 지시: 메타 블록에 'Task 호출: {task_calls}회' 라인을 추가하세요.\n"
        )
        sys.exit(2)
    if claimed_task_calls != task_calls:
        sys.stderr.write(
            "❌ Stop guard (허위 주장): 메타 블록 Task 호출 수가 감사 로그와 일치하지 않습니다. "
            f"claimed={claimed_task_calls}, actual={task_calls}\n"
            f"⚡ 자동 복구 지시: 메타 블록의 'Task 호출:' 을 {task_calls}회로 정정하세요.\n"
        )
        sys.exit(2)
    if claimed_iteration is None:
        sys.stderr.write(
            "❌ Stop guard: 메타 블록에 'Iteration: N회'가 없습니다.\n"
            "⚡ 자동 복구 지시: 메타 블록에 'Iteration: N회' 라인을 추가하세요 (N ≤ task_calls).\n"
        )
        sys.exit(2)
    if claimed_iteration > task_calls:
        # (2026-06-12 카브아웃) "Iteration N = c+x 페어 N라운드 = ≥N task" 산술은 페어 보유
        # 프로젝트 전제. 미보유 프로젝트는 c=본인+x=generic 1콜로 1 iteration이 성립해
        # 정직한 Iteration 표기가 항상 task_calls를 초과 → advisory로 완화.
        if not _has_cx_pairs():
            sys.stderr.write(
                f"⚠️ Stop guard (advisory): Iteration({claimed_iteration}) > task_calls({task_calls}) "
                "— 페어 미보유 프로젝트라 차단하지 않음.\n"
            )
        else:
            sys.stderr.write(
                "❌ Stop guard (허위 주장): 메타 블록 Iteration이 실제 Task 호출 수를 초과합니다. "
                f"claimed={claimed_iteration}, task_calls={task_calls}\n"
                f"⚡ 자동 복구 지시: Iteration 값을 {task_calls} 이하로 정정하세요.\n"
            )
            sys.exit(2)

    # ── v2.7.6 STEP compliance 검사 (5대 미준수 차단) ──
    _check_step_compliance(mode, actual_pairs, task_calls, assistant_text, is_b_workflow)


def _check_step_compliance(
    mode: str,
    actual_pairs: set,
    task_calls: int,
    assistant_text: str,
    is_b_workflow: bool,
) -> None:
    """5대 미준수 사항 검증. 위반 시 exit(2) 차단 또는 stderr 경고."""

    # ── 검증 1: Codex (x-*) 교차검증 미수행 차단 ──
    # A1/B에서 x-* 페어가 하나도 없으면 비대칭 교차검증 위반
    if mode in (MODE_A1, MODE_B) and task_calls >= 2:
        has_x_pair = any(
            p.startswith("x-") or p.startswith("X-") for p in actual_pairs
        )
        if not has_x_pair:
            # (2026-06-12 카브아웃) 페어 미보유 프로젝트는 x-* 명명 에이전트가 존재하지 않아
            # 충족 불가능한 요구 — generic 적대검토 에이전트로 2-pass 수행하는 구조 → advisory.
            if not _has_cx_pairs():
                sys.stderr.write(
                    f"⚠️ Stop guard (advisory): {mode} task {task_calls}회, x-* 명명 페어 없음 "
                    "— 페어 미보유 프로젝트(generic 적대검토 인정). 차단하지 않음.\n"
                )
            else:
                sys.stderr.write(
                    f"❌ Stop guard (교차검증 위반): {mode}인데 Codex(x-*) 페어가 0개입니다. "
                    f"참여 페어: {sorted(actual_pairs)}.\n"
                    "⚡ 자동 복구 지시: 지금 즉시 관련 x-* 페어(예: x-lead, x-dev, x-sar 등)를 "
                    "Task 도구로 호출하여 교차검증을 수행하세요. c-* 만으로는 비대칭 검증이 불가합니다. "
                    "완료 후 verify 결과로 메타 블록을 작성하세요.\n"
                )
                sys.exit(2)

    # ── 검증 1.5: 발산 미해소인데 Iteration 1회 종결 차단 (글로벌 2-pass 규칙) ──
    # c-/x- 한쪽이 단독 발견하거나 발산점이 미해소면 최소 2회 iteration 필요.
    if mode in (MODE_A1, MODE_B) and task_calls >= 2:
        # 미해소 발산 신호 (강한 시그널만 — false positive 방어)
        DIVERGENCE_SIGNALS = ("단독 발견", "미해소", "미수렴", "합의 실패", "충돌")
        has_divergence = any(s in assistant_text for s in DIVERGENCE_SIGNALS)
        # "발산점 N건" 에서 N>0 이고 "해소" 안 붙은 경우도 발산
        m = re.search(r"발산점?\s*([1-9]\d*)\s*건", assistant_text)
        if m and "해소" not in assistant_text:
            has_divergence = True
        claimed_iter = _parse_claimed_iteration(assistant_text)
        if has_divergence and claimed_iter is not None and claimed_iter < 2:
            sys.stderr.write(
                f"❌ Stop guard (발산 미해소): {mode}인데 발산점이 있는데 Iteration {claimed_iter}회로 종결했습니다.\n"
                "⚡ 자동 복구 지시: 글로벌 2-pass 규칙상 발산(한쪽 단독 발견·미해소·충돌)이 있으면 "
                "최소 2회 iteration 필수입니다. 발산점에 대해 c-/x- 페어를 다시 호출하여 2차 교차 재검증을 "
                "수행하고, 수렴 또는 명시적 해소 후 메타 블록의 Iteration 을 갱신하세요. "
                "(이전 응답 전체 재작성 X — 발산점만 추가 검증해 이어붙이기)\n"
            )
            sys.exit(2)

    # ── 검증 2~5: 모드 B 전용 (step_compliance.json 연동) ──
    if mode != MODE_B:
        return

    compliance_file = RUNTIME_DIR / "step_compliance.json"
    if not compliance_file.exists():
        # step_compliance 미초기화 — 모드 B인데 enter-b 호출 안 됨
        sys.stderr.write(
            "⚠️ Stop guard (STEP compliance): 모드 B인데 step_compliance.json이 없습니다. "
            "STEP 0부터 시작하려면 'python3 scripts/step_compliance.py enter-b'를 호출하세요.\n"
        )
        return

    try:
        state = json.loads(compliance_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    if not state.get("active"):
        return

    # 턴 카운트 업데이트
    state["total_turns"] = state.get("total_turns", 0) + 1
    has_x = any(p.startswith("x-") or p.startswith("X-") for p in actual_pairs)
    if has_x:
        state["codex_turns"] = state.get("codex_turns", 0) + 1

    # 검증 2: STEP 0 전역 변수 미확정
    current_step = state.get("current_step")
    if current_step is not None and current_step > 0 and not state.get("globals_confirmed"):
        sys.stderr.write(
            "❌ Stop guard (STEP 위반): STEP 0 전역 변수가 확정되지 않은 채 "
            f"STEP {current_step}으로 진행했습니다.\n"
            "⚡ 자동 복구 지시: 사용자에게 전역 변수(PROJECT_PHASE, OUTPUT_TYPE, PRIMARY_DOMAIN 등)를 "
            "확인한 뒤 `python3 scripts/step_compliance.py globals-ok`를 호출하세요.\n"
        )
        _save_compliance(state, compliance_file)
        sys.exit(2)

    # 검증 3: STEP 순서 건너뛰기
    completed = state.get("completed_steps", [])
    if current_step is not None:
        step_order = [0, 1, 1.5, 2, 2.5, 3, 4, 5, 6]
        for step in step_order:
            if step >= current_step:
                break
            if step not in completed:
                sys.stderr.write(
                    f"❌ Stop guard (STEP 위반): STEP {step}이 완료되지 않은 채 "
                    f"STEP {current_step}으로 진행했습니다.\n"
                    f"⚡ 자동 복구 지시: STEP {step}부터 순서대로 수행하세요. "
                    f"완료 후 `python3 scripts/step_compliance.py advance {step}`를 호출하세요.\n"
                )
                _save_compliance(state, compliance_file)
                sys.exit(2)

    # 검증 4: 사용자 게이트 미통과 (STEP 진행 시 [계속]/[시작] 필요)
    gate_required = {1, 1.5, 2, 2.5, 3, 4, 5, 6}
    if current_step in gate_required and is_b_workflow:
        gates = state.get("user_gates", [])
        gate_steps = {g.get("step") for g in gates}
        if current_step not in gate_steps:
            gate_entry = {
                "trigger": "[계속]",
                "at": datetime.now().isoformat(timespec="seconds"),
                "step": current_step,
            }
            state.setdefault("user_gates", []).append(gate_entry)

    # 검증 5: STEP 4 승인 없이 구현 진행 (가장 위험)
    if current_step == 5 and 4 not in completed:
        sys.stderr.write(
            "❌ Stop guard (게이트 위반): STEP 4 (사용자 검토 + 승인)이 완료되지 않은 채 "
            "STEP 5 (구현)으로 진행했습니다.\n"
            "⚡ 자동 복구 지시: 사용자에게 PLAN.md 검토를 요청하고 '구현해줘' 승인을 받으세요. "
            "승인 후 `python3 scripts/step_compliance.py advance 4`를 호출하세요.\n"
        )
        _save_compliance(state, compliance_file)
        sys.exit(2)

    _save_compliance(state, compliance_file)


def _save_compliance(state: dict, path: Path) -> None:
    """step_compliance.json 저장 (stop guard 내부용)."""
    state["last_updated"] = datetime.now().isoformat(timespec="seconds")
    try:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def cmd_show(args) -> None:
    events = _iter_log_events()
    if args.last:
        events = events[-args.last:]
    for event in events:
        print(json.dumps(event, ensure_ascii=False, indent=2))


def cmd_stats(args) -> None:
    events = _iter_log_events()
    by_type: dict[str, int] = {}
    by_turn: dict[str, int] = {}
    for e in events:
        by_type[e.get("event", "?")] = by_type.get(e.get("event", "?"), 0) + 1
        by_turn[e.get("turn", "?")] = by_turn.get(e.get("turn", "?"), 0) + 1
    if args.format == "json":
        print(json.dumps({"events": by_type, "turns": len(by_turn)}, ensure_ascii=False, indent=2))
        return
    print("━━━ session_logger 통계 ━━━")
    print(f"  총 이벤트: {len(events)}")
    print(f"  총 턴:     {len(by_turn)}")
    for k, v in sorted(by_type.items()):
        print(f"  - {k}: {v}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Session logger + stop guard")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("turn-start")
    sm = sub.add_parser("set-mode") ; sm.add_argument("mode", choices=sorted(VALID_MODES))
    sub.add_parser("task-call")
    sub.add_parser("task-end")
    sub.add_parser("subagent-audit")
    te = sub.add_parser("turn-end") ; te.add_argument("--guard-exit", type=int, default=0)
    sub.add_parser("stop-guard")
    vf = sub.add_parser("verify") ; vf.add_argument("--turn") ; vf.add_argument("--recent", type=int, default=0) ; vf.add_argument("--format", choices=["text", "json"], default="text")
    sh = sub.add_parser("show") ; sh.add_argument("--last", type=int)
    st = sub.add_parser("stats") ; st.add_argument("--format", choices=["text", "json"], default="text")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "turn-start": cmd_turn_start()
    elif args.cmd == "set-mode": cmd_set_mode(args)
    elif args.cmd == "task-call": cmd_task_call()
    elif args.cmd == "task-end": cmd_task_end()
    elif args.cmd == "subagent-audit": cmd_subagent_audit()
    elif args.cmd == "turn-end": cmd_turn_end(args)
    elif args.cmd == "stop-guard": cmd_stop_guard()
    elif args.cmd == "verify": cmd_verify(args)
    elif args.cmd == "show": cmd_show(args)
    elif args.cmd == "stats": cmd_stats(args)


if __name__ == "__main__":
    main()
