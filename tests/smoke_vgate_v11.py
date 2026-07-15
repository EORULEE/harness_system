#!/usr/bin/env python3
"""smoke_vgate_v11.py — verification-gate v1.1 수용기준 스모크 (설계=implementation_design_v1.1.md).

격리: 임시 runtime 디렉토리로 vgate_common 경로를 monkeypatch (실 runtime 오염 0).
커버: measure.py 정직성(결함#7) · decision_receipt contract(결함#1·#2) ·
      orchestrator 의미대조/retry(결함#5·#6) · tripwire(결함#3) · audit 분모(P2).
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

TMP = Path(tempfile.mkdtemp(prefix="vgate11_"))

import vgate_common as vc  # noqa: E402
# ── 격리 monkeypatch ──
vc.VGATE_DIR = TMP / "vgate"
vc.RECEIPTS = vc.VGATE_DIR / "receipts.jsonl"
vc.DECISIONS = vc.VGATE_DIR / "decisions.jsonl"
vc.METHODS = vc.VGATE_DIR / "methods.jsonl"
vc.FINDINGS = vc.VGATE_DIR / "findings.jsonl"
vc.STOP_STATE = vc.VGATE_DIR / "stop_state.json"
vc.BASELINE_DIR = vc.VGATE_DIR / "baseline"
vc.AUDIT_QUEUE = vc.VGATE_DIR / "audit-queue"
vc.AUDIT_LABELS = vc.VGATE_DIR / "audit-labels.jsonl"

import vgate_orchestrator as vo  # noqa: E402
for name in ("DECISIONS", "FINDINGS", "STOP_STATE", "BASELINE_DIR", "AUDIT_QUEUE", "VGATE_DIR"):
    setattr(vo, name, getattr(vc, name))
vo.PINNED_FP = vc.VGATE_DIR / "pinned_fp.txt"
vo.LEDGER = TMP / "tool-use.jsonl"

import decision_receipt as dr  # noqa: E402
for name in ("DECISIONS", "METHODS", "RECEIPTS"):
    setattr(dr, name, getattr(vc, name))
dr.LEDGER = TMP / "tool-use.jsonl"
# turn 결속(M5) 격리
TURN_FILE = TMP / "_current_turn.txt"
TURN_FILE.write_text("turn-vgtest")
dr.CURRENT_TURN = TURN_FILE
vo.CURRENT_TURN = TURN_FILE
vo.QUEUE_INDEX = vc.VGATE_DIR / "queue-index.jsonl"

R = []
def ck(name, cond, detail=""):
    R.append((name, bool(cond)))
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if not cond and detail else ""))


class A:  # argparse namespace 대용
    def __init__(self, **kw):
        self.__dict__.update({"task": None, "summary": None, "host": None,
                              "attempted": None, "evidence": None, "policy_ref": None,
                              "type": None, "methods": None, **kw})


def declare(**kw):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = dr.cmd_declare(A(**kw))
    return rc, json.loads(buf.getvalue())


def orch(payload):
    """orchestrator main 을 격리 실행."""
    import io, contextlib
    stdin_backup = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            vo.main()
    finally:
        sys.stdin = stdin_backup
    finds = vc.load_jsonl(vc.FINDINGS)
    return [f for f in finds if "findings" in f][-1]


print("== AC-1 measure.py 정직성(결함#7: 개별 rc, 허위 성공 금지) ==")
env = dict(os.environ)
p = subprocess.run([sys.executable, str(SCRIPTS / "measure.py"), "mount", "--path", "/nonexistent_xyz"],
                   capture_output=True, text=True, env=env, cwd=str(ROOT))
rec = json.loads(p.stdout)
ck("AC-1.1 미존재 path → ok=false", rec["ok"] is False)
ck("AC-1.2 findmnt 개별 rc!=0 보존", rec["probes"]["findmnt"]["rc"] != 0)
ck("AC-1.3 실패 시 exit 1", p.returncode == 1)
p2 = subprocess.run([sys.executable, str(SCRIPTS / "measure.py"), "import", "--module", "os;import evil"],
                    capture_output=True, text=True, env=env, cwd=str(ROOT))
ck("AC-1.4 모듈명 injection 거부", p2.returncode == 2)

print("== AC-2 decision contract(결함#1: laundering, #2: none-known) ==")
rc, out = declare(type="BLOCKED", summary="x")
ck("AC-2.1 BLOCKED 원형 선언 거부", rc == 1 and out["reject_code"] == "STATE_NOT_DECLARABLE")
rc, out = declare(type="GLOBALLY_IMPOSSIBLE")
ck("AC-2.2 보편부정 선언 거부", rc == 1)
rc, out = declare(type="DECLARE_ROOT_CAUSE")
ck("AC-2.3 확정 원인 선언 거부(hypothesis 강제)", rc == 1)
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="t-unreg", attempted="m=obs:x")
ck("AC-2.4 method 선등록 없이 거부", out["reject_code"] == "METHODS_NOT_REGISTERED")

import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    dr.cmd_register_methods(A(task="tv", methods="m1,m2,m3"))
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m9=obs:x")
ck("AC-2.5 미등록 method 거부", out["reject_code"] == "UNREGISTERED_METHOD")
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m1=obs:fake999")
ck("AC-2.6 가짜 receipt 거부(laundering 차단)", out["reject_code"] == "EVIDENCE_UNRESOLVED")
# 실패 receipt 생성(격리 receipts.jsonl — 등록 이후 ts, measure 형식)
vc.flock_append(vc.RECEIPTS, {"receipt_id": "obs:real00000001", "ok": False, "ts": vc.now(),
                              "observable": "linux.mount.fstype",
                              "subject": {"requested_alias": "local"}})
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m1=obs:real00000001")
ck("AC-2.7 실패 receipt 1건 수락 + untried 기계계산",
   rc == 0 and out["untried_computed"] == ["m2", "m3"] and out["search_space_closed"] is False)
rc, out = declare(type="ROOT_CAUSE_HYPOTHESIS", summary="가설")
ck("AC-2.8 hypothesis modality 수락", rc == 0 and out["modality"] == "hypothesis")
# M4: 타 호스트 receipt 를 다른 host 선언에 사용 → 거부
vc.flock_append(vc.RECEIPTS, {"receipt_id": "obs:otherhost0001", "ok": True, "ts": vc.now(),
                              "observable": "python.module.import_latency",
                              "subject": {"requested_alias": "devbox", "remote_hostname": "DEVBOX"}})
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv",
                  attempted="m1=obs:otherhost0001", host="server-a")
ck("AC-2.9 M4형: 타 머신 receipt 오귀속 거부", out["reject_code"] == "EVIDENCE_UNRESOLVED")

print("== AC-6 codex 리뷰 BLOCKER 재발 방지(적대 케이스) ==")
# B1: local receipt 로 원격 host 선언 → 거부(local 면제 제거)
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv",
                  attempted="m1=obs:real00000001", host="prod-server")
ck("AC-6.1 B1 local receipt→원격 선언 거부", out["reject_code"] == "EVIDENCE_UNRESOLVED")
# B1b: 원격 receipt 를 host 미지정(local) 선언에 → 거부
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m1=obs:otherhost0001")
ck("AC-6.2 B1 원격 receipt→local 선언 거부", out["reject_code"] == "EVIDENCE_UNRESOLVED")
# B2: 성공 receipt 는 실패 증거 불가
vc.flock_append(vc.RECEIPTS, {"receipt_id": "obs:successlocal", "ok": True, "ts": vc.now(),
                              "observable": "python.module.import_latency",
                              "subject": {"requested_alias": "local"}})
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m1=obs:successlocal")
ck("AC-6.3 B2 성공 receipt→BLOCKED 거부", out["reject_code"] == "EVIDENCE_UNRESOLVED"
   and "실패 증거" in out["message"])
# B3: 동일 evidence 로 전 method 닫기 → 거부
vc.flock_append(vc.RECEIPTS, {"receipt_id": "obs:fail2", "ok": False, "ts": vc.now(),
                              "subject": {"requested_alias": "local"}})
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv",
                  attempted="m1=obs:real00000001,m2=obs:real00000001,m3=obs:real00000001")
ck("AC-6.4 B3 동일 evidence 재사용 거부", out["reject_code"] == "SAME_EVIDENCE_REUSED")
# B3b: 등록 이전 ts 의 evidence → 거부(선등록 강제)
vc.flock_append(vc.RECEIPTS, {"receipt_id": "obs:stale0000001", "ok": False,
                              "ts": "2020-01-01T00:00:00Z",
                              "subject": {"requested_alias": "local"}})
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv", attempted="m1=obs:stale0000001")
ck("AC-6.5 B3 등록 이전 evidence 거부", out["reject_code"] == "EVIDENCE_UNRESOLVED"
   and "선행" in out["message"])
# B4: ledger tu_ 이벤트를 원격 선언에 → 거부(host 결속 불가)
rc, out = declare(type="BLOCKED_UNDER_TESTED_METHODS", task="tv",
                  attempted="m1=tu_whatever", host="server-a")
ck("AC-6.6 B4 ledger 이벤트→원격 선언 거부", "host 결속 불가" in out["message"])
# M6: 임의 파일 policy 거부 + 실제 인용문 검증
rc, out = declare(type="BLOCKED_UNDER_POLICY", policy_ref="/etc/passwd", policy_quote="root")
ck("AC-6.7 M6 정책 스코프 밖 파일 거부", out["reject_code"] == "POLICY_FILE_OUT_OF_SCOPE")
# 이식성: 대상 프로젝트 CLAUDE.md 내용에 의존하지 않도록 스코프 내 임시 정책 파일 사용
POLICY_F = ROOT / ".claude" / "runtime" / "_vgate_smoke_policy.md"
POLICY_F.parent.mkdir(parents=True, exist_ok=True)
POLICY_F.write_text("테스트 정책: 실거래 금지 조항", encoding="utf-8")
rc, out = declare(type="BLOCKED_UNDER_POLICY", policy_ref=str(POLICY_F),
                  policy_quote="이 문구는 존재하지 않는다zzz")
ck("AC-6.8 M6 인용문 미존재 거부", out["reject_code"] == "POLICY_QUOTE_NOT_FOUND")
rc, out = declare(type="BLOCKED_UNDER_POLICY", policy_ref=str(POLICY_F),
                  policy_quote="실거래 금지")
ck("AC-6.9 M6 실재 인용문 수락", rc == 0)
POLICY_F.unlink(missing_ok=True)

print("== AC-3 orchestrator 의미대조·retry(결함#5·#6) ==")
# 섹션 격리: AC-2/6 에서 수락된 decision(동일 turn 결속)이 표현을 정당화하지 않도록 초기화.
vc.DECISIONS.write_text("")
vo.PINNED_FP.parent.mkdir(parents=True, exist_ok=True)
vo.PINNED_FP.write_text(vc.gate_fingerprint())
f = orch({"session_id": "s", "prompt_id": "p1",
          "last_assistant_message": "이 작업은 진행 불가입니다."})
wb = [x for x in f["findings"] if x.get("would_block")]
ck("AC-3.1 M3형 receipt-scope 불일치 → would_block", f["would_block_count"] >= 1
   and any("search_space_closed" in x.get("resolution", "") or "receipt 없음" in x.get("resolution", "") for x in wb))
f = orch({"session_id": "s", "prompt_id": "p2",
          "last_assistant_message": "원인은 SMR입니다."})
ck("AC-3.2 M2형 확정 원인 → would_block",
   any(x.get("class") == "root_cause_assertion" for x in f["findings"]))
f = orch({"session_id": "s", "prompt_id": "p3",
          "last_assistant_message": "SMR 영향 가능성이 있으나 미검증입니다. 측정값은 2.0초."})
ck("AC-3.3 강등 표현 통과(FP 방지)", f["would_block_count"] == 0)
f = orch({"session_id": "s", "prompt_id": "p4",
          "last_assistant_message": "> 인용: 진행 불가\n```\n원인은 X입니다.\n```\n계속 분석합니다."})
ck("AC-3.4 인용·코드블록 제외", f["would_block_count"] == 0)
f1 = orch({"session_id": "s", "prompt_id": "p5",
           "last_assistant_message": "진행 불가입니다."})
f2 = orch({"session_id": "s", "prompt_id": "p5", "stop_hook_active": True,
           "last_assistant_message": "여전히 진행 불가입니다."})
ck("AC-3.5 retry 재평가 + attempts 증가", f1["attempts"] == 1 and f2["attempts"] == 2)
# gate self-modified: pin 을 다른 값으로 → advisory
vo.PINNED_FP.write_text("deadbeef0000")
f = orch({"session_id": "s", "prompt_id": "p6", "last_assistant_message": "일반 응답."})
ck("AC-3.6 gate fp 불일치 → self-modified 기록",
   any(x.get("class") == "fp_mismatch" for x in f["findings"]))
vo.PINNED_FP.write_text(vc.gate_fingerprint())

print("== AC-4 audit 블라인딩·분모 ==")
pkgs = list(vc.AUDIT_QUEUE.glob("*.json"))
ck("AC-4.1 would_block 전건 audit queue 적재", len(pkgs) >= 3)
blind_ok = all("would_block" not in json.loads(p.read_text(encoding="utf-8"))
               and "findings" not in json.loads(p.read_text(encoding="utf-8")) for p in pkgs)
ck("AC-4.2 reviewer 패키지에 detector 결과 없음(블라인딩)", blind_ok)
# M8: stream 키가 패키지에 없고 사이드카 index 에만 존재
stream_leak = any("stream" in json.loads(p.read_text(encoding="utf-8")) for p in pkgs)
idx = vc.load_jsonl(vc.VGATE_DIR / "queue-index.jsonl")
ck("AC-4.3 M8 stream 은 패키지 밖(사이드카)", not stream_leak and len(idx) >= 1
   and all("stream" in r for r in idx))

print("== AC-7 M7 한국어 우회·M9 스트림 오염·M10 마스킹 ==")
vc.DECISIONS.write_text("")  # 섹션 격리(동일 turn decision 의 정당화 차단)
f = orch({"session_id": "s", "prompt_id": "q1",
          "last_assistant_message": "이 방식은 사용할 수 없습니다."})
ck("AC-7.1 M7 '~할 수 없습니다' 포착",
   any(x.get("class") == "blocked_declaration" for x in f["findings"]))
f = orch({"session_id": "s", "prompt_id": "q2",
          "last_assistant_message": "원인은 네트워크 설정 오류입니다."})
ck("AC-7.2 M7 다어절 원인 확정 포착",
   any(x.get("class") == "root_cause_assertion" for x in f["findings"]))
f = orch({"session_id": "s", "prompt_id": "q3",
          "last_assistant_message": "원인은 권한 부족입니다. 단, 다른 항목은 미검증입니다."})
ck("AC-7.3 M7 문장단위 guard(뒤쪽 '미검증' 세탁 차단)",
   any(x.get("class") == "root_cause_assertion" for x in f["findings"]))
f = orch({"session_id": "s", "prompt_id": "q4",
          "last_assistant_message": "현재 정보로는 단정할 수 없습니다. 확신할 수 없어 재측정이 필요합니다."})
ck("AC-7.4 abstention 표현 통과(FP 방지)", f["would_block_count"] == 0)
# M9: 강제 sampling + would_block 턴 → C stream 미적재(AB 만)
import types as _types, secrets as _secrets
_orig_secrets = vo.secrets
vo.secrets = _types.SimpleNamespace(randbelow=lambda n: 0, token_hex=_secrets.token_hex)
idx_before = {r["stream"] for r in []}
c_before = sum(1 for r in vc.load_jsonl(vo.QUEUE_INDEX) if r["stream"] == "C_random_passed")
ab_before = sum(1 for r in vc.load_jsonl(vo.QUEUE_INDEX) if r["stream"] == "AB_would_block")
f = orch({"session_id": "s", "prompt_id": "q5",
          "last_assistant_message": "이 경로는 사용할 수 없습니다."})
vo.secrets = _orig_secrets
c_after = sum(1 for r in vc.load_jsonl(vo.QUEUE_INDEX) if r["stream"] == "C_random_passed")
ab_after = sum(1 for r in vc.load_jsonl(vo.QUEUE_INDEX) if r["stream"] == "AB_would_block")
ck("AC-7.5 M9 would_block 턴은 C stream 제외(AB 만)",
   f["sampled_baseline"] and c_after == c_before and ab_after == ab_before + 1)
# M10: secret 이 패키지에 평문 저장되지 않음.
# fixture 토큰은 런타임 조립(파일에 평문 두면 릴리스 seal secret-precheck 가 차단 — 실측 2026-07-15)
_tok = "sk-" + "live1234567890abcdefghij"
f = orch({"session_id": "s", "prompt_id": "q6",
          "last_assistant_message": f"원인은 인증 오류입니다. Bearer {_tok} 토큰 사용."})
newest = max(vc.AUDIT_QUEUE.glob("*.json"), key=lambda p: p.stat().st_mtime)
raw = newest.read_text(encoding="utf-8")
ck("AC-7.6 M10 secret 마스킹(패키지에 원문 부재)", _tok not in raw)
# codex seal #9: ledger_tail 도 마스킹 경로 통과 검증(ledger 에 secret 심고 패키지 원문 부재)
_tok2 = "sk-" + "ledgerhidden1234567890ab"
(TMP / "tool-use.jsonl").write_text(
    json.dumps({"ts": vc.now(), "turn": "turn-vgtest", "kind": "exec",
                "tool": "Bash", "cwd": "/x",
                "target": {"verb": "curl", "paths": [f"Bearer {_tok2}"]}}) + "\n")
f = orch({"session_id": "s", "prompt_id": "q7",
          "last_assistant_message": "원인은 인증 헤더입니다."})
newest = max(vc.AUDIT_QUEUE.glob("*.json"), key=lambda p: p.stat().st_mtime)
ck("AC-7.7 #9 ledger_tail 마스킹(패키지에 ledger secret 부재)",
   _tok2 not in newest.read_text(encoding="utf-8"))

print("== AC-5 tripwire(결함#3) ==")
def trip(cmd):
    p = subprocess.run(["node", str(ROOT / "hooks" / "pre-tool-vgate-tripwire.mjs")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True)
    return "ask" in p.stdout
ck("AC-5.1 rm -rf 절대경로 → ask", trip("rm -rf /data/x"))
ck("AC-5.2 원격 destructive → ask", trip("ssh h systemctl restart svc"))
ck("AC-5.3 /tmp 삭제 침묵(FP)", not trip("rm -rf /tmp/x"))
ck("AC-5.4 일반 명령 침묵", not trip("ls -la && python3 t.py"))
# M14: 분리형/장형 플래그 변형
ck("AC-5.5 M14 rm -r -f 분리형 → ask", trip("rm -r -f /etc/app"))
ck("AC-5.6 M14 rm --recursive --force → ask", trip("rm --recursive --force /etc/app"))
ck("AC-5.7 M14 원격 장형 → ask", trip("ssh prod rm --recursive --force /etc/app"))
ck("AC-5.8 M14 rm -rf 상대경로 침묵(FP)", not trip("rm -rf build/ dist/"))

print("== AC-8 hard 모드(사용자 승인 2026-07-15) ==")
vc.DECISIONS.write_text("")
vo.MODE_FILE = vc.VGATE_DIR / "mode.txt"
LEDGER_F = TMP / "tool-use.jsonl"


def orch_rc(payload):
    import io, contextlib
    stdin_backup = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                rc = vo.main()
        return rc, err.getvalue()
    finally:
        sys.stdin = stdin_backup


vo.MODE_FILE.write_text("report")
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h0",
                 "last_assistant_message": "이 작업은 진행 불가입니다."})
ck("AC-8.1 report 모드 = 위반이어도 exit 0", rc == 0)
vo.MODE_FILE.write_text("hard")
rc, err = orch_rc({"session_id": "s", "prompt_id": "h1",
                   "last_assistant_message": "이 작업은 진행 불가입니다."})
ck("AC-8.2 hard 모드 위반 → exit 2 + 해소지시", rc == 2 and ("해소" in err or "declare" in err))
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h2",
                 "last_assistant_message": "방법 A/B 시도 실패, C 미시도 — 미확정입니다. 가능성 검토 계속."})
ck("AC-8.3 hard 모드 강등 표현 → exit 0", rc == 0)
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h3",
                 "last_assistant_message": "모든 방법이 아니라 일부만 실패했습니다."})
ck("AC-8.4 advisory(scope)만으로는 차단 안 함", rc == 0)
# 부재 단정: 검색 증거 없음 → 2, 이번 turn ledger 증거 있음 → 0
LEDGER_F.write_text("")
rc, err = orch_rc({"session_id": "s", "prompt_id": "h4",
                   "last_assistant_message": "그 스킬은 설치되어 있지 않습니다."})
ck("AC-8.5 부재 단정 무증거 → exit 2", rc == 2 and "absence" in err)
LEDGER_F.write_text(json.dumps({"ts": vc.now(), "turn": "turn-vgtest", "kind": "search",
                                "tool": "Grep", "cwd": "/x", "target": {"pattern": "skill"}}) + "\n")
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h5",
                 "last_assistant_message": "그 스킬은 설치되어 있지 않습니다."})
ck("AC-8.6 부재 단정 + 이번 turn 검색 증거 → exit 0", rc == 0)
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h6",
                 "last_assistant_message": "문제 없습니다. 이상 없습니다. 오류가 없습니다."})
ck("AC-8.7 '문제/이상 없습니다' FP 방지(부재 아님)", rc == 0)
rc, err = orch_rc({"session_id": "s", "prompt_id": "h7",
                   "last_assistant_message": "근본 원인은 권한 부족이라고 확신합니다. 원인은 권한입니다."})
ck("AC-8.8 F11 '확신합니다' 강한 단정 면제 버그 수정", rc == 2)
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h8",
                 "last_assistant_message": "원인이 무엇인지 확신할 수 없습니다."})
ck("AC-8.9 '확신할 수 없' 부정형은 통과", rc == 0)
# F4/F5(server-b 라이브 실측 발견): _current_turn.txt 부재 시 부재 detector 가
# ledger 의 오래된 evidence 로 세탁되면 안 됨(최근창만 수용).
import time as _t
vo.CURRENT_TURN = TMP / "_no_such_turn.txt"  # 부재 강제
LEDGER_F.write_text(json.dumps({"ts": "2020-01-01T00:00:00Z", "turn": "old",
                                "kind": "search", "tool": "Grep", "cwd": "/x",
                                "target": {"pattern": "z"}}) + "\n")
rc, err = orch_rc({"session_id": "s", "prompt_id": "h9",
                   "last_assistant_message": "그 파일은 존재하지 않습니다."})
ck("AC-8.10 F4 turn 미결속+오래된 evidence → 여전히 차단", rc == 2 and "absence" in err)
import datetime as _dt
fresh_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
LEDGER_F.write_text(json.dumps({"ts": fresh_ts, "turn": "x", "kind": "search",
                                "tool": "Grep", "cwd": "/x", "target": {"pattern": "z"}}) + "\n")
rc, _ = orch_rc({"session_id": "s", "prompt_id": "h10",
                 "last_assistant_message": "그 파일은 존재하지 않습니다."})
ck("AC-8.11 F4 turn 미결속+최근 검색 → 통과", rc == 0)
TURN_FILE.write_text("turn-vgtest")
vo.CURRENT_TURN = TURN_FILE
# 부재 표현 형태 corpus(server-b 실측 '존재하지 않' 미탐 + codex F11 목록)
LEDGER_F.write_text("")  # 검색 증거 0 → 부재 단정이면 차단돼야
ABS_CATCH = ["그 파일은 존재하지 않습니다.", "CUDA 모듈이 설치되어 있지 않습니다.",
             "오늘자 체크포인트 파일이 없습니다.", "활성 훅이 없습니다.",
             "해당 데이터가 발견되지 않았습니다.", "그 함수는 구현되어 있지 않습니다."]
_c = sum(1 for m in ABS_CATCH
         if orch_rc({"session_id": "s", "prompt_id": "abc" + str(hash(m) % 999),
                     "last_assistant_message": m})[0] == 2)
ck(f"AC-8.12 부재 형태 corpus {len(ABS_CATCH)}종 전부 차단", _c == len(ABS_CATCH),
   f"{_c}/{len(ABS_CATCH)}")
ABS_FP = ["문제 없습니다.", "이상 없습니다. 오류가 없습니다.", "특별한 제약이 없습니다."]
_f = sum(1 for m in ABS_FP
         if orch_rc({"session_id": "s", "prompt_id": "afp" + str(hash(m) % 999),
                     "last_assistant_message": m})[0] == 0)
ck(f"AC-8.13 부재 FP 방지 {len(ABS_FP)}종 통과", _f == len(ABS_FP), f"{_f}/{len(ABS_FP)}")

n_pass = sum(1 for _, ok in R if ok)
print(f"\n{'='*50}\nRESULT: {n_pass}/{len(R)} PASS")
sys.exit(0 if n_pass == len(R) else 1)
