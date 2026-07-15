#!/usr/bin/env python3
"""vgate_orchestrator.py — 단일 Stop orchestrator (v1.1 — mode-aware: report|hard).

역할(설계 implementation_design_v1.1.md §3-5 — ChatGPT 결함 #5·#6 반영):
- 훅 병렬성 사실 반영: vgate 로직 전부를 이 한 프로세스에서 순차 평가(체인 순서 가정 폐기).
- last_assistant_message 우선(문서 미확정 필드 — 있으면 사용), 없으면 transcript fallback.
- stop_hook_active retry 상태모델: 재생성된 메시지도 재평가. finding fingerprint + attempts 추적.
  연속 8회 cap 도달은 stop_gate_overridden_after_cap 으로 기록(enforcement failure — pass 아님).
- 모드(codex seal R3 #6 정합): mode.txt=hard 면 would_block 시 exit 2(차단+재생성 지시),
  report(또는 파일 부재=fail-safe)면 항상 exit 0(기록만). 인프라 예외는 모드 무관 exit 0(fail-open).
- Detector 4종(would_block 산출은 decision_boundary·absence 만, scope 는 영구 advisory):
  1) decision_boundary — 좁은 assertive 표현(불가능/진행불가/원인 확정)만. 대응 decision receipt
     (decisions.jsonl, TTL 내) 부재 시 would_block 기록 + 구체 해소 지시문 생성.
  2) scope_reduction — 보편부정·인과확정 표현 advisory (영구 report-only, hard 승격 대상 아님).
  3) gate_self_modified — gate 파일 fingerprint 가 pinned 값과 다르면 이 턴 PASS 불인정 기록.
- P−1 baseline sampling: secrets.randbelow(N) — detector 결과와 무관, 최종 출력 후 추첨.
- audit queue: would_block 전건(stream A/B) + baseline 표본(stream C). reviewer 패키지에는
  detector 결과를 넣지 않는다(블라인딩 — 별도 findings.jsonl 에만 기록).
"""
from __future__ import annotations
import json, re, secrets, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vgate_common import (AUDIT_QUEUE, BASELINE_DIR, DECISIONS, FINDINGS, RUNTIME,
                          STOP_STATE, VGATE_DIR, bounded, flock_append,
                          gate_fingerprint, load_jsonl, make_id, now, read_stdin_json)

SAMPLE_N = 20              # passed-turn 무작위 표본 1/20
DECISION_TTL_SEC = 1800    # decision turn 결속 불가 시 폴백 유효창 — 카나리로 조정
ABSENCE_RECENT_SEC = 180   # turn 미결속 시 부재-증거 최근창(전 이력 stale 세탁 차단)
PINNED_FP = VGATE_DIR / "pinned_fp.txt"
LEDGER = RUNTIME / "tool-use.jsonl"
CURRENT_TURN = RUNTIME / "_current_turn.txt"
QUEUE_INDEX = VGATE_DIR / "queue-index.jsonl"   # M8: stream 은 사이드카(리뷰어 비노출)
MODE_FILE = VGATE_DIR / "mode.txt"              # "hard" | "report" — 사용자 승인 게이트로만 전환


def _mode() -> str:
    try:
        m = MODE_FILE.read_text(encoding="utf-8").strip()
        return m if m in ("hard", "report") else "report"
    except Exception:
        return "report"  # 파일 부재 = 안전측(report-only)

try:
    from secret_masking import mask_secrets  # M10: 저장 텍스트 전건 마스킹
except Exception:
    # codex seal #9: 부재 시 원문 반환은 평문 저장 위험 → 보수적 억제(원문 저장 금지).
    def mask_secrets(t):  # noqa: E306
        return f"[MASKING_UNAVAILABLE:len={len(t) if isinstance(t, str) else 0}]"

