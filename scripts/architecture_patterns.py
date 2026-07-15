"""architecture_patterns.py — Composite Architecture (v2.5.0+).

대규모 복합 프로젝트를 위한 다중 패턴 공존 시스템.

기존 v2.4.7 은 표준 4 페어 + 도메인 N 페어 고정 생성.
v2.5.0 은 6 패턴 (core/investigation/expert_pool/debate/pipeline/hierarchical)
을 모두 생성하고, STEP 진행에 따라 활성 패턴이 전환.

핵심 원칙:
1. c-/x- 쌍 구조 **절대 유지** (Claude↔Codex 비대칭 검증 보호)
2. 에이전트는 bootstrap 시 **전부 eager 생성** (~36 개)
3. Task 호출은 STEP 활성 패턴에 한정 (context 절약)
4. 사용자가 활성 패턴 명시 가능 ("이번 STEP 에 Debate 도 써줘")
"""
from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────
# 패턴 정의 — 6 개 아키텍처 패턴
# ─────────────────────────────────────────────────────────────
#
# 각 패턴은:
#   - pairs: [(kind, pair_id, display, c_role, x_role), ...]
#   - active_steps: "always" 또는 [STEP 번호 목록]
#   - debate_enabled: True 면 STEP 진입 시 토론 엔진 사용 권고
#
# kind 는 에이전트 파일명 (c-{kind}.md, x-{kind}.md) 을 결정.

