"""debate_manager.py — Claude ↔ Codex 다턴 토론 엔진 (v2.5.0+).

목적:
- 기존 v2.4.7 의 1 회 교환 (c- → /codex:adversarial-review → x-) 한계 극복.
- 양측이 서로 반박·재반박·합의 형성까지 여러 턴 주고받음.

핵심 설계:
- **최소 2 턴 강제** (조기 종료 방지 — 1 회 교환보다 의미있는 상호작용 보장).
- 기본 3 턴, 최대 5 턴.
- 각 턴은 c-측(Claude) + x-측(Codex) 페어 교환 1 회.
- 수렴 감지 (no-finding, 입장 불변, max turn 초과).
- 공유 메모리 (jsonl) + 감사 로그.

사용자 요구 (2026-04-19):
> "debate 의 경우 iteration 이 최소 2~3 회는 이상이어야만 해."

구현:
- min_turns = 2 (하드 하한)
- default_turns = 3 (사용자 요구 중앙값)
- max_turns = 5 (무한 루프 방지)

의존성:
- Task 도구 (Claude 측 응답) — 실제 호출은 Claude Code 내에서
- /codex:rescue 슬래시 명령 (Codex 측 응답)
- 이 모듈은 **프로토콜 레이어** 만 담당. 실제 LLM 호출은 외부 integration.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────
# 토론 설정 (v2.5.0 기본값)
# ─────────────────────────────────────────────────────────────

MIN_TURNS = 2          # 사용자 요구: 최소 2 턴 강제
DEFAULT_TURNS = 3      # 사용자 요구: 권장 3 턴
MAX_TURNS = 5          # 무한 루프 방지

# 수렴 감지 키워드 (x-측 응답에서 발견 시 수렴 후보)
CONVERGENCE_MARKERS = [
    "no finding",
    "no issues found",
    "agree with",
    "accept the proposal",
    "수렴",
    "합의",
    "동의",
]


# ─────────────────────────────────────────────────────────────
# Turn / Debate 데이터 클래스
# ─────────────────────────────────────────────────────────────

@dataclass
class Turn:
    """토론의 1 턴 = c-측 응답 + x-측 응답 1 쌍."""
    turn_no: int
    c_agent: str
    c_content: str
    c_timestamp: str
    x_agent: str
    x_content: str
    x_timestamp: str
    finding_count: int = 0  # x 측이 제기한 새 findings 수
    convergence_signal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DebateSession:
    """토론 전체 세션 기록."""
    debate_id: str
    topic: str
    c_agent_name: str       # 예: "c-proposer"
    x_agent_name: str       # 예: "x-proposer"
    min_turns: int = MIN_TURNS
    target_turns: int = DEFAULT_TURNS
    max_turns: int = MAX_TURNS
    turns: list[Turn] = field(default_factory=list)
    status: str = "active"  # active | converged | max_turns_reached | unresolved
    started_at: str = ""
    ended_at: str = ""
    consensus: Optional[str] = None
    unresolved_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["turns"] = [t.to_dict() for t in self.turns]
        return d


# ─────────────────────────────────────────────────────────────
# DebateManager — 토론 엔진
# ─────────────────────────────────────────────────────────────

class DebateManager:
    """Claude ↔ Codex 다턴 토론 관리자.

    사용 패턴:
        dm = DebateManager(workspace=".claude")
        session = dm.start_debate(
            topic="평균회귀 vs 추세추종 선택",
            c_agent="c-proposer",
            x_agent="x-proposer",
            target_turns=3,
        )

        for _ in range(session.max_turns):
            c_resp = some_claude_call(session)  # Task(c-proposer, ...)
            x_resp = some_codex_call(session)   # /codex:rescue ...
            dm.record_turn(session, c_resp, x_resp)
            if dm.check_convergence(session):
                break

        final = dm.finalize(session)
        # final == {"consensus": ..., "unresolved": [...], "audit_log": "..."}
    """

    def __init__(self, workspace: str | Path = ".claude"):
        self.workspace = Path(workspace)
        self.debate_dir = self.workspace / "debate"
        self.debate_dir.mkdir(parents=True, exist_ok=True)

    def start_debate(
        self,
        topic: str,
        c_agent: str,
        x_agent: str,
        target_turns: int = DEFAULT_TURNS,
        min_turns: int = MIN_TURNS,
        max_turns: int = MAX_TURNS,
    ) -> DebateSession:
        """새 토론 세션 시작.

        Args:
            topic: 토론 주제 (한 문장)
            c_agent: Claude 측 에이전트 이름 (예: "c-proposer")
            x_agent: Codex 측 에이전트 이름 (예: "x-proposer")
            target_turns: 권장 턴 수 (기본 3)
            min_turns: 최소 턴 수 (기본 2, 하드 하한)
            max_turns: 최대 턴 수 (기본 5)

        Returns:
            새 DebateSession (status="active")
        """
        # 하한 강제
        if min_turns < MIN_TURNS:
            raise ValueError(
                f"min_turns 는 {MIN_TURNS} 이상이어야 합니다 "
                f"(사용자 정책: 최소 2 턴). 받은 값: {min_turns}"
            )
        if target_turns < min_turns:
            target_turns = min_turns
        if max_turns < target_turns:
            max_turns = target_turns

        debate_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        session = DebateSession(
            debate_id=debate_id,
            topic=topic,
            c_agent_name=c_agent,
            x_agent_name=x_agent,
            min_turns=min_turns,
            target_turns=target_turns,
            max_turns=max_turns,
            started_at=now,
        )
        self._persist(session)
        return session

    def record_turn(
        self,
        session: DebateSession,
        c_content: str,
        x_content: str,
        finding_count: int | None = None,
    ) -> Turn:
        """1 턴 기록. c-측과 x-측 응답 모두 포함.

        Args:
            session: 진행 중 세션
            c_content: c-agent (Claude) 응답 전체
            x_content: x-agent (Codex) 응답 전체
            finding_count: x 측이 제기한 new finding 수 (None 면 자동 추정)

        Returns:
            생성된 Turn 객체
        """
        if session.status != "active":
            raise RuntimeError(
                f"Debate {session.debate_id} 이미 종료됨 (status={session.status})"
            )

        turn_no = len(session.turns) + 1
        now = datetime.now(timezone.utc).isoformat()

        # finding_count 자동 추정 (x 측 응답 기반)
        if finding_count is None:
            finding_count = self._estimate_finding_count(x_content)

        # 수렴 신호 감지
        convergence_signal = self._detect_convergence_signal(x_content)

        turn = Turn(
            turn_no=turn_no,
            c_agent=session.c_agent_name,
            c_content=c_content,
            c_timestamp=now,
            x_agent=session.x_agent_name,
            x_content=x_content,
            x_timestamp=now,
            finding_count=finding_count,
            convergence_signal=convergence_signal,
        )
        session.turns.append(turn)
        self._persist(session)
        return turn

    def check_convergence(self, session: DebateSession) -> bool:
        """현재 session 이 수렴했는지 판단.

        수렴 조건 (AND):
        1. min_turns 이상 진행됨 (하한 보장)
        2. 아래 중 하나 충족:
           a) 마지막 턴이 convergence_signal=True + finding_count=0
           b) 2 턴 연속 finding_count=0
           c) target_turns 도달 + 마지막 턴 finding_count <= 1
        """
        turns = session.turns
        if len(turns) < session.min_turns:
            return False

        last = turns[-1]

        # (a) 명확한 수렴 신호
        if last.convergence_signal and last.finding_count == 0:
            return True

        # (b) 2 연속 zero findings
        if len(turns) >= 2:
            prev = turns[-2]
            if last.finding_count == 0 and prev.finding_count == 0:
                return True

        # (c) target_turns 도달 + 낮은 finding
        if len(turns) >= session.target_turns and last.finding_count <= 1:
            return True

        return False

    def check_timeout(self, session: DebateSession) -> bool:
        """max_turns 초과 여부."""
        return len(session.turns) >= session.max_turns

    def finalize(
        self,
        session: DebateSession,
        consensus: str | None = None,
        unresolved: list[str] | None = None,
    ) -> dict[str, Any]:
        """토론 종료 + 최종 결과 반환.

        Args:
            session: 진행한 세션
            consensus: 합의 내용 (None 이면 마지막 c-content 요약)
            unresolved: 미해결 항목 (None 이면 마지막 x-finding 기반 추정)

        Returns:
            {
                "debate_id": ...,
                "status": "converged" | "max_turns_reached" | "unresolved",
                "turns": int,
                "consensus": "...",
                "unresolved": [...],
                "audit_log_path": ".claude/debate/D-*.jsonl",
            }
        """
        if self.check_convergence(session):
            session.status = "converged"
        elif self.check_timeout(session):
            session.status = "max_turns_reached"
        else:
            session.status = "unresolved"

        session.ended_at = datetime.now(timezone.utc).isoformat()

        # consensus 추출 (사용자 미지정 시)
        if consensus is None and session.turns:
            last_c = session.turns[-1].c_content
            # 단순 요약 (앞 500 자)
            consensus = last_c[:500] + ("..." if len(last_c) > 500 else "")
        session.consensus = consensus

        # unresolved 추출 (사용자 미지정 시)
        if unresolved is None and session.turns:
            last = session.turns[-1]
            if last.finding_count > 0 and session.status != "converged":
                # 마지막 x-content 의 findings 파싱 (단순 추출)
                unresolved = self._extract_findings(last.x_content)
            else:
                unresolved = []
        session.unresolved_items = unresolved or []

        self._persist(session)

        audit_path = self.debate_dir / f"{session.debate_id}.jsonl"
        return {
            "debate_id": session.debate_id,
            "status": session.status,
            "turns": len(session.turns),
            "min_turns": session.min_turns,
            "target_turns": session.target_turns,
            "consensus": session.consensus,
            "unresolved": session.unresolved_items,
            "audit_log_path": str(audit_path),
        }

    def load_session(self, debate_id: str) -> DebateSession | None:
        """기존 세션 로드 (감사·분석용)."""
        path = self.debate_dir / f"{debate_id}.jsonl"
        if not path.exists():
            return None
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return None
        # 마지막 상태 사용 (라인마다 overwrite 가 아닌 단일 JSON 형식)
        data = json.loads(lines[-1])
        # dataclass 역직렬화
        turns = [Turn(**t) for t in data.pop("turns", [])]
        session = DebateSession(**data)
        session.turns = turns
        return session

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """최근 토론 세션 요약 목록."""
        files = sorted(
            self.debate_dir.glob("D-*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        result = []
        for f in files:
            try:
                session = self.load_session(f.stem)
                if session:
                    result.append({
                        "debate_id": session.debate_id,
                        "topic": session.topic[:80],
                        "turns": len(session.turns),
                        "status": session.status,
                        "started_at": session.started_at,
                    })
            except Exception:
                continue
        return result

    # ─────────────────────────────────────────────────────────
    # 내부 유틸
    # ─────────────────────────────────────────────────────────

    def _generate_id(self) -> str:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        # 같은 날 내 순번
        existing = list(self.debate_dir.glob(f"D-{date_str}-*.jsonl"))
        seq = len(existing) + 1
        return f"D-{date_str}-{seq:02d}"

    def _persist(self, session: DebateSession) -> None:
        path = self.debate_dir / f"{session.debate_id}.jsonl"
        # 현재 상태를 마지막 라인으로 append (감사 로그)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(session.to_dict(), ensure_ascii=False) + "\n")

    def _estimate_finding_count(self, x_content: str) -> int:
        """x-측 응답에서 finding 수 추정.

        휴리스틱:
        - bullet list 항목 (- 또는 * 로 시작)
        - 번호 매긴 리스트 (1. 2. 등)
        - "no finding" 이면 0
        """
        content_lower = x_content.lower()
        if any(m in content_lower for m in ["no finding", "no issues", "no new"]):
            return 0
        # bullet / numbered list count
        lines = x_content.strip().splitlines()
        bullets = sum(
            1 for line in lines
            if line.strip().startswith(("-", "*", "•"))
            or (len(line.strip()) > 2 and line.strip()[0].isdigit()
                and line.strip()[1] in ".)")
        )
        return bullets

    def _detect_convergence_signal(self, x_content: str) -> bool:
        """convergence 마커 발견 여부."""
        lower = x_content.lower()
        return any(marker in lower for marker in CONVERGENCE_MARKERS)

    def _extract_findings(self, x_content: str) -> list[str]:
        """x-content 에서 finding bullet 들 추출."""
        findings = []
        for line in x_content.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")):
                findings.append(stripped.lstrip("-*• ").strip()[:200])
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)":
                findings.append(stripped[2:].strip()[:200])
        return findings[:10]  # 최대 10 개


# ─────────────────────────────────────────────────────────────
# CLI (검증·감사용)
# ─────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Debate manager CLI (v2.5.0)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="최근 토론 세션 목록")

    show = sub.add_parser("show", help="세션 상세 보기")
    show.add_argument("debate_id")

    demo = sub.add_parser("demo", help="데모 토론 (가상 3 턴)")
    demo.add_argument("--turns", type=int, default=DEFAULT_TURNS)

    args = parser.parse_args()
    dm = DebateManager()

    if args.cmd == "list":
        sessions = dm.list_sessions()
        if not sessions:
            print("(아직 토론 기록 없음)")
            return
        print(f"최근 {len(sessions)} 세션:\n")
        for s in sessions:
            print(f"  {s['debate_id']}  {s['status']:20s}  {s['turns']} 턴  — {s['topic']}")

    elif args.cmd == "show":
        session = dm.load_session(args.debate_id)
        if not session:
            print(f"❌ {args.debate_id} 없음")
            return
        print(f"\n토론 {session.debate_id}")
        print(f"  주제: {session.topic}")
        print(f"  상태: {session.status}")
        print(f"  턴 수: {len(session.turns)} (min={session.min_turns}, target={session.target_turns})")
        for t in session.turns:
            print(f"\n  Turn {t.turn_no}:")
            print(f"    [{t.c_agent}] {t.c_content[:150]}...")
            print(f"    [{t.x_agent}] {t.x_content[:150]}...")
            print(f"    findings={t.finding_count}, convergence_signal={t.convergence_signal}")

    elif args.cmd == "demo":
        session = dm.start_debate(
            topic="데모 주제 — 평균회귀 vs 추세추종",
            c_agent="c-proposer",
            x_agent="x-proposer",
            target_turns=args.turns,
        )
        demo_turns = [
            ("평균회귀 전략 제안: sharpe 1.8, max DD 12%.",
             "- look-ahead bias 의심\n- slippage 0 가정\n- regime shift 대응 없음"),
            ("look-ahead 증명 완료. slippage 0.1% 반영 시 sharpe 1.4.",
             "- slippage 1.4 도 marginal\n- regime shift 대응 추가 필요"),
            ("regime detector 추가. volatility 상승 시 포지션 절반 축소.",
             "no finding — 합의."),
        ]
        for c, x in demo_turns[:args.turns]:
            dm.record_turn(session, c, x)
            if dm.check_convergence(session):
                break
        result = dm.finalize(session)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