# ── 좁은 assertive 트리거(codex: 광범위 표현은 telemetry 전용) ──────────────────
# ⚠️ 한글에는 \b 사용 금지(한글끼리는 word boundary 미성립 — '불가입니다' 실측 미매치).
# M7: guard 는 라인 전체가 아니라 **문장(절) 단위** — 같은 라인 뒤쪽 '미검증' 으로 앞 단정을
#     세탁하는 gaming 차단. 트리거에 일반형 '~할 수 없습니다/없다' 추가.
# ⚠️ '확신/장담/보장' 은 **부정형만** 면제(codex 배포리뷰 F11 — bare 토큰은 의미역전:
#    "원인은 X라고 확신합니다"가 면제되는 버그였음).
NEG_GUARD = re.compile(
    r"(단정|아니|않|없다고|의문|가능성|추정|미검증|미확정|가설"
    r"|(확신|장담|보장)할\s*수\s*없|알\s*수\s*없|\?)")
BLOCKED_PAT = re.compile(
    r"(불가능(합니다|하다|함)|진행\s*불가|[가-힣]+할\s*수(는|가)?\s*없(습니다|다|음)|(?<![A-Z_])BLOCKED\b)")
ROOTCAUSE_PAT = re.compile(
    r"(원인은\s?[^\n.!?]{1,60}(입니다|이다|였다)|때문입니다|근본\s*원인\s*=\s*|root\s+cause\s+(is|was)\b)")
# advisory 전용(광범위 — 영구 report-only)
SCOPE_PAT = re.compile(r"(모든\s*방법|어떤\s*방법도|유일한\s*(방법|원인)|전부\s*실패|절대\s*(안|불))")
SENT_SPLIT = re.compile(r"[.!?。\n]+")
# 부재 단정(사용자 최빈 실수 유형 — $imagegen "없다" 등). '문제 없습니다'류 FP 방지 위해
# 산출물 명사 결합 또는 명시적 부재 동사구만. ⚠️ '하지 않'(존재하지 않) 형태 필수 —
# server-b 라이브 실측서 이 형태 미탐 발견(2026-07-15). '되어 있지 않' 만 잡던 버그.
ABSENCE_PAT = re.compile(
    r"(존재하지\s*않|(설치|등록|구현|배선|생성)(되어|돼|되지|하지)[가-힣\s]{0,6}(않|없|못)"
    r"|찾(을\s*수\s*없|지\s*못)|발견(되지\s*않|하지\s*못)|미설치|미등록|미구현|미배선"
    r"|(파일|스킬|모듈|패키지|명령어?|함수|설정|훅|폴더|디렉토리|경로|도구|항목|데이터|체크포인트)"
    r"[가-힣\s]{0,15}(없습니다|없다|없음|존재하지\s*않))")
# ⚠️ 부재 전용 guard: 범용 NEG_GUARD 의 '않/아니'는 부재 표현 자체("있지 않습니다")의
# 형태소라 사용 불가 — hedging 표지만 면제(가설·불확실 표현은 단정이 아님).
ABS_GUARD = re.compile(r"(가능성|추정|모르|확실치|의문|미확인|Unverified|않을\s*수|아닐\s*수|수도\s*있|\?)")


def _lines_for_scan(text: str):
    """code fence·인용 제외한 본문 → **문장(절) 단위**(M7: 라인단위 guard gaming 차단)."""
    in_code = False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or s.startswith(">") or s.startswith("|"):
            continue
        for sent in SENT_SPLIT.split(ln):
            if sent.strip():
                yield sent