PATTERNS: dict[str, dict[str, Any]] = {

    # Core — 모든 STEP 에서 활성 (조율·품질·방법론)
    "core": {
        "display": "Core (조율·QA·방법론)",
        "emoji": "🛠",
        "pairs": [
            (
                "lead", "PAIR-LEAD", "Lead & Orchestrator",
                ["전체 조율·플래닝·통합 답변", "STEP 간 의존성 관리"],
                ["전체 설계의 근본 가정", "도메인 간 우선순위 편향"],
            ),
            (
                "qa", "PAIR-QA", "Boundary QA",
                [
                    "도메인 간 경계면 정합성 검증 (incremental)",
                    "단위·스케일·시공간 해상도 일치 확인",
                    "한 도메인 출력 ↔ 다른 도메인 입력 shape 검증",
                ],
                ["경계에서의 정보 손실", "회귀·음성 경로", "silent failure mode"],
            ),
            (
                "methods", "PAIR-METHODS", "Methodology & Statistics",
                ["평가 프로토콜·통계 검정·ground truth 정의"],
                ["다중 비교·p-hacking·ground truth 주관성"],
            ),
        ],
        "active_steps": "always",
        "debate_enabled": False,
    },

    # Investigation — STEP 2 (리서치) 전용
    # 가설-증거-종합 3 단 구조로 리서치 수행
    "investigation": {
        "display": "Investigation (가설-증거-종합)",
        "emoji": "🔍",
        "pairs": [
            (
                "hypothesis", "PAIR-HYP", "Hypothesis Formulation",
                [
                    "연구 질문에 대한 구체 가설 제안",
                    "반증 가능한 형태로 작성",
                    "선행 연구 기반 정당화",
                ],
                [
                    "가설이 반증 불가능한 형태",
                    "cherry-picked 선행 연구",
                    "암묵적 가정 누락",
                ],
            ),
            (
                "evidence", "PAIR-EVD", "Evidence Collection",
                [
                    "1차 출처·논문·데이터 수집",
                    "출처별 신뢰도 평가",
                    "발산하는 출처 표시",
                ],
                [
                    "2 차 요약만 인용",
                    "단일 저자·연구소 의존",
                    "출판 편향 미반영",
                ],
            ),
            (
                "synthesis", "PAIR-SYN", "Synthesis & Convergence",
                [
                    "수렴·발산 지점 명시",
                    "공백 영역 표시",
                    "RESEARCH.md 구조로 정리",
                ],
                [
                    "확증 편향 재현",
                    "발산을 과소·과대 평가",
                    "출처 간 연결 미흡",
                ],
            ),
        ],
        "active_steps": ["STEP_2"],
        "debate_enabled": True,  # 가설↔증거 토론 활성
    },

    # Expert Pool — 도메인별 전문가 병렬 (STEP 1, 3, 6)
    # pairs 는 도메인 자동 판별 결과로 동적 생성 (build_composite_agents 에서 주입)
    "expert_pool": {
        "display": "Expert Pool (도메인 전문가)",
        "emoji": "⚡",
        "pairs": [],  # 동적 주입
        "active_steps": ["STEP_1", "STEP_3", "STEP_6"],
        "debate_enabled": False,
    },

    # Debate — STEP 3, 4, 6 의사결정 구간
    # 제안 → 반박 → 조정 3 축
    "debate": {
        "display": "Debate (토론·합의)",
        "emoji": "⚔️",
        "pairs": [
            (
                "proposer", "PAIR-PROP", "Proposer",
                [
                    "구체 안 제시 + 정당화 근거",
                    "trade-off 명시",
                    "대안 안 최소 1 개",
                ],
                [
                    "같은 안을 다른 프레임으로 재제시",
                    "trade-off 중 한쪽 과소평가",
                    "대안 검토 피상적",
                ],
            ),
            (
                "challenger", "PAIR-CHAL", "Challenger",
                [
                    "제안의 약점·실패 조건 발굴",
                    "반례 구성",
                    "숨은 가정 노출",
                ],
                [
                    "이미 알려진 약점 반복",
                    "반례가 비현실적",
                    "대안 제시 (역할 이탈)",
                ],
            ),
            (
                "mediator", "PAIR-MED", "Mediator",
                [
                    "양측 주장 요약",
                    "합의 가능한 지점 도출",
                    "미해결 항목 후속 이슈로 기록",
                ],
                [
                    "한쪽 편향 합의",
                    "미해결을 합의된 것으로 왜곡",
                    "합의 강요 (시간 압박)",
                ],
            ),
        ],
        "active_steps": ["STEP_3", "STEP_4", "STEP_6"],
        "debate_enabled": True,  # 토론 엔진 강제
    },

    # Pipeline — STEP 5 순차 구현
    # 데이터 수집 → 피처 → 모델 → 배포 4 단
    "pipeline": {
        "display": "Pipeline (순차 구현)",
        "emoji": "🔗",
        "pairs": [
            (
                "ingest", "PAIR-ING", "Data Ingest",
                [
                    "데이터 소스 연결·수집·검증",
                    "스키마·형식 표준화",
                    "에러·결측 정책",
                ],
                [
                    "스로틀링·rate limit 미대응",
                    "스키마 변경 감지 누락",
                    "재시도 로직 부재",
                ],
            ),
            (
                "feature", "PAIR-FEA", "Feature Engineering",
                [
                    "피처 계산·변환·집계",
                    "시간 정합성 (look-ahead 방지)",
                    "결측·이상치 처리",
                ],
                [
                    "Look-ahead bias",
                    "피처 누수 (target leakage)",
                    "train/val 분포 차이 무시",
                ],
            ),
            (
                "model", "PAIR-MDL", "Model Training",
                [
                    "모델 학습·검증·선택",
                    "하이퍼파라미터 탐색",
                    "재현성 확보 (seed, env)",
                ],
                [
                    "과적합 (overfitting)",
                    "검증 세트 오염",
                    "베이스라인 대비 평가 누락",
                ],
            ),
            (
                "serve", "PAIR-SRV", "Deployment & Serving",
                [
                    "모델 배포·모니터링",
                    "성능 저하 감지 (drift)",
                    "롤백 메커니즘",
                ],
                [
                    "프로덕션 학습 분포 괴리",
                    "로그·메트릭 부재",
                    "버전 관리 실패",
                ],
            ),
        ],
        "active_steps": ["STEP_5"],
        "debate_enabled": False,
    },

    # Hierarchical — STEP 5 대규모 복합 구현
    # 아키텍트 → 통합자 2 단
    "hierarchical": {
        "display": "Hierarchical (계층·통합)",
        "emoji": "🏗",
        "pairs": [
            (
                "architect", "PAIR-ARC", "System Architect",
                [
                    "모듈 경계·API 계약 설계",
                    "의존성 그래프 명시",
                    "확장성·운영성 고려",
                ],
                [
                    "과도한 추상화",
                    "경계 불명확 (blob)",
                    "실제 구현 가능성 미검증",
                ],
            ),
            (
                "integrator", "PAIR-INT", "Integration Coordinator",
                [
                    "모듈 통합·E2E 검증",
                    "의존성 병목 제거",
                    "배포 오케스트레이션",
                ],
                [
                    "통합 실패 시 원인 모호",
                    "버전 불일치 누락",
                    "종속성 순환",
                ],
            ),
        ],
        "active_steps": ["STEP_5"],
        "debate_enabled": False,
    },
}


