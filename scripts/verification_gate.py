#!/usr/bin/env python3
"""verification_gate_v2.py — 일반화 Detector 프레임워크 (확장성·범용성 검증용).

v1 한계: ClaimClass 가 'tool 증거 대조'에만 묶여 있어 입력충실도($imagegen 삭제)·보정 같은
        비-evidence형 검사를 못 담았다(= 범용성 부족).
v2: 모든 검사를 단일 인터페이스 Detector.check(ctx)->[Finding] 로 통일.
    ctx = {output_text, tool_evidence, user_input}. 이종 detector 가 같은 evaluate 로 합성됨.
    → 확장성 = register(Detector) 한 줄, CORE 무변경. 범용성 = 서로 다른 입력원을 쓰는 detector 공존.

격리 프로토타입 — live 훅 미배선.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# ══════════════════════ CORE (아래는 detector 추가 시 절대 안 바뀌는 부분) ══════════════════════
@dataclass
class Context:
    output_text: str = ""
    tool_evidence: list = field(default_factory=list)   # list[str]: 이번 턴 read/grep/exec paths+cmd
    user_input: str = ""

@dataclass
class Finding:
    detector: str
    would_block: bool
    mode: str            # report|soft|hard
    why: str
    detail: str = ""
    @property
    def blocking(self) -> bool:
        return self.would_block and self.mode == "hard"

REGISTRY: list = []
def register(d):
    REGISTRY.append(d); return d

def evaluate(ctx: Context, mode_overrides: dict | None = None) -> dict:
    mo = mode_overrides or {}
    findings = []
    for d in REGISTRY:
        for f in d.check(ctx):
            if d.id in mo:            # per-detector mode 승격/강등
                f.mode = mo[d.id]
            findings.append(f)
    return {"findings": findings,
            "exit_code": 2 if any(f.blocking for f in findings) else 0}
# ══════════════════════ CORE END (확장은 이 아래 register 만 추가) ══════════════════════


# ── detector KIND 1: evidence-scope (L1) — tool 증거의 범위충족 ──
class EvidenceScopeDetector:
    def __init__(self, id, patterns, required_scopes, mode="hard", why=""):
        self.id = id; self.mode = mode; self.why = why
        self._p = [re.compile(p) for p in patterns]; self.req = required_scopes
    def check(self, ctx: Context):
        if not any(p.search(ctx.output_text) for p in self._p):
            return []
        missing = [n for n, pred in self.req if not any(pred(e) for e in ctx.tool_evidence)]
        return [Finding(self.id, bool(missing), self.mode, self.why, f"missing_scopes={missing}")]

def _global_skills(e): return (("/.claude/skills" in e or ".codex/skills" in e)
                               and ("/home/" in e or e.strip().startswith("~") or "$HOME" in e))
def _project_skills(e): return ".claude/skills" in e and not _global_skills(e)

register(EvidenceScopeDetector(
    "skill_install_absence",
    [r"(미설치|설치[\s]*안[\s]*(됨|돼)|스킬[\s]*(이[\s]*)?없|not installed)"],
    [("project-local .claude/skills", _project_skills),
     ("global ~/.claude|~/.codex skills", _global_skills)],
    why="스킬/설치 부재 — project-local + global 둘 다 확인 필수(범위충족)."))

register(EvidenceScopeDetector(
    "capability_absence",
    [r"((codex|툴|도구).{0,25}(이미지[\s]*생성|image[\s_-]*gen).{0,10}(없|불가|안[\s]*됨|not|no)|"
     r"(이미지[\s]*생성).{0,10}기능.{0,6}(없|미지원))"],
    [("authoritative source (codex features / ~/.codex/skills)",
      lambda e: ("features" in e and "codex" in e) or (".codex/skills" in e))],
    why="능력 부재 — 권위 소스(features list/스킬) 확인 필수(--help 불충분)."))

# ── detector KIND 2: input-fidelity (L0) — 입력원이 다름(user_input) = 범용성 증거 ──
class InputFidelityDetector:
    id = "input_fidelity"; mode = "hard"
    why = "사용자 원문 지시어(리터럴 토큰: $skill·플래그) 보존 필수 — 치환/삭제 금지."
    def check(self, ctx: Context):
        ui = ctx.user_input or ""
        toks = set(re.findall(r"\$[A-Za-z_][\w-]*", ui)) | set(re.findall(r"(?:^|\s)(--?[A-Za-z][\w-]+)", ui))
        if not toks:
            return []
        surface = " ".join(ctx.tool_evidence) + " " + ctx.output_text   # 내가 실제 전달/수행한 표면
        dropped = sorted(t for t in toks if t not in surface)
        return [Finding(self.id, bool(dropped), self.mode, self.why, f"dropped={dropped}")]
register(InputFidelityDetector())

# ── detector KIND 3: calibration (L4) — 확신+무근거 → soft flag(입력원 또 다름) ──
class CalibrationDetector:
    id = "calibration"; mode = "soft"
    why = "확신 단정에 증거 포인터 없음 → 'Unverified'/hedge 권고(soft)."
    CONF = re.compile(r"(확실히|분명히|틀림없|반드시|100%)")
    PTR = re.compile(r"(:\d+|tool-use|features\s*list|sha256|realpath|`[^`]+:\d+`)")
    def check(self, ctx: Context):
        t = ctx.output_text
        if self.CONF.search(t) and not self.PTR.search(t):
            return [Finding(self.id, True, self.mode, self.why, "confident+no-evidence-pointer")]
        return []
register(CalibrationDetector())


# ══════════════ L1 확장 (4-layer 계약 2026-07-15): C1 부재/위치 · C3 부분→전체 · C4 허위완료 ══════════════
# ── C1: 일반 부재/위치 단정 — 검색/확인 증거 없이 '없다 / 여기 있다' (기존 skill/capability 특화의 상위 일반형) ──
class AbsenceLocationDetector:
    id = "absence_location"; mode = "hard"
    why = "부재/위치 단정 — 직전 검색(grep/glob/find/ls/read/realpath) 증거 필수(헌법 §3)."
    ABSENCE = re.compile(r"(존재하지\s*않|없습니다|없어요|없다\b|미구현|미등록|등록\s*안\s*(됨|돼)|"
                         r"not\s+found|does\s*not\s+exist|doesn't\s+exist|찾을\s*수\s*없)")
    LOCATION = re.compile(r"(cwd|현재\s*디렉|홈\s*디렉|\bHOME\b|경로에\s*(있|위치)|launch\s*dir|에\s*설치되어\s*있)")
    SEARCH_EV = ("grep", "glob", "find ", "ls ", "rg ", "read", "realpath", "cat ", "test -", "stat ", "which ")
    def check(self, ctx: Context):
        t = ctx.output_text
        if not (self.ABSENCE.search(t) or self.LOCATION.search(t)):
            return []
        has_search = any(any(s in e.lower() for s in self.SEARCH_EV) for e in ctx.tool_evidence)
        return [Finding(self.id, not has_search, self.mode, self.why,
                        f"absence/location claim; search_evidence={has_search}")]
register(AbsenceLocationDetector())

# ── C3: 부분→전체 과장 — '전부/모두/전건' 단정인데 확인 증거가 없거나 소수 ──
class WholeClaimDetector:
    id = "whole_claim"; mode = "soft"     # 범위 오판은 애매 → soft(경고) 시작
    why = "전체 단정('전부/모두/전건') — 확인 범위 vs 주장 범위 대조 필요(부분 확인으로 전수 단정 금지)."
    WHOLE = re.compile(r"(전부|모두\s*(통과|정상|완료|확인)|전건|전체\s*(통과|정상|다)|빠짐없이|하나도\s*빠짐없)")
    def check(self, ctx: Context):
        if not self.WHOLE.search(ctx.output_text):
            return []
        # 확인 증거가 2개 미만이면 전수 주장 근거 약함
        weak = len(ctx.tool_evidence) < 2
        return [Finding(self.id, weak, self.mode, self.why,
                        f"whole-scope claim; evidence_count={len(ctx.tool_evidence)}")]
register(WholeClaimDetector())

# ── C4: 허위 완료 — 'fresh 증거' 없이 완료/통과/배포/검증 단정(1주장=1증거) ──
class FakeCompletionDetector:
    id = "fake_completion"; mode = "hard"
    why = "완료/통과/배포/검증 단정 — fresh 증거(test·build·scan 원문 event) 필수(헌법 §4)."
    CLAIM = re.compile(r"(테스트\s*통과|빌드\s*(성공|통과)|배포\s*(됨|완료)|검증\s*(됨|완료)|"
                       r"모두\s*통과|smoke\s*(pass|통과)|정상\s*작동\s*확인|\bPASS\b)")
    FRESH_EV = ("pytest", "smoke", "py_compile", "npm test", "build", "bash tests", "test ",
                "scan", "grep", "exit=0", "pass", "compile")
    def check(self, ctx: Context):
        if not self.CLAIM.search(ctx.output_text):
            return []
        has_fresh = any(any(s in e.lower() for s in self.FRESH_EV) for e in ctx.tool_evidence)
        return [Finding(self.id, not has_fresh, self.mode, self.why,
                        f"completion claim; fresh_evidence={has_fresh}")]
register(FakeCompletionDetector())
# ── C5: liveness/진행 허위보고 — '진행 중/RUNNING/N%'인데 delta 증거 없이(pgrep -f 만) ──
#    근거: feedback_backup_monitor_liveness (example-project-a 백업 15h '진행 중 54%' 허위보고, pgrep -f 오탐)
class LivenessProgressDetector:
    id = "liveness_progress"; mode = "soft"     # 흔한 표현 → FP 회피 위해 soft
    why = "진행/생존 보고 — mtime·size 델타 등 fresh 진행증거 필수(pgrep -f 단독 금지)."
    LIVENESS = re.compile(r"(진행\s*중|정상\s*진행|계속\s*(실행|진행|돌아)|\bRUNNING\b|실행\s*중이|"
                          r"\d{1,3}\s*%\s*(완료|진행)|남았습니다|남음|살아\s*있)")
    DELTA_EV = ("mtime", "size", "델타", "delta", "stat ", "ls -l", "du ", "wc -l",
                "pgrep -x", "tail -f", "byte", "증가", "bytes")
    def check(self, ctx: Context):
        if not self.LIVENESS.search(ctx.output_text):
            return []
        has_delta = any(any(s in e.lower() for s in self.DELTA_EV) for e in ctx.tool_evidence)
        return [Finding(self.id, not has_delta, self.mode, self.why,
                        f"liveness/progress claim; delta_evidence={has_delta}")]
register(LivenessProgressDetector())
# ── C6: evidence-contract(도구권위) — 파생속성(FS타입·blocked) 단정에 '권위 도구' 증거 강제 ──
#    근거: feedback_measure_target_not_infer (heuristic/기억으로 단정 → 실측 대신). M1/M3 유형.
#    ⚠️ groundedness(L3)로 못 잡는 유형(주장이 '틀린 증거'에 grounded) — 도구권위는 정책검사라야 잡힘.
class ToolAuthorityDetector:
    id = "tool_authority"; mode = "soft"    # 보수적 soft(FP 회피, canary)
    why = "파생속성 단정 — 권위 도구 증거 필수(heuristic/기억 금지)."
    # FS 타입 주장(예: 'storage1은 ext4입니다')
    FS_CLAIM = re.compile(r"(ext[234]|xfs|btrfs|zfs|ntfs|vfat)\b|파일\s*시스템[은는이가]|파일시스템\s*타입|filesystem\s+is")
    FS_AUTH  = ("df -t", "findmnt", "lsblk", "/proc/mounts", "mount |")   # 권위(마운트 실측)
    FS_WEAK  = ("stat -f", "stat --file")                                  # heuristic(금지 단독)
    # 불가/blocked 주장
    BLOCKED  = re.compile(r"(불가능|blocked|막혀|못\s*(함|합니다|한다|해)|할\s*수\s*없|권한\s*없|"
                          r"sudo\s*(가\s*)?필요|관리자\s*필요|impossible|permission\s+denied)")
    ATTEMPT  = ("error", "denied", "실패", "failed", "exit=", "timeout", "traceback",
                "refused", "cannot", "→", "no such", "not found")
    def check(self, ctx: Context):
        t = ctx.output_text; ev = " ".join(ctx.tool_evidence).lower(); out = []
        if self.FS_CLAIM.search(t):
            has_auth = any(a in ev for a in self.FS_AUTH)
            only_weak = (not has_auth) and any(w in ev for w in self.FS_WEAK)
            out.append(Finding(self.id, not has_auth, self.mode,
                               self.why + " (FS타입=df/findmnt/lsblk, stat 단독 금지)",
                               f"FS-type claim; authoritative={has_auth}; weak_only={only_weak}"))
        if self.BLOCKED.search(t):
            has_attempt = any(a in ev for a in self.ATTEMPT)
            out.append(Finding(self.id, not has_attempt, self.mode,
                               self.why + " (blocked=실제 시도+오류로그 필수)",
                               f"blocked/impossible claim; attempt_evidence={has_attempt}"))
        return out
register(ToolAuthorityDetector())
# ── C7: 명시 도구지시 치환(평문) — "X으로 그려/만들어"의 X를 다른 걸로 치환 금지 ──
#    근거: feedback_literal_input_and_full_scope(E5). input_fidelity($토큰)의 평문 확장(Q2 no-$).
class ExplicitToolRequestDetector:
    id = "explicit_tool_request"; mode = "soft"
    why = "사용자 명시 도구(X으로 그려/만들어)를 다른 것으로 치환 금지 — 지시어 존중(불응 시 1줄 확인)."
    # X=ASCII 도구명(한글 일반명사 '방법' 등 배제) + 생성/작도 동사
    #   ⚠️ 도구명은 ASCII 전용([A-Za-z0-9.+_-]) — \w는 한글 매칭해 '으로'를 캡처에 흡수함(오탐).
    REQ = re.compile(r"([A-Za-z][A-Za-z0-9.+_-]{1,})\s*(?:으로|로)[^.\n]{0,30}?"
                     r"(그려|그리|만들|생성|작성|렌더|draw|generate|plot|render)")
    def check(self, ctx: Context):
        m = self.REQ.search(ctx.user_input or "")
        if not m:
            return []
        tool = m.group(1).lower()
        surface = (" ".join(ctx.tool_evidence) + " " + ctx.output_text).lower()
        dropped = tool not in surface
        return [Finding(self.id, dropped, self.mode, self.why,
                        f"requested_tool={tool!r}; preserved={not dropped}")]
register(ExplicitToolRequestDetector())

# ── C8: machine-attribution provenance — 머신별 측정/귀속 주장에 그 머신 실측 증거 강제 (M4) ──
#    근거: feedback_measure_target_not_infer (한 머신 관측을 다른 머신에 교차이식). groundedness 못 잡음.
class MachineAttributionDetector:
    id = "machine_attribution"; mode = "soft"
    why = "머신별 측정/귀속 주장 — 그 머신에서 실측한 증거 필수(교차이식 금지)."
    MACHINES = ("server-a", "server-b", "notebook", "workstation", "local")  # 예시 — 환경에 맞게 수정
    # 측정/인과 귀속 트리거(단순 '에서' 배제 — FP 회피)
    ATTR = re.compile(r"(때문|원인|\d+\s*(초|분|ms|시간|밀리초)|측정[^\n]{0,6}(값|결과)|"
                      r"느림|빠름|지연|import\s|속도)")
    def check(self, ctx: Context):
        t = ctx.output_text
        claim_m = [m for m in self.MACHINES if m in t]
        if not claim_m or not self.ATTR.search(t):
            return []
        ev = " ".join(ctx.tool_evidence).lower()
        missing = [m for m in claim_m if m not in ev]
        return [Finding(self.id, bool(missing), self.mode, self.why,
                        f"claim_machines={claim_m}; unverified_on={missing}")]
register(MachineAttributionDetector())
# ══════════════ L1 확장 END ══════════════


def detector_kinds():
    return sorted({type(d).__name__ for d in REGISTRY})


def _main():
    """hook 용: stdin JSON {output_text,user_input,tool_evidence} → findings JSON.
    report-mode(canary): 계산만 하고 exit 0. (hard 승격 시 hook 이 exit_code 를 존중.)"""
    import sys, json
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        print(json.dumps({"findings": [], "exit_code": 0, "err": "bad-json"})); return 0
    ctx = Context(output_text=payload.get("output_text", ""),
                  user_input=payload.get("user_input", ""),
                  tool_evidence=list(payload.get("tool_evidence", [])))
    r = evaluate(ctx)
    # ⚠️ report-only(canary): serialized exit_code=0(machine-safe) — 소비자가 우연히 차단 활성화 못 하게.
    #    가정적 판정은 would_exit_code 로만 노출. 실제 hard 강제는 별도 승인된 활성화 설정 필요(codex r54 #2).
    out = {"findings": [{"detector": f.detector, "would_block": f.would_block,
                          "mode": f.mode, "would_block_hard": f.blocking, "detail": f.detail} for f in r["findings"]],
           "exit_code": 0, "would_exit_code": r["exit_code"], "report_only": True}
    print(json.dumps(out, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    import sys; sys.exit(_main())