def _recent_decisions(ttl: int = DECISION_TTL_SEC) -> list[dict]:
    """M5: 현재 turn 에 결속된 decision 만(턴 결속 불가 시에만 TTL 폴백 — 한계 명시 기록)."""
    cur_turn = ""
    try:
        cur_turn = CURRENT_TURN.read_text(encoding="utf-8").strip()[:80]
    except Exception:
        pass
    out = []
    cutoff = time.time() - ttl
    for r in load_jsonl(DECISIONS):
        if not r.get("accepted"):
            continue
        rturn = r.get("turn", "")
        if cur_turn and rturn:
            if rturn == cur_turn:
                out.append(r)
            continue
        # 폴백(turn 미기록 레코드): TTL — 세션 교차 오염 가능성 있는 약한 결속(카나리 관측 대상)
        try:
            ts = datetime.strptime(r.get("ts", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
        if ts >= cutoff:
            r = dict(r); r["_weak_binding"] = True
            out.append(r)
    return out


def detect_decision_boundary(text: str) -> list[dict]:
    findings = []
    decs = _recent_decisions()
    dec_types = {d.get("type") for d in decs}
    # 의미 대조(결함 #1): '진행 불가' 확정 표현을 정당화하는 receipt 는
    #   search_space_closed=True 인 TESTED_METHODS 또는 POLICY 뿐.
    #   미시도 잔존(closed=False) receipt 는 확정 표현을 승인하지 않는다(범위 강등 요구).
    blocked_ok = any(
        (d.get("type") == "BLOCKED_UNDER_TESTED_METHODS" and d.get("search_space_closed"))
        or d.get("type") == "BLOCKED_UNDER_POLICY" for d in decs)
    scoped_only = (not blocked_ok) and any(
        d.get("type") == "BLOCKED_UNDER_TESTED_METHODS" for d in decs)
    for ln in _lines_for_scan(text):
        if NEG_GUARD.search(ln):
            continue
        if BLOCKED_PAT.search(ln):
            if not blocked_ok:
                reason = ("receipt 는 있으나 미시도 method 잔존(search_space_closed=false) — "
                          "확정 표현 불가. '시도한 방법 실패, X 미시도 — 미확정'으로 강등하십시오."
                          ) if scoped_only else (
                          "BLOCKED 류 선언에 decision receipt 없음. 허용 해소: "
                          "1) measure.py 로 대안 실측 후 재작성 "
                          "2) decision_receipt.py register-methods → declare "
                          "--type BLOCKED_UNDER_TESTED_METHODS "
                          "3) 표현 강등: '방법 A/B 시도 실패, C 미시도 — 미확정'")
                findings.append({
                    "detector": "decision_boundary", "class": "blocked_declaration",
                    "would_block": True, "line": mask_secrets(bounded(ln.strip(), 200)),
                    "resolution": reason})
        if ROOTCAUSE_PAT.search(ln):
            # hypothesis receipt 는 가설 표현만 정당화 — 확정형은 v1.1 에서 선언 경로 자체가
            # 없으므로(intervention/contrastive/외부검토 필요) 항상 강등 요구(의미 대조).
            findings.append({
                "detector": "decision_boundary", "class": "root_cause_assertion",
                "would_block": True, "line": mask_secrets(bounded(ln.strip(), 200)),
                "resolution": ("확정형 원인 주장은 intervention/contrastive/외부검토 없이 불가. "
                               "허용 해소: 1) 가설 강등('가능성이 있으나 미검증') + 측정값 병기 "
                               "2) decision_receipt.py declare --type ROOT_CAUSE_HYPOTHESIS "
                               "후 가설 표현으로 재작성")})
    return findings[:5]


def detect_scope_reduction(text: str) -> list[dict]:
    out = []
    for ln in _lines_for_scan(text):
        if NEG_GUARD.search(ln):
            continue
        if SCOPE_PAT.search(ln):
            out.append({"detector": "scope_reduction", "class": "universal_claim",
                        "would_block": False, "advisory": True,
                        "line": mask_secrets(bounded(ln.strip(), 200))})
    return out[:5]


def detect_absence(text: str) -> list[dict]:
    """부재 단정 — 이번 turn 에 검색/읽기 증거(ledger)가 있어야 통과.
    (absence_claim_guard L1 과 동형 — 하드 대상으로 orchestrator 에 내장, 사용자 승인 2026-07-15)"""
    hits = []
    for ln in _lines_for_scan(text):
        if ABS_GUARD.search(ln):
            continue
        if ABSENCE_PAT.search(ln):
            hits.append(ln)
    if not hits:
        return []
    cur_turn = ""
    try:
        cur_turn = CURRENT_TURN.read_text(encoding="utf-8").strip()[:80]
    except Exception:
        pass
    evid_kinds = {"search", "glob", "read", "list", "exec", "mcp-read"}
    ledger = [r for r in load_jsonl(LEDGER) if r.get("kind") in evid_kinds]
    if cur_turn:
        evidence = [r for r in ledger if r.get("turn") == cur_turn]
    else:
        # ⚠️ turn 미결속(_current_turn.txt 부재 — headless 등, codex 배포리뷰 F4/F5).
        # hard 게이트에서 '전체 ledger 수용'은 부재 단정을 무력화 → **최근 시간창**만 수용
        # (decisions TTL 폴백과 동형). 전 이력 stale evidence 로 세탁 불가.
        cutoff = time.time() - ABSENCE_RECENT_SEC
        evidence = []
        for r in ledger:
            try:
                ts = datetime.strptime(r.get("ts", ""), "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc).timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                evidence.append(r)
    if evidence:
        return []  # 조사 이벤트 존재 — 통과(약결속: 대상 일치까지는 미검증)
    return [{"detector": "absence", "class": "absence_without_search",
             "would_block": True, "line": mask_secrets(bounded(hits[0].strip(), 200)),
             "weak_turn_binding": not cur_turn,
             "resolution": ("부재 단정 전 이번 턴에 검색/읽기 증거가 없음. 허용 해소: "
                            "1) Grep/Glob/ls 로 실측 후 재작성 — 도구/스킬 부재는 "
                            "~/.codex/skills·~/.claude/skills·~/.agents/skills 전부 확인 "
                            "2) '확인 못 함/Unverified' 로 강등. "
                            "**필수 문형**: 부재/불가 결론은 반드시 '확인한 곳: …/미확인: …' 범위를 "
                            "함께 명시(범위 없는 단정은 사용자에게 틀린 믿음을 심음)")}]


def detect_gate_self_modified() -> list[dict]:
    cur = gate_fingerprint()
    try:
        pinned = PINNED_FP.read_text(encoding="utf-8").strip()
    except Exception:
        return [{"detector": "gate_self_modified", "class": "no_pin",
                 "would_block": False, "advisory": True,
                 "note": "pinned_fp 미설정 — 배선 단계에서 pin 필요"}]
    if cur != pinned:
        return [{"detector": "gate_self_modified", "class": "fp_mismatch",
                 "would_block": False, "advisory": True,
                 "note": f"gate fp {cur} ≠ pinned {pinned}. 이 상태의 gate PASS 는 증거로 불인정.",
                 "pinned": pinned, "current": cur}]
    return []


def _last_assistant_from_transcript(tpath: str) -> str:
    try:
        lines = Path(tpath).read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    for ln in reversed(lines):
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        msg = rec.get("message", rec)
        role = msg.get("role") or rec.get("role") or rec.get("type")
        if role == "assistant":
            c = msg.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                t = "\n".join(b.get("text", "") for b in c
                              if isinstance(b, dict) and b.get("type") == "text")
                if t.strip():
                    return t
    return ""


def _ledger_tail(n: int = 40) -> list:
    """codex seal #9: ledger 항목(경로·패턴·verb)도 저장 전 마스킹 — JSON 왕복으로 전 필드 적용."""
    tail = load_jsonl(LEDGER)[-n:]
    try:
        return json.loads(mask_secrets(json.dumps(tail, ensure_ascii=False)))
    except Exception:
        return [{"masking_error": True, "count": len(tail)}]


def _write_audit_package(kind: str, payload_id: str, text: str, extra: dict) -> None:
    """reviewer 블라인딩(M8): stream 은 패키지에 넣지 않고 사이드카 index 에만 기록.
    M10: 저장 텍스트 전건 secret 마스킹. M12: tmp+rename 원자 쓰기."""
    pkg = {"ts": now(), "package_id": payload_id,
           "assistant_output": mask_secrets(bounded(text, 6000)),
           "ledger_tail": _ledger_tail(),
           "recent_decisions": [
               {k: (mask_secrets(v) if isinstance(v, str) else v)
                for k, v in d.items() if k not in ("gate_fp",)}
               for d in _recent_decisions(3600)], **extra}
    try:
        AUDIT_QUEUE.mkdir(parents=True, exist_ok=True)
        tmp = AUDIT_QUEUE / f".{payload_id}.tmp"
        tmp.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(AUDIT_QUEUE / f"{payload_id}.json")
        flock_append(QUEUE_INDEX, {"ts": now(), "package_id": payload_id, "stream": kind})
    except Exception:
        pass


def main() -> int:
    payload = read_stdin_json()
    session_id = str(payload.get("session_id", ""))[:60]
    prompt_id = str(payload.get("prompt_id", ""))[:60]
    stop_active = bool(payload.get("stop_hook_active"))
    text = payload.get("last_assistant_message") or ""
    if not text:
        tpath = payload.get("transcript_path") or payload.get("transcriptPath") or ""
        if tpath:
            text = _last_assistant_from_transcript(tpath)
    if not text:
        return 0  # 평가 대상 없음 — fail-open

    findings = (detect_decision_boundary(text)
                + detect_absence(text)
                + detect_scope_reduction(text)
                + detect_gate_self_modified())
    would_block = [f for f in findings if f.get("would_block")]

    # retry 상태모델(결함 #6): 재생성 메시지도 재평가, fingerprint 로 동일위반 추적.
    # M12: session 결속 key + tmp/rename 원자 쓰기(전역 prompt_id 충돌·race 해소).
    fp = make_id("fnd", {"c": sorted(f"{f['detector']}:{f.get('class')}" for f in would_block)})
    skey = f"{session_id}:{prompt_id}"
    state = {}
    try:
        state = json.loads(STOP_STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    attempts = 1
    if stop_active and state.get("key") == skey and state.get("fingerprint") == fp and would_block:
        attempts = int(state.get("attempts", 1)) + 1
    cap_overridden = attempts >= 8 and bool(would_block)
    try:
        VGATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STOP_STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"key": skey, "fingerprint": fp, "attempts": attempts, "ts": now()}),
            encoding="utf-8")
        tmp.rename(STOP_STATE)
    except Exception:
        pass

    # P−1 baseline: detector 와 무관한 무작위 표본(출력 후 추첨 — 사전 예측 불가).
    # M12: pkg_id 에 난수 토큰(초 해상도 충돌 방지). M9: C stream 은 passed 턴만
    #      (would_block 턴은 AB stream 전용 — miss 분모 오염 방지). baseline 은 무조건.
    sampled = secrets.randbelow(SAMPLE_N) == 0
    pkg_id = make_id("aud", {"s": session_id, "p": prompt_id, "t": now(),
                             "r": secrets.token_hex(4)})
    if sampled:
        try:
            BASELINE_DIR.mkdir(parents=True, exist_ok=True)
            btmp = BASELINE_DIR / f".{pkg_id}.tmp"
            btmp.write_text(json.dumps(
                {"ts": now(), "session_id": session_id, "prompt_id": prompt_id,
                 "assistant_output": mask_secrets(bounded(text, 6000)),
                 "ledger_tail": _ledger_tail()}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            btmp.rename(BASELINE_DIR / f"{pkg_id}.json")
        except Exception:
            pass
        if not would_block:
            _write_audit_package("C_random_passed", pkg_id, text, {})
    if would_block:  # stream A/B: would_block 전건 감사 대상
        _write_audit_package("AB_would_block", "wb-" + pkg_id, text, {})

    mode = _mode()
    flock_append(FINDINGS, {
        "ts": now(), "session_id": session_id, "prompt_id": prompt_id,
        "gate_fp": gate_fingerprint(), "mode": mode, "stop_hook_active": stop_active,
        "attempts": attempts, "cap_overridden": cap_overridden,
        "sampled_baseline": sampled, "would_block_count": len(would_block),
        "findings": findings})
    if cap_overridden:
        flock_append(FINDINGS, {"ts": now(), "metric": "stop_gate_overridden_after_cap",
                                "prompt_id": prompt_id})
    # hard 모드(사용자 승인 2026-07-15): would_block → exit 2 + 구체 해소 지시(stderr → 모델 재생성).
    # 연속 8회 cap 은 Claude Code 가 상위에서 강제 종료(문서 TRUE) — cap_overridden 으로 기록됨.
    if mode == "hard" and would_block:
        for f in would_block:
            sys.stderr.write(f"[vgate:{f['class']}] {f.get('line','')}\n"
                             f"  → {f.get('resolution','')}\n")
        sys.stderr.write(f"(vgate hard gate — 위 {len(would_block)}건 해소 후 재작성. "
                         f"attempt {attempts}/8)\n")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # 어떤 예외에도 턴을 깨지 않음