# ─────────────────────────────────────────────────────────────
# STEP ↔ 활성 패턴 매핑 (기본값)
# ─────────────────────────────────────────────────────────────

DEFAULT_STEP_PATTERNS: dict[str, list[str]] = {
    "STEP_0": ["core"],
    "STEP_1": ["core", "expert_pool"],
    "STEP_2": ["core", "investigation"],
    "STEP_3": ["core", "expert_pool", "debate"],
    "STEP_4": ["core", "debate"],
    "STEP_5": ["core", "pipeline", "hierarchical"],
    "STEP_5_5": ["core"],  # 경계 QA
    "STEP_6": ["core", "expert_pool", "debate"],
}


def get_active_patterns(step: str) -> list[str]:
    """현재 STEP 의 활성 패턴 목록 반환.

    Args:
        step: "STEP_0" ~ "STEP_6" 형식 문자열

    Returns:
        활성 패턴 이름 목록 (core 는 항상 포함)
    """
    step_normalized = step.upper().replace(" ", "_").replace("-", "_")
    if not step_normalized.startswith("STEP_"):
        step_normalized = f"STEP_{step_normalized}"
    patterns = DEFAULT_STEP_PATTERNS.get(step_normalized, ["core"])
    return patterns


def get_pattern_agents(pattern_name: str) -> list[str]:
    """특정 패턴의 모든 에이전트 이름 목록 (c-*/x-* 전부).

    Returns:
        ["c-lead", "x-lead", "c-qa", "x-qa", ...]
    """
    pattern = PATTERNS.get(pattern_name)
    if not pattern:
        return []
    agents: list[str] = []
    for pair in pattern.get("pairs", []):
        kind = pair[0]
        agents.extend([f"c-{kind}", f"x-{kind}"])
    return agents


def get_active_agents(step: str, domains: list[str] | None = None) -> list[str]:
    """현재 STEP 에서 호출 가능한 모든 에이전트 목록.

    Args:
        step: "STEP_0" ~ "STEP_6"
        domains: 활성 도메인 목록 (expert_pool 패턴에 주입)

    Returns:
        에이전트 이름 목록 (c-* / x-* 섞여 있음)
    """
    patterns = get_active_patterns(step)
    agents: list[str] = []
    for pname in patterns:
        if pname == "expert_pool" and domains:
            for domain in domains:
                # 도메인 이름이 곧 kind (예: crypto_trading → market, strategy, risk)
                # build_composite_agents 에서 별도 주입됨
                agents.extend([f"c-{domain}", f"x-{domain}"])
        else:
            agents.extend(get_pattern_agents(pname))
    return agents


# ─────────────────────────────────────────────────────────────
# Composite Architecture 생성 엔진
# ─────────────────────────────────────────────────────────────

def build_composite_agents(
    domains: list[str],
    domain_entries: dict[str, dict[str, Any]] | None = None,
    project_name: str = "(미지정)",
) -> list[dict[str, Any]]:
    """Composite 에이전트 전체 목록 생성.

    Args:
        domains: 활성 도메인 목록 (예: ["crypto_trading", "quantitative_strategy", "risk_management"])
        domain_entries: DOMAIN_CATALOG + dynamic 도메인 엔트리 (assumptions·terms·checklist 제공)
        project_name: 프로젝트 이름

    Returns:
        에이전트 스펙 목록. 각 원소:
            {
                "kind": "market",
                "pair_id": "PAIR-MARKET",
                "display": "Cryptocurrency Trading",
                "pattern": "expert_pool",
                "c_role": [...],
                "x_role": [...],
                "assumptions": [...],     # expert_pool 인 경우
                "critical_checklist": [...],
                "key_terms": {...},
            }
    """
    specs: list[dict[str, Any]] = []

    # 1. 고정 패턴들 (core, investigation, debate, pipeline, hierarchical)
    for pattern_name, pattern in PATTERNS.items():
        if pattern_name == "expert_pool":
            continue  # 도메인 기반 동적 생성
        for kind, pair_id, display, c_role, x_role in pattern["pairs"]:
            specs.append({
                "kind": kind,
                "pair_id": pair_id,
                "display": display,
                "pattern": pattern_name,
                "c_role": c_role,
                "x_role": x_role,
                "assumptions": [],
                "critical_checklist": [],
                "key_terms": {},
                "project_name": project_name,
            })

    # 2. Expert Pool — 도메인마다 1 페어
    for domain_key in domains:
        entry = (domain_entries or {}).get(domain_key, {})
        display = entry.get("display", domain_key.replace("_", " ").title())
        pair_id = f"PAIR-{domain_key.upper().replace('_', '-')[:12]}"
        # kind 는 domain_key 의 마지막 단어 (crypto_trading → market 처럼 간결하게)
        # 하지만 사용자가 기대하는 것은 도메인 이름 자체이므로 그대로 사용
        kind = _domain_to_kind(domain_key)
        specs.append({
            "kind": kind,
            "pair_id": pair_id,
            "display": display,
            "pattern": "expert_pool",
            "c_role": [f"{display} 도메인의 1차 설계·분석·구현 결과물"],
            "x_role": [f"{display} 결과물의 약점·반례·숨은 가정 발굴"],
            "assumptions": entry.get("assumptions", []),
            "critical_checklist": entry.get("critical_review_checklist", []),
            "key_terms": entry.get("key_terms", {}),
            "project_name": project_name,
        })

    return specs


def _domain_to_kind(domain_key: str) -> str:
    """도메인 키를 에이전트 kind 로 변환.

    예: crypto_trading → market (첫 단어 + 추상화)
        quantitative_strategy → strategy
        risk_management → risk

    단순 규칙: 마지막 밑줄 이후 단어 사용 (명확한 도메인 이름).
    """
    # 잘 알려진 매핑
    mapping = {
        "crypto_trading": "market",
        "quantitative_strategy": "strategy",
        "risk_management": "risk",
        "sar": "sar",
        "ai": "ai",
        "ml": "ml",
        "volcanology": "volc",
        "volc": "volc",
        "insar": "insar",
        "geodesy": "geodesy",
        "remote_sensing": "sensing",
    }
    if domain_key in mapping:
        return mapping[domain_key]
    # 기본: 마지막 밑줄 뒤 단어
    parts = domain_key.split("_")
    return parts[-1][:12]  # 최대 12 자


def render_composite_agent_markdown(
    spec: dict[str, Any],
    side: str = "c",  # "c" or "x"
) -> str:
    """Composite 에이전트의 .md 파일 내용 생성.

    Args:
        spec: build_composite_agents 반환값의 1 원소
        side: "c" (constructive) or "x" (critical)

    Returns:
        markdown 문자열
    """
    kind = spec["kind"]
    pair_id = spec["pair_id"]
    display = spec["display"]
    pattern = spec["pattern"]
    project_name = spec.get("project_name", "(미지정)")

    pattern_info = PATTERNS.get(pattern, {})
    pattern_display = pattern_info.get("display", pattern)
    pattern_emoji = pattern_info.get("emoji", "")

    if side == "c":
        role_list = spec.get("c_role", [])
        primary_mode = "constructive"
        header_icon = "🔵"
        peer_side = "x"
        llm_label = "Claude"
    else:
        role_list = spec.get("x_role", [])
        primary_mode = "critical"
        header_icon = "🟢"
        peer_side = "c"
        llm_label = "Codex"

    role_md = "\n".join(f"- {r}" for r in role_list) or "- (역할 기술 없음)"

    assumptions = spec.get("assumptions", [])
    assumptions_md = "\n".join(f"- {a}" for a in assumptions)
    checklist = spec.get("critical_checklist", [])
    checklist_md = "\n".join(f"- {c}" for c in checklist)
    terms = spec.get("key_terms", {})
    terms_md = "\n".join(f"- **{t}**: {m}" for t, m in terms.items())

    # 활성 STEP 표시
    active_steps = pattern_info.get("active_steps", "always")
    if active_steps == "always":
        steps_str = "**모든 STEP** (항상 활성)"
    else:
        steps_str = ", ".join(active_steps)

    # 토론 엔진 명시
    debate_enabled = pattern_info.get("debate_enabled", False)
    debate_note = ""
    if debate_enabled and side == "x":
        debate_note = (
            f"\n## 토론 엔진 (v2.5.0+)\n\n"
            f"이 에이전트는 `debate_manager` 로 다턴 토론이 가능하다.\n"
            f"기본 **최소 2 턴, 권장 3 턴, 최대 5 턴**. 수렴 시 조기 종료.\n"
            f"감사 로그는 `.claude/debate/D-YYYY-MM-DD-*.jsonl` 에 보존.\n"
        )

    # 도메인 기본 가정 블록 (있으면)
    assumptions_section = ""
    if assumptions_md and side == "c":
        assumptions_section = (
            f"\n## 도메인 기본 가정 ({display})\n\n{assumptions_md}\n\n"
            f"> ⚠️ 이 가정들은 기본값이다. 프로젝트 맥락에서 틀릴 수 있으니 x-{kind} 가 도전한다.\n"
        )

    # critical checklist (x 측)
    checklist_section = ""
    if checklist_md and side == "x":
        checklist_section = (
            f"\n## {display} 도메인에서 항상 의심할 것\n\n{checklist_md}\n"
        )

    # 용어 블록
    terms_section = ""
    if terms_md:
        terms_section = (
            f"\n## 이 도메인의 핵심 용어 (다른 도메인과 혼동 주의)\n\n{terms_md}\n"
        )

    # 페어 연동
    if side == "c":
        peer_section = (
            f"## 페어 연동\n"
            f"- 페어 상대: **x-{kind}** (🟢 Codex, Critical)\n"
            f"- 호출 방식: codex exec 적대검토(CLI 직접) 또는 `debate_manager` (토론 시)\n"
            f"- x-{kind} 가 이 결과물의 **약점·반례·놓친 엣지 케이스** 반환\n"
        )
    else:
        peer_section = (
            f"## 페어 연동\n"
            f"- 페어 상대: **c-{kind}** (🔵 Claude, Constructive)\n"
            f"- 호출 방식: `codex exec --sandbox read-only`(적대검토 프롬프트, CLI 직접)\n"
            f"- **대안 설계를 내지 말 것** — c-{kind} 의 제안을 도전하는 것이 주 임무\n"
        )

    return f"""# {side}-{kind} ({header_icon} {llm_label}) — {display}

## 소속 패턴
- 패턴: **{pattern_emoji} {pattern_display}** ({pattern})
- 활성 STEP: {steps_str}
- 페어 ID: **{pair_id}**
- primary_mode: **{primary_mode}**

## 핵심 역할
{role_md}
{assumptions_section}{checklist_section}{terms_section}
{peer_section}
{debate_note}
## 프로젝트 맥락
프로젝트: **{project_name}**
"""


def list_patterns() -> list[dict[str, Any]]:
    """모든 패턴의 요약 정보 목록.

    Returns:
        [{name, display, emoji, active_steps, pair_count, debate_enabled}, ...]
    """
    result = []
    for name, spec in PATTERNS.items():
        result.append({
            "name": name,
            "display": spec["display"],
            "emoji": spec["emoji"],
            "active_steps": spec["active_steps"],
            "pair_count": len(spec["pairs"]),
            "debate_enabled": spec["debate_enabled"],
        })
    return result
