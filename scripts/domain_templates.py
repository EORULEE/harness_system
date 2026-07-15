#!/usr/bin/env python3
"""domain_templates.py — 프로젝트 부트스트랩용 도메인 템플릿 라이브러리.

목적: 프로젝트 시작 시 사용자가 매번 수동으로 만들던 것을 자동 생성.
  - 도메인별 기본 assumptions
  - 도메인 간 용어 충돌 매핑
  - 에이전트 .md 템플릿
  - 융합 연구 anti-patterns

사용: campaign_manager.py bootstrap 이 호출한다.
"""

from __future__ import annotations
from typing import Any

# ──────────────────────────────────────────────────────────────────
# 도메인 카탈로그 — 각 도메인의 assumption·용어·전형적 함정
# ──────────────────────────────────────────────────────────────────

DOMAIN_CATALOG: dict[str, dict[str, Any]] = {
    "sar": {
        "display": "SAR (Synthetic Aperture Radar)",
        "pair_id": "PAIR-SAR",
        "agent_kind": "sar",
        "assumptions": [
            "InSAR 위상 언래핑이 정확하다",
            "coherence > 0.3 구간만 신뢰 가능",
            "대기 효과는 PSInSAR 또는 이중차분으로 제거됨",
            "궤도 오차는 정밀궤도력(POD)으로 보정됨",
        ],
        "critical_review_checklist": [
            "저-coherence 지역 (식생·눈·급경사) 영향",
            "대기 효과 (특히 troposphere)",
            "궤도 오차·DEM 오차의 잔여 기여",
            "ascending/descending 조합으로 해소 가능한지",
        ],
        "key_terms": {
            "accuracy": "위상 언래핑 오차의 RMSE (radian 또는 mm)",
            "resolution": "공간 해상도 (m/pixel)",
            "coherence": "간섭 쌍의 위상 일관성 (0-1)",
            "coverage": "유효 픽셀 비율",
        },
    },
    "insar": {
        "display": "InSAR (Interferometric SAR)",
        "pair_id": "PAIR-INSAR",
        "agent_kind": "insar",
        "assumptions": [
            "시계열 InSAR 기법(PS/SBAS)이 안정점 기반 시계열을 제공",
            "변위 신호 > 대기·궤도 노이즈",
        ],
        "critical_review_checklist": [
            "reference point 선정의 임의성",
            "seasonal·tropospheric artifact",
            "non-linear 변위 가정 위반",
        ],
        "key_terms": {
            "deformation": "누적 지표 변위 (mm 또는 mm/year)",
            "velocity": "시간 평균 변위 속도 (mm/year)",
        },
    },
    "ai": {
        "display": "AI / Machine Learning",
        "pair_id": "PAIR-AI",
        "agent_kind": "ai",
        "assumptions": [
            "학습 데이터가 테스트 분포를 대표한다",
            "레이블이 일관되게 정의됨",
            "train/val/test 분할이 data leakage 없음",
            "모델이 표현 가능한 함수 공간에 목표가 존재",
        ],
        "critical_review_checklist": [
            "data leakage (시공간 의존성에서 특히)",
            "class imbalance + sampling 편향",
            "hyperparameter를 test set으로 튜닝",
            "random seed shopping / p-hacking",
            "OOD 일반화 가정",
        ],
        "key_terms": {
            "accuracy": "올바르게 분류된 샘플 비율 (0-1)",
            "resolution": "모델이 구분 가능한 최소 특징 크기",
            "precision": "양성 예측 중 실제 양성 비율",
            "recall": "실제 양성 중 탐지된 비율",
        },
    },
    "ml": {  # alias
        "display": "Machine Learning",
        "pair_id": "PAIR-AI",
        "agent_kind": "ai",
        "assumptions": [],
        "critical_review_checklist": [],
        "key_terms": {},
    },
    "volcanology": {
        "display": "Volcanology",
        "pair_id": "PAIR-VOLC",
        "agent_kind": "volc",
        "assumptions": [
            "분화 정의가 일관됨 (VEI 기준)",
            "분화 전 지표 변위 패턴이 보편적으로 존재",
            "분화 라벨의 source가 신뢰 가능 (Smithsonian GVP 등)",
            "precursor 시간 스케일이 관측 주기와 호환됨",
        ],
        "critical_review_checklist": [
            "survivor bias (기록된 분화만 분석)",
            "분화 없이도 변위가 발생하는 경우 (dike intrusion without eruption)",
            "VEI 경계값의 주관성",
            "precursor 기간의 화산별 편차",
        ],
        "key_terms": {
            "accuracy": "분화 감지 성공률 (실제 분화 구간)",
            "resolution": "시간 해상도 (탐지 지연)",
            "eruption": "VEI ≥ 1 또는 ≥ 2 (명시 필요)",
            "precursor": "분화 전 관측 가능한 신호 (초~수개월)",
        },
    },
    "volc": {  # alias
        "display": "Volcanology",
        "pair_id": "PAIR-VOLC",
        "agent_kind": "volc",
        "assumptions": [],
        "critical_review_checklist": [],
        "key_terms": {},
    },
    "geodesy": {
        "display": "Geodesy",
        "pair_id": "PAIR-GEO",
        "agent_kind": "geo",
        "assumptions": [
            "GNSS reference frame이 일관됨 (ITRF)",
            "tide·loading 효과 보정됨",
        ],
        "critical_review_checklist": [
            "reference frame 간 변환 오차",
            "monument instability",
        ],
        "key_terms": {
            "accuracy": "위치 측정 오차 (mm)",
            "baseline": "관측점 간 거리",
        },
    },
    "remote_sensing": {
        "display": "Remote Sensing (generic)",
        "pair_id": "PAIR-RS",
        "agent_kind": "rs",
        "assumptions": [
            "센서 보정이 유효 기간 내",
            "cloud mask·atmospheric correction 적용됨",
        ],
        "critical_review_checklist": [
            "센서 간 상호 보정",
            "시공간 해상도 mismatch",
        ],
        "key_terms": {
            "accuracy": "복원 오차 (센서별 단위)",
            "resolution": "공간/시간/스펙트럼 해상도",
        },
    },
}


# ──────────────────────────────────────────────────────────────────
# 도메인 별칭 정규화
# ──────────────────────────────────────────────────────────────────

def normalize_domain(name: str) -> str | None:
    """사용자 입력 'AI' / 'ai' / 'ML' / 'machine-learning' → 표준 키.

    우선순위:
    1. 정적 DOMAIN_CATALOG 키 직접 매칭
    2. 정적 alias 매핑
    3. 동적 등록 도메인 (domain_cache.json) 매칭
    4. 매칭 실패 시 None
    """
    k = name.lower().replace("-", "_").replace(" ", "_").strip()
    aliases = {
        # SAR / InSAR
        "sar": "sar", "insar": "insar",
        # AI / ML
        "ai": "ai", "ml": "ai", "machine_learning": "ai", "deep_learning": "ai",
        # 화산학
        "volcano": "volcanology", "volcanology": "volcanology", "volc": "volcanology",
        # 측지학
        "geodesy": "geodesy", "geo": "geodesy",
        # 원격탐사
        "remote_sensing": "remote_sensing", "rs": "remote_sensing",
    }
    # 정적 매칭
    if k in aliases:
        return aliases[k]
    if k in DOMAIN_CATALOG:
        return k
    # 동적 매칭 (캐시에서 로드된 키)
    if k in _DYNAMIC_DOMAINS:
        return k
    return None


# ──────────────────────────────────────────────────────────────────
# 동적 도메인 등록 시스템 (v2.4.7+)
# ──────────────────────────────────────────────────────────────────
#
# 목적: Claude 가 자동 도메인 판별 후 DOMAIN_CATALOG 에 새 도메인을
#       동적으로 등록할 수 있게 한다. 등록된 도메인은 domain_cache.json
#       에 영속되어 다음 세션에서 자동 복원.
#
# 주의: 런타임에 DOMAIN_CATALOG 를 수정하는 것이 아니라, 별도의
#       _DYNAMIC_DOMAINS dict 에 저장하고 lookup 시 병합한다.
#       이렇게 하면 정적 카탈로그(하드코딩) 와 동적 카탈로그(학습)
#       가 분리되어 디버깅·감사가 용이.

import json as _json
from pathlib import Path as _Path

# 동적 도메인 저장소 (모듈 로드 시 캐시에서 복원됨)
_DYNAMIC_DOMAINS: dict[str, dict[str, Any]] = {}

# 캐시 파일 경로 (프로젝트 루트 .claude/ 아래)
_DOMAIN_CACHE_PATH = _Path(".claude") / "domain_cache.json"


def get_domain(key: str) -> dict[str, Any] | None:
    """도메인 엔트리 조회 (정적 + 동적 통합).

    정적 DOMAIN_CATALOG 우선, 없으면 _DYNAMIC_DOMAINS 에서 조회.
    """
    if key in DOMAIN_CATALOG:
        return DOMAIN_CATALOG[key]
    if key in _DYNAMIC_DOMAINS:
        return _DYNAMIC_DOMAINS[key]
    return None


def list_all_domains() -> list[str]:
    """등록된 모든 도메인 키 반환 (정적 + 동적)."""
    return sorted(set(DOMAIN_CATALOG.keys()) | set(_DYNAMIC_DOMAINS.keys()))


def register_dynamic_domain(
    key: str,
    display: str,
    pair_id: str,
    agent_kind: str,
    assumptions: list[str],
    critical_review_checklist: list[str],
    key_terms: dict[str, str],
    *,
    source: str = "auto_detect",
    skills: list[dict[str, str]] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """동적 도메인 엔트리를 등록.

    Args:
        key: 도메인 키 (snake_case, 예: "crypto_trading")
        display: 사람이 읽기 쉬운 이름
        pair_id: PAIR 식별자 (예: "PAIR-MARKET")
        agent_kind: 에이전트 kind (예: "market")
        assumptions: 이 도메인의 기본 가정 목록
        critical_review_checklist: 전형적 함정 체크리스트
        key_terms: 용어 정의 dict
        source: 등록 출처 ("auto_detect", "manual", "migration" 등)
        skills: 도메인별 skill 목록 (Phase 7 에서 사용)
        persist: True 면 domain_cache.json 에 저장

    Returns:
        등록된 엔트리 dict

    Raises:
        ValueError: key 가 이미 정적 DOMAIN_CATALOG 에 존재하는 경우
    """
    # 정적 카탈로그 충돌 방지
    if key in DOMAIN_CATALOG:
        raise ValueError(
            f"'{key}' 는 정적 DOMAIN_CATALOG 에 이미 존재합니다. "
            f"동적 등록 불가. 정적 카탈로그를 직접 수정하거나 다른 키를 사용하세요."
        )

    # 키 정규화 검증
    if not key or not key.replace("_", "").isalnum():
        raise ValueError(
            f"도메인 키는 snake_case 영숫자여야 합니다: {key!r}"
        )

    entry = {
        "display": display,
        "pair_id": pair_id,
        "agent_kind": agent_kind,
        "assumptions": list(assumptions),
        "critical_review_checklist": list(critical_review_checklist),
        "key_terms": dict(key_terms),
        "_dynamic": True,
        "_source": source,
    }
    if skills is not None:
        entry["skills"] = list(skills)

    _DYNAMIC_DOMAINS[key] = entry

    if persist:
        save_domain_cache()

    return entry


def load_domain_cache(path: _Path | str | None = None) -> int:
    """세션 시작 시 domain_cache.json 로드.

    Returns:
        로드된 동적 도메인 개수
    """
    cache_path = _Path(path) if path else _DOMAIN_CACHE_PATH
    if not cache_path.exists():
        return 0

    try:
        data = _json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as e:
        # 캐시 파일 깨져도 무시 (세션은 계속 진행)
        import sys
        print(f"⚠️  domain_cache.json 로드 실패: {e}", file=sys.stderr)
        return 0

    count = 0
    for key, entry in data.get("domains", {}).items():
        if key in DOMAIN_CATALOG:
            # 정적 카탈로그와 충돌하면 캐시 항목 무시
            continue
        _DYNAMIC_DOMAINS[key] = entry
        count += 1

    return count


def save_domain_cache(path: _Path | str | None = None) -> None:
    """현재 _DYNAMIC_DOMAINS 를 domain_cache.json 에 저장."""
    cache_path = _Path(path) if path else _DOMAIN_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "_version": "v2.4.7",
        "_schema": "domain_cache/1.0",
        "domains": _DYNAMIC_DOMAINS,
    }
    cache_path.write_text(
        _json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def clear_dynamic_domains() -> int:
    """모든 동적 도메인 제거 (메모리 + 캐시 파일).

    Returns:
        제거된 도메인 개수
    """
    count = len(_DYNAMIC_DOMAINS)
    _DYNAMIC_DOMAINS.clear()
    if _DOMAIN_CACHE_PATH.exists():
        _DOMAIN_CACHE_PATH.unlink()
    return count


def build_domain_entry_from_scan(
    key: str,
    scan_result: dict[str, Any],
    *,
    display: str | None = None,
    pair_id: str | None = None,
) -> dict[str, Any]:
    """domain_detector.py 스캔 결과 + Claude 추론을 기반으로 도메인 엔트리 초안 생성.

    Claude 가 이 함수를 직접 호출하지는 않는다. 대신 Claude 가
    scan_result 를 해석해서 assumptions/checklist/key_terms 를 직접 생성하고
    register_dynamic_domain() 를 호출한다. 이 함수는 **구조 검증용 헬퍼**.

    Args:
        key: 도메인 키 (snake_case)
        scan_result: domain_detector.py 의 출력
        display: 명시적 표시 이름 (없으면 key 에서 생성)
        pair_id: 명시적 pair_id (없으면 key 에서 생성)

    Returns:
        구조가 검증된 초안 dict (실제 내용은 Claude 가 채워야 함)
    """
    display = display or key.replace("_", " ").title()
    pair_id = pair_id or f"PAIR-{key.upper().split('_')[0][:8]}"

    return {
        "key": key,
        "display": display,
        "pair_id": pair_id,
        "agent_kind": key.split("_")[0],
        "assumptions": [],  # Claude 가 채워야 함
        "critical_review_checklist": [],  # Claude 가 채워야 함
        "key_terms": {},  # Claude 가 채워야 함
        "_source": "auto_detect",
        "_scan_summary": {
            "total_files": scan_result.get("file_structure", {}).get("total_files", 0),
            "top_extensions": list(scan_result.get("file_structure", {})
                                   .get("extension_counts", {}).keys())[:5],
            "primary_imports": (
                (scan_result.get("imports", {}).get("python", []) or [])[:5]
                + (scan_result.get("imports", {}).get("javascript", []) or [])[:5]
            ),
        },
    }


# 모듈 로드 시 자동으로 캐시 복원 시도
# (테스트 환경 등에서는 .claude/domain_cache.json 이 없을 수 있음 → 조용히 무시)
try:
    load_domain_cache()
except Exception:
    pass


# ──────────────────────────────────────────────────────────────────
# 용어 충돌 자동 감지
# ──────────────────────────────────────────────────────────────────

def detect_term_conflicts(domain_keys: list[str]) -> dict[str, dict[str, str]]:
    """여러 도메인에서 같은 용어가 다른 의미를 가지면 충돌로 기록."""
    term_map: dict[str, dict[str, str]] = {}
    for dk in domain_keys:
        dd = DOMAIN_CATALOG.get(dk, {})
        for term, meaning in dd.get("key_terms", {}).items():
            term_map.setdefault(term, {})
            term_map[term][dk] = meaning
    return {t: defs for t, defs in term_map.items() if len(defs) >= 2}


# ──────────────────────────────────────────────────────────────────
# 융합 연구 공통 anti-patterns
# ──────────────────────────────────────────────────────────────────

CROSS_DOMAIN_ANTI_PATTERNS = [
    {
        "id": "cross-domain-metric-mismatch",
        "category": "anti_patterns",
        "trigger": {
            "natural": "여러 도메인이 같은 단어(accuracy, resolution 등)를 다른 의미로 쓸 때",
            "keywords": ["accuracy", "resolution", "metric", "performance"],
        },
        "action": (
            "수치를 쓸 때 반드시 도메인 맥락을 명시한다.\n"
            "예: 'AI classification accuracy: 92%' (X: 'accuracy: 92%')\n"
            "domain-terminology-map.yaml 참조하여 해당 용어의 맥락별 정의 확인."
        ),
        "tags": ["cross-domain", "terminology"],
    },
    {
        "id": "cross-domain-boundary-skip",
        "category": "anti_patterns",
        "trigger": {
            "natural": "여러 도메인 결과를 이어붙이기 직전",
            "keywords": ["integrate", "combine", "pipeline", "통합", "결합"],
        },
        "action": (
            "각 도메인 결과를 합치기 전 PAIR-QA가 경계면 검증을 먼저 실행한다.\n"
            "확인할 것:\n"
            "  - 시공간 해상도 mismatch\n"
            "  - 단위/스케일 변환 (특히 log, dB, radian)\n"
            "  - 한 도메인의 가정이 다른 도메인 입력을 오염시키는지\n"
            "  - 경계에서 정보 손실 또는 과잉 smoothing"
        ),
        "tags": ["cross-domain", "qa", "boundary"],
    },
    {
        "id": "cross-domain-single-pair-decision",
        "category": "anti_patterns",
        "trigger": {
            "natural": "융합 프로젝트에서 한 도메인 페어만 호출하고 결정할 때",
            "keywords": ["decide", "결정", "선택", "채택"],
        },
        "action": (
            "B 모드 중요 결정은 관련된 모든 도메인 페어 호출 필수.\n"
            "예: 'loss function 선택'은 PAIR-AI 단독이 아니라 PAIR-AI + PAIR-<도메인> 동시.\n"
            "한 페어 결정은 상관 오류를 낳기 쉽다."
        ),
        "tags": ["cross-domain", "decision", "orchestration"],
    },
]


# ──────────────────────────────────────────────────────────────────
# 에이전트 .md 템플릿
# ──────────────────────────────────────────────────────────────────

def render_constructive_agent(kind: str, pair_id: str, display: str,
                              project_name: str,
                              assumptions: list[str],
                              key_terms: dict[str, str]) -> str:
    """c-*.md (Constructive Claude) 템플릿 렌더링.

    v2.7.1+: Claude Code 공식 frontmatter (name + description) 추가.
    """
    assumptions_md = "\n".join(f"- {a}" for a in assumptions) or "- (도메인 기본 가정 없음)"
    terms_md = "\n".join(f"- **{t}**: {m}" for t, m in key_terms.items()) or "- (특기 용어 없음)"
    # 도메인 페어 트리거: 도메인 키워드 + 핵심 가정 첫 항목
    kw_hint = ", ".join(list(key_terms.keys())[:3]) if key_terms else display
    desc = (f"{display} 도메인의 1차 분석·구현·답변. "
            f"{kw_hint} 작업 시 호출. 표준 가정 적용 후 x-{kind} 가 도전")
    return f"""---
name: c-{kind}
description: {desc}
model: inherit
---

# c-{kind} (🔵 Claude) — {display}

## 핵심 역할
- 페어: **{pair_id}**
- primary_mode: **constructive**
- 역할: {display} 도메인의 1차 설계·분석·구현 결과물 생성

## 작업 원칙
- 본 도메인의 표준 방법론·관례·최신 동향에 기반해 **건설적 제안** 생성
- 다른 도메인 페어와 경계에서는 명시적 입출력 정의
- 수치·지표 사용 시 아래 용어 정의 따름

## 도메인 기본 가정 ({display})
{assumptions_md}

> ⚠️ 이 가정들은 기본값이다. 프로젝트 맥락에서 **틀릴 수 있으니** x-{kind}가 도전한다.

## 이 도메인의 핵심 용어 (다른 도메인과 혼동 주의)
{terms_md}

## 페어 연동
- 페어 상대: **x-{kind}** (🟢 Codex, Critical)
- 호출 방식: `codex exec` 적대검토(CLI 직접 — 플러그인 제거 2026-07-13)
- x-{kind}가 이 결과물의 **약점·반례·놓친 엣지 케이스**를 반환

## 프로젝트 맥락
프로젝트: **{project_name}**
"""


def render_critical_agent(kind: str, pair_id: str, display: str,
                          project_name: str,
                          critical_checklist: list[str],
                          key_terms: dict[str, str]) -> str:
    """x-*.md (Critical Codex) 템플릿 렌더링.

    v2.7.1+: Claude Code 공식 frontmatter 추가.
    """
    checklist_md = "\n".join(f"- {c}" for c in critical_checklist) or "- (도메인 공통 체크 없음)"
    terms_md = "\n".join(f"- **{t}**: {m}" for t, m in key_terms.items()) or "- (특기 용어 없음)"
    first_check = critical_checklist[0] if critical_checklist else "암묵 가정·엣지 케이스"
    desc = (f"{display} 도메인의 c-{kind} 결과 도전. "
            f"{first_check[:80]} 등 깨지는 조건·반례 탐색. c-{kind} 직후 호출")
    return f"""---
name: x-{kind}
description: {desc}
model: inherit
---

# x-{kind} (🟢 Codex) — {display} Critical Reviewer

## 핵심 역할
- 페어: **{pair_id}**
- primary_mode: **critical**
- 역할: c-{kind}의 결과물이 **깨지는 조건**과 **숨은 가정**을 찾는다.

## 작업 원칙
- **대안 설계를 내지 말 것**. c-{kind}의 제안을 도전하는 것이 주 임무.
- 다음 질문에 답:
  1. 이 접근이 **깨지는 조건**은?
  2. 어떤 **암묵적 가정**이 있고 언제 위반되는가?
  3. 어떤 **엣지 케이스·예외**가 놓였는가?
  4. 반례를 만들 수 있는가?
- 발견이 없으면 "no finding"으로 답. 억지로 찾지 말 것.

## {display} 도메인에서 항상 의심할 것
{checklist_md}

## 용어 검증 (다른 도메인과 혼동)
c-{kind}가 쓴 수치가 다음 용어와 맥락이 일치하는지 확인:
{terms_md}

## 실행 방법 (CLI 직접 — 플러그인 제거 2026-07-13)

이 에이전트는 **codex CLI 직접 호출**을 사용한다 (openai-codex 플러그인 제거됨).
기본 모델 = `~/.codex/config.toml` pin (gpt-5.6-sol).

### 기본: codex exec 적대검토

```
codex exec --sandbox read-only --skip-git-repo-check "challenge the assumptions and failure modes of [c-{kind} 결과]"
```

- 반드시 timeout 동반 (cold-start hang 리스크) · read-only sandbox 고정.
- 파일 allowlist·secret 마스킹·재시도 캡이 필요한 게이트 검토는 `scripts/gate_codex_review.py` 사용.
- 장시간 리뷰는 Bash run_in_background 로 실행.

### 완전 독립 분석 (드문 경우)

```
codex exec --skip-git-repo-check "investigate why the integration test is flaky"
```

> ⚠️ 세션당 **3회 제한** 권고 (circuit_breaker). 남용 시 상관 오류 위험.

### Codex CLI 미설치·미인증 시

`codex --version`/`codex login status` 실패 시 x-{kind}는 **Claude 기반 self-review**로 fallback한다
(같은 모델이 양쪽을 담당 → 상관 오류 증가 주의).

## 페어 연동
- 페어 상대: **c-{kind}** (🔵 Claude, Constructive)
- 호출 순서: c-{kind} 1차 결과 → codex exec 적대검토(CLI) → Codex findings → 메인 Claude가 통합

## 프로젝트 맥락
프로젝트: **{project_name}**
"""


# 공통 페어 (도메인 무관)
# v2.7+: writer + references 추가 (논문·제안서·보고서 작성 + 학술 출처 검증)
STANDARD_PAIRS = [
    ("lead", "PAIR-LEAD", "Lead & Orchestrator",
     ["전체 조율·플래닝·통합 답변", "STEP 간 의존성 관리"],
     ["전체 설계의 근본 가정", "도메인 간 우선순위 편향"]),
    ("dev", "PAIR-DEV", "Implementation",
     ["코드 구현·테스트·리팩터링"],
     ["구현 에지 케이스·성능·보안·재현성"]),
    ("qa", "PAIR-QA", "Boundary QA",
     ["도메인 간 경계면 정합성 검증 (incremental)",
      "단위·스케일·시공간 해상도 일치 확인",
      "한 도메인 출력 ↔ 다른 도메인 입력 shape 검증"],
     ["경계에서의 정보 손실", "회귀·음성 경로", "silent failure mode"]),
    ("methods", "PAIR-METHODS", "Methodology & Statistics",
     ["평가 프로토콜·통계 검정·ground truth 정의"],
     ["다중 비교·p-hacking·ground truth 주관성"]),
    # v2.7+ 신규
    ("writer", "PAIR-WRITER", "Logical Writing — 논문·제안서·보고서",
     ["논문 abstract/intro/methods/results/discussion 초안",
      "연구개발계획서·제안서 배경·목표·방법·예상 성과",
      "보고서 executive summary·findings·recommendations",
      "한국어/영어 학술 톤 (정중·명확·hedging)",
      "ATBD·기술 명세서 구조화"],
     ["주장의 논리 비약·증거 부족 단정",
      "출처 불명 인용·numerical claim",
      "영어 번역의 어색함·학술 컨벤션 위반",
      "모호한 표현 ('적절한', '필요시')·hedging 부족",
      "논리 구조 (가설 → 증거 → 결론) 단절"]),
    ("references", "PAIR-REFERENCES", "References Research & Validation",
     ["WebSearch/WebFetch 로 학술 논문·보고서·표준 조사",
      "4 카테고리 분류 (peer-reviewed / 기관보고서 / 표준 / 공식docs)",
      "<project>/.claude/references/<topic-slug>.md 영구 저장",
      "INDEX.md 토픽 인덱스 갱신",
      "본문 인용과 출처 매칭 검증"],
     ["가짜 출처·존재하지 않는 URL·논문 제목 환각 검출",
      "잘못된 인용 (페이지·연도·저자 불일치)",
      "카테고리 분류 오류 (블로그·포럼이 메인으로 들어간 것)",
      "단정에 카테고리 1 출처 부재 ('논문 미확인' 표시 강제)",
      "1차/2차 출처 혼동·복제 인용"]),
]


def render_standard_agent_pair(kind: str, pair_id: str, role: str,
                               project_name: str,
                               c_duties: list[str], x_duties: list[str]) -> tuple[str, str]:
    """표준 페어(lead/dev/qa/methods/writer/references) c-·x- 양쪽 md 생성.

    v2.7.1+: Claude Code 공식 frontmatter 추가 (name + description 필수).
    출처: https://code.claude.com/docs/en/sub-agents
    """
    c_duties_md = "\n".join(f"- {d}" for d in c_duties)
    x_duties_md = "\n".join(f"- {d}" for d in x_duties)

    # Claude Code subagent 자동 트리거용 description (한 문장, 명확)
    c_desc = _standard_c_description(kind, role, c_duties)
    x_desc = _standard_x_description(kind, role, x_duties)

    c = f"""---
name: c-{kind}
description: {c_desc}
model: inherit
---

# c-{kind} (🔵 Claude) — {role}

## 핵심 역할
- 페어: **{pair_id}**
- primary_mode: **constructive**

## 책임
{c_duties_md}

## 페어 연동
- 페어 상대: **x-{kind}** (🟢 Codex)
- 기본 커맨드: `codex exec --sandbox read-only`(적대검토 프롬프트)

## 프로젝트 맥락
프로젝트: **{project_name}**
"""
    x = f"""---
name: x-{kind}
description: {x_desc}
model: inherit
---

# x-{kind} (🟢 Codex) — {role} Critical

## 핵심 역할
- 페어: **{pair_id}**
- primary_mode: **critical**
- 대안 설계가 아니라 **c-{kind} 결과물의 약점 탐지**가 주 임무.

## 체크리스트
{x_duties_md}

## 발견이 없으면 "no finding"
억지 지적 금지. 검증했으나 문제 없으면 그렇게 답할 것.

## 페어 연동
- 페어 상대: **c-{kind}** (🔵 Claude)

## 프로젝트 맥락
프로젝트: **{project_name}**
"""
    return c, x


# v2.7.1+: 표준 페어별 자동 트리거 description
_C_DESCRIPTIONS = {
    "lead":       "Constructive 1차 답변·플래닝·통합. 모드 A1/B 의 핵심 결정·다도메인 통합 시점에 호출",
    "dev":        "코드 구현·테스트·리팩터링. 'Implement X' 또는 코드 작업 요청 시 호출",
    "qa":         "도메인 간 경계면 정합성·해상도·단위 일치 검증. STEP 1.5/2.5 cross-pair 게이트에서 호출",
    "methods":    "평가 프로토콜·통계 검정·ground truth 정의. 모델 검증·통계 분석 시점에 호출",
    "writer":     "논문·제안서·보고서·ATBD 논리적 작성. 한국어/영어 학술 톤·hedging. 문서 작성 요청 시 호출",
    "references": "학술 출처 조사·WebSearch 4 카테고리 분류·references/<topic>.md 영구 저장. 외부 사실 인용 시 호출",
}
_X_DESCRIPTIONS = {
    "lead":       "c-lead 결과의 근본 가정·도메인 간 우선순위 편향 도전. c-lead 직후 호출",
    "dev":        "c-dev 결과의 엣지 케이스·성능·보안·재현성 도전. 코드 작성 직후 호출",
    "qa":         "QA 검증의 silent failure·회귀·정보 손실·음성 경로 도전. c-qa 직후 호출",
    "methods":    "c-methods 의 다중 비교·p-hacking·ground truth 주관성 도전. 통계 결과 직후 호출",
    "writer":     "c-writer 결과의 논리 비약·증거 부족·hedging 부족·번역 어색·인용 형식 위반 도전. 작성 직후 호출",
    "references": "가짜 출처·존재하지 않는 URL·잘못된 인용·카테고리 분류 오류 검출. 학술 인용 직후 호출",
}


def _standard_c_description(kind: str, role: str, c_duties: list[str]) -> str:
    """표준 c-* 페어의 description 생성 (정의 dict + 폴백)."""
    if kind in _C_DESCRIPTIONS:
        return _C_DESCRIPTIONS[kind]
    # 폴백: role + 첫 책임
    first = c_duties[0] if c_duties else "constructive 1차 답변"
    return f"{role} — Constructive. {first[:100]}"


def _standard_x_description(kind: str, role: str, x_duties: list[str]) -> str:
    """표준 x-* 페어의 description 생성."""
    if kind in _X_DESCRIPTIONS:
        return _X_DESCRIPTIONS[kind]
    first = x_duties[0] if x_duties else "약점·반례 탐색"
    return f"{role} — Critical. c-{kind} 결과의 {first[:80]} 도전"


# ──────────────────────────────────────────────────────────────────
# v2.4.7+: 공용 skills 도메인 특화 섹션 주입
# ──────────────────────────────────────────────────────────────────
#
# 5개 공용 skill (debugging, qa-integration, hierarchical-delegation,
# research, visualization) 에는 {{DOMAIN_PITFALLS}}, {{DOMAIN_TOOLS}}
# 플레이스홀더가 있다. bootstrap 시 이 함수로 치환.

COMMON_SKILLS = [
    "debugging",
    "qa-integration",
    "hierarchical-delegation",
    "research",
    "visualization",
    "html-infographic",  # v2.4.7+: HTML/CSS 기반 설명 그림
    "debate",            # v2.5.0+: Claude↔Codex 다턴 토론 엔진 연동
]


def render_domain_pitfalls(
    skill_name: str,
    domain_keys: list[str],
) -> str:
    """공용 skill 의 DOMAIN_PITFALLS 섹션 내용 생성.

    각 도메인의 critical_review_checklist 에서 skill 과 연관된 항목을
    뽑아 markdown bullet 목록 생성.

    Args:
        skill_name: 공용 skill 이름
        domain_keys: 활성 도메인 키 목록

    Returns:
        markdown 형식 문자열
    """
    lines: list[str] = []
    for dkey in domain_keys:
        entry = get_domain(dkey)
        if not entry:
            continue
        checklist = entry.get("critical_review_checklist", [])
        if not checklist:
            continue
        display = entry.get("display", dkey)
        lines.append(f"\n**{display} 특화 함정**:")
        for item in checklist:
            lines.append(f"- {item}")

    if not lines:
        return "_(활성 도메인 없음 — 기본 공용 함정만 적용)_"
    return "\n".join(lines).strip()


def render_domain_tools(
    skill_name: str,
    domain_keys: list[str],
    tech_stack: list[str] | None = None,
) -> str:
    """공용 skill 의 DOMAIN_TOOLS 섹션 내용 생성.

    도메인별 권장 도구를 tech_stack 과 결합해 제시.

    Args:
        skill_name: 공용 skill 이름
        domain_keys: 활성 도메인 키 목록
        tech_stack: 전역 변수 TECH_STACK (실제 사용 중 도구)

    Returns:
        markdown 형식 문자열
    """
    lines: list[str] = []

    if tech_stack:
        lines.append("**이 프로젝트에서 실제 사용 중**:")
        for tool in tech_stack:
            lines.append(f"- `{tool}`")
        lines.append("")

    # 도메인별 관련 도구 힌트 (간단 매핑)
    # 자세한 도구는 Claude 가 bootstrap 시 생성하여 domain entry 에 추가
    for dkey in domain_keys:
        entry = get_domain(dkey)
        if not entry:
            continue
        # 동적 도메인이 skills 필드에 도구 목록을 포함할 수 있음
        skill_tools = entry.get("skill_tools", {}).get(skill_name, [])
        if skill_tools:
            display = entry.get("display", dkey)
            lines.append(f"**{display} 권장 도구**:")
            for tool in skill_tools:
                lines.append(f"- {tool}")
            lines.append("")

    if not lines:
        return "_(사용자 tech_stack 또는 도메인별 도구 목록 없음)_"
    return "\n".join(lines).strip()


def inject_skill_placeholders(
    skill_md_path: _Path | str,
    domain_keys: list[str],
    *,
    tech_stack: list[str] | None = None,
) -> str:
    """SKILL.md 파일의 {{DOMAIN_PITFALLS}}, {{DOMAIN_TOOLS}} 플레이스홀더 치환.

    Args:
        skill_md_path: SKILL.md 파일 경로
        domain_keys: 활성 도메인 키 목록
        tech_stack: 프로젝트 tech_stack

    Returns:
        치환된 markdown 문자열 (파일에 쓰지는 않음 — 호출자가 결정)
    """
    path = _Path(skill_md_path)
    content = path.read_text(encoding="utf-8")

    # skill 이름 추출 (frontmatter 의 name: 또는 폴더명)
    skill_name = path.parent.name

    pitfalls = render_domain_pitfalls(skill_name, domain_keys)
    tools = render_domain_tools(skill_name, domain_keys, tech_stack)

    content = content.replace("{{DOMAIN_PITFALLS}}", pitfalls)
    content = content.replace("{{DOMAIN_TOOLS}}", tools)
    return content


def install_common_skills(
    target_dir: _Path | str,
    domain_keys: list[str],
    *,
    source_dir: _Path | str | None = None,
    tech_stack: list[str] | None = None,
) -> dict[str, str]:
    """공용 skills 5개를 target_dir 에 복사 + 플레이스홀더 치환.

    Args:
        target_dir: `.claude/skills/` 같은 대상 디렉토리
        domain_keys: 활성 도메인 키 목록
        source_dir: 템플릿 skills/ 경로 (기본: 현재 패키지의 skills/)
        tech_stack: 프로젝트 tech_stack

    Returns:
        skill_name → 설치 경로 dict
    """
    import shutil
    target = _Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if source_dir is None:
        # 현재 패키지 기준 skills/ 찾기
        source = _Path(__file__).parent.parent / "skills"
    else:
        source = _Path(source_dir)

    if not source.exists():
        raise FileNotFoundError(f"공용 skills 소스 없음: {source}")

    installed: dict[str, str] = {}
    for name in COMMON_SKILLS:
        src_dir = source / name
        dst_dir = target / name
        if not src_dir.exists():
            continue
        # 전체 폴더 복사 (references/ 포함)
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
        # SKILL.md 플레이스홀더 치환
        skill_md = dst_dir / "SKILL.md"
        if skill_md.exists():
            rendered = inject_skill_placeholders(
                skill_md, domain_keys, tech_stack=tech_stack
            )
            skill_md.write_text(rendered, encoding="utf-8")
        installed[name] = str(dst_dir)

    return installed


# ──────────────────────────────────────────────────────────────────
# v2.4.7+: skill 자가 검증 프로토콜
# ──────────────────────────────────────────────────────────────────

import re as _re

SKILL_REQUIRED_FRONTMATTER = {"name", "description", "version", "auto_trigger"}
SKILL_REQUIRED_SECTIONS = {
    "Trigger", "Procedure", "Domain Pitfalls",
    "Tools & References", "호출 규약", "실패 모드",
}

# 금지 표현 (모호성)
SKILL_FORBIDDEN_PHRASES = [
    "필요 시", "필요시", "적절한 경우", "상황에 따라",
    "잘 모르겠지만", "아마도", "대략",
]


def validate_skill_md(content: str) -> dict[str, Any]:
    """SKILL.md 내용을 skill_generation_guide.md 기준으로 검증.

    Args:
        content: SKILL.md 전체 텍스트

    Returns:
        {
            "passed": bool,
            "errors": [...],
            "warnings": [...],
            "line_count": int,
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. frontmatter 검증
    fm_match = _re.match(r"^---\n(.*?)\n---", content, _re.DOTALL)
    if not fm_match:
        errors.append("frontmatter(---) 누락")
    else:
        fm_text = fm_match.group(1)
        for field in SKILL_REQUIRED_FRONTMATTER:
            if not _re.search(rf"^{field}:", fm_text, _re.MULTILINE):
                errors.append(f"frontmatter 필수 필드 누락: {field}")

    # 2. 필수 섹션 검증
    for section in SKILL_REQUIRED_SECTIONS:
        # "## Section" 형식 (정확히) 또는 "## Section Name" 형식
        pattern = rf"^## {_re.escape(section)}\b"
        if not _re.search(pattern, content, _re.MULTILINE):
            errors.append(f"필수 섹션 누락: ## {section}")

    # 3. 본문 길이 (200 줄 권장)
    line_count = content.count("\n") + 1
    if line_count > 250:
        warnings.append(
            f"본문 {line_count} 줄 — 200 줄 초과, "
            f"상세 내용을 references/ 로 분리 권장"
        )

    # 4. 금지 표현
    for phrase in SKILL_FORBIDDEN_PHRASES:
        if phrase in content:
            warnings.append(f"모호 표현 감지: '{phrase}' (구체화 권장)")

    # 5. Trigger 섹션 실제 내용 검증 (3개 이상 bullet)
    trigger_match = _re.search(
        r"^## Trigger\n(.*?)(?=^## |\Z)", content, _re.MULTILINE | _re.DOTALL
    )
    if trigger_match:
        trigger_body = trigger_match.group(1)
        bullet_count = len(_re.findall(r"^[\-\*] ", trigger_body, _re.MULTILINE))
        if bullet_count < 3:
            warnings.append(
                f"Trigger bullet 수 {bullet_count}개 — "
                f"최소 3~4개 권장"
            )

    # 6. Procedure 섹션 실제 단계 검증
    proc_match = _re.search(
        r"^## Procedure.*?\n(.*?)(?=^## |\Z)",
        content, _re.MULTILINE | _re.DOTALL
    )
    if proc_match:
        proc_body = proc_match.group(1)
        step_count = len(_re.findall(r"^### \d+\.", proc_body, _re.MULTILINE))
        if step_count < 3:
            warnings.append(
                f"Procedure 단계 수 {step_count}개 — "
                f"5~8 단계 권장"
            )
        elif step_count > 10:
            warnings.append(
                f"Procedure 단계 수 {step_count}개 — "
                f"너무 세분화됨, 통합 고려"
            )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "line_count": line_count,
    }


def validate_skill_file(skill_md_path: _Path | str) -> dict[str, Any]:
    """파일에서 SKILL.md 를 읽어 검증."""
    path = _Path(skill_md_path)
    if not path.exists():
        return {
            "passed": False,
            "errors": [f"파일 없음: {path}"],
            "warnings": [],
            "line_count": 0,
        }
    return validate_skill_md(path.read_text(encoding="utf-8"))


def validate_all_skills(skills_dir: _Path | str) -> dict[str, dict[str, Any]]:
    """skills/ 디렉토리 내 모든 SKILL.md 검증.

    Returns:
        {skill_name: validation_result}
    """
    skills_dir = _Path(skills_dir)
    results: dict[str, dict[str, Any]] = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        results[skill_dir.name] = validate_skill_file(skill_md)
    return results


# ──────────────────────────────────────────────────────────────────
# v2.4.7+: 도메인 skill 생성 프로토콜
# ──────────────────────────────────────────────────────────────────
#
# Claude 가 bootstrap 시 도메인 맞춤 skill 을 생성한다. 이 모듈은
# 생성 프로토콜의 Python 측 지원:
#   - Claude 에게 보낼 프롬프트 템플릿 생성
#   - 생성된 JSON 결과를 SKILL.md 파일로 변환
#   - 검증 실패 시 재생성 루프 관리

# Claude 에게 보내는 프롬프트 템플릿
_DOMAIN_SKILL_PROMPT_TEMPLATE = """당신은 하네스 v2.4.7 의 도메인 skill 생성자입니다.

반드시 `scripts/skill_generation_guide.md` 의 규약을 따르세요.

## 작업 맥락

- **도메인 키**: `{domain_key}`
- **도메인 표시명**: {display}
- **핵심 가정**: {assumptions}
- **전형적 함정**: {pitfalls}
- **프로젝트 tech_stack**: {tech_stack}
- **프로젝트 설명**: {project_description}

## 스캔 요약 (domain_detector.py 결과)

- 주요 import: {top_imports}
- 주요 키워드: {top_keywords}
- README 발췌: {readme_snippet}

## 생성 지시

이 도메인·이 프로젝트에서 **실제로 유용할 skill 3~5 개**를 제안하세요.
각 skill 에 대해 아래 JSON 형식으로:

```json
{{
  "skills": [
    {{
      "name": "kebab-case-name",
      "description": "자동 트리거 조건 한 문장",
      "auto_trigger": true,
      "trigger_bullets": [
        "구체 조건 1",
        "구체 조건 2",
        "구체 조건 3"
      ],
      "procedure_steps": [
        {{"title": "단계 1", "body": "내용"}},
        {{"title": "단계 2", "body": "내용"}}
      ],
      "domain_pitfalls": [
        {{"pitfall": "함정1", "avoidance": "회피법1"}},
        {{"pitfall": "함정2", "avoidance": "회피법2"}}
      ],
      "tools": ["도구 1", "도구 2"],
      "call_context_required": ["필수 필드명"],
      "call_context_optional": ["선택 필드명"],
      "result_keys": ["반환 키"],
      "failure_modes": ["언제 에스컬레이션"]
    }}
  ]
}}
```

## 금지 사항

- Trigger 에 모호 표현 ("필요 시", "적절한 경우") 사용
- Procedure 에 실행 불가능한 추상 단계
- 다른 도메인의 예시 복붙
- 출처 없는 수치·통계

## 품질 체크

생성 후 스스로 아래를 확인하세요:

- [ ] 각 skill 은 이 도메인에서 **반복 사용** 가치가 있는가?
- [ ] 3~5 개 숫자 준수 (너무 많으면 의미 희석)
- [ ] Procedure 단계는 실행 가능한가?
- [ ] Domain Pitfalls 는 일반 프로그래밍이 아닌 **이 도메인 고유**인가?
"""


def build_skill_generation_prompt(
    domain_key: str,
    *,
    project_description: str = "",
    tech_stack: list[str] | None = None,
    scan_result: dict[str, Any] | None = None,
) -> str:
    """Claude 에게 보낼 도메인 skill 생성 프롬프트 작성.

    Args:
        domain_key: 도메인 키 (DOMAIN_CATALOG 또는 _DYNAMIC_DOMAINS 에 등록되어야 함)
        project_description: 프로젝트 설명
        tech_stack: 사용 중인 기술 스택
        scan_result: domain_detector.py 의 출력

    Returns:
        프롬프트 문자열

    Raises:
        KeyError: domain_key 가 등록되지 않은 경우
    """
    entry = get_domain(domain_key)
    if entry is None:
        raise KeyError(
            f"도메인 '{domain_key}' 가 등록되지 않았습니다. "
            f"먼저 register_dynamic_domain() 으로 등록하세요."
        )

    # 스캔 결과 요약
    top_imports = ""
    top_keywords = ""
    readme_snippet = ""
    if scan_result:
        imports = scan_result.get("imports", {})
        py_imports = imports.get("python", []) or []
        js_imports = imports.get("javascript", []) or []
        top_imports = ", ".join(
            f"{name}({cnt})" for name, cnt in (py_imports + js_imports)[:10]
        )
        kw = scan_result.get("keyword_frequency", {})
        top_keywords = ", ".join(list(kw.keys())[:15])
        readme = scan_result.get("readme", {})
        readme_snippet = (readme.get("content") or "")[:500]

    return _DOMAIN_SKILL_PROMPT_TEMPLATE.format(
        domain_key=domain_key,
        display=entry.get("display", domain_key),
        assumptions=entry.get("assumptions", []),
        pitfalls=entry.get("critical_review_checklist", []),
        tech_stack=tech_stack or [],
        project_description=project_description or "(미지정)",
        top_imports=top_imports or "(없음)",
        top_keywords=top_keywords or "(없음)",
        readme_snippet=readme_snippet or "(없음)",
    )


def render_skill_md_from_spec(
    spec: dict[str, Any],
    domain_key: str,
    generated_at: str | None = None,
) -> str:
    """Claude 가 반환한 skill spec (dict) 을 SKILL.md 형식으로 렌더링.

    Args:
        spec: skills[] 배열의 단일 원소
        domain_key: 도메인 키
        generated_at: ISO 날짜 (기본: 오늘)

    Returns:
        SKILL.md 형식 문자열
    """
    if generated_at is None:
        from datetime import datetime
        generated_at = datetime.now().strftime("%Y-%m-%d")

    name = spec["name"]
    desc = spec["description"]
    auto_trigger = spec.get("auto_trigger", True)

    lines: list[str] = []
    # frontmatter
    lines.append("---")
    lines.append(f"name: {name}")
    lines.append(f"description: |")
    lines.append(f"  {desc}")
    lines.append(f"version: 1.0.0")
    lines.append(f"auto_trigger: {str(auto_trigger).lower()}")
    lines.append(f"domain: {domain_key}")
    lines.append(f"generated_at: {generated_at}")
    lines.append("---")
    lines.append("")
    # 제목
    lines.append(f"# {name.replace('-', ' ').title()}")
    lines.append("")
    lines.append(desc.strip())
    lines.append("")

    # Trigger
    lines.append("## Trigger")
    lines.append("")
    for t in spec.get("trigger_bullets", []):
        lines.append(f"- {t}")
    lines.append("")

    # Procedure
    steps = spec.get("procedure_steps", [])
    lines.append(f"## Procedure ({len(steps)} 단계)")
    lines.append("")
    for i, step in enumerate(steps, 1):
        lines.append(f"### {i}. {step['title']}")
        lines.append("")
        lines.append(step["body"])
        lines.append("")

    # Domain Pitfalls
    lines.append("## Domain Pitfalls")
    lines.append("")
    for p in spec.get("domain_pitfalls", []):
        lines.append(f"- **{p['pitfall']}**")
        lines.append(f"  - 회피: {p['avoidance']}")
    lines.append("")

    # Tools & References
    lines.append("## Tools & References")
    lines.append("")
    for tool in spec.get("tools", []):
        lines.append(f"- {tool}")
    lines.append("")

    # 호출 규약
    lines.append("## 호출 규약")
    lines.append("")
    req = spec.get("call_context_required", [])
    opt = spec.get("call_context_optional", [])
    res = spec.get("result_keys", [])
    lines.append(f"- `SkillCall(\"{name}\", context={{...}})`")
    if req:
        lines.append(f"- context 필수: {', '.join(f'`{k}`' for k in req)}")
    if opt:
        lines.append(f"- context 선택: {', '.join(f'`{k}`' for k in opt)}")
    if res:
        lines.append(f"- result 반환 키: {', '.join(f'`{k}`' for k in res)}")
    lines.append("")

    # 실패 모드
    lines.append("## 실패 모드")
    lines.append("")
    for f in spec.get("failure_modes", []):
        lines.append(f"- {f}")
    lines.append("")

    return "\n".join(lines)


def install_domain_skills(
    target_dir: _Path | str,
    domain_key: str,
    skill_specs: list[dict[str, Any]],
    *,
    validate: bool = True,
    max_regenerations: int = 2,
) -> dict[str, Any]:
    """도메인 skill spec 목록을 target_dir 에 SKILL.md 파일로 설치.

    각 spec 에 대해 render_skill_md_from_spec() 으로 렌더링 후
    validate_skill_md() 로 검증. 실패 시 max_regenerations 번까지
    재생성 요청 신호 반환 (실제 재생성은 Claude 가 수행).

    Args:
        target_dir: `.claude/skills/` 같은 대상 디렉토리
        domain_key: 도메인 키
        skill_specs: Claude 가 반환한 skills[] 배열
        validate: True 면 자가 검증 수행
        max_regenerations: 검증 실패 시 재생성 시도 횟수

    Returns:
        {
            "installed": [{name, path}, ...],
            "validation_failed": [{name, errors}, ...],
            "regeneration_needed": [{name, reason}, ...],
        }
    """
    target = _Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    installed: list[dict[str, str]] = []
    validation_failed: list[dict[str, Any]] = []
    regeneration_needed: list[dict[str, Any]] = []

    for spec in skill_specs:
        name = spec.get("name")
        if not name:
            validation_failed.append({
                "name": "(unknown)",
                "errors": ["name 필드 누락"],
            })
            continue

        skill_dir = target / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(exist_ok=True)

        content = render_skill_md_from_spec(spec, domain_key)
        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(content, encoding="utf-8")

        if validate:
            result = validate_skill_md(content)
            if not result["passed"]:
                validation_failed.append({
                    "name": name,
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                })
                regeneration_needed.append({
                    "name": name,
                    "reason": "validation failed",
                    "attempts_remaining": max_regenerations,
                })
                continue

        installed.append({"name": name, "path": str(skill_md_path)})

    return {
        "installed": installed,
        "validation_failed": validation_failed,
        "regeneration_needed": regeneration_needed,
    }


# ──────────────────────────────────────────────────────────────────
# v2.5.0+: Composite Architecture 연동
# ──────────────────────────────────────────────────────────────────

def render_composite_agents(
    domains: list[str],
    project_name: str = "(미지정)",
    persist_dir: _Path | str | None = None,
) -> dict[str, str]:
    """Composite Architecture 전체 에이전트 .md 파일 생성.

    Args:
        domains: 활성 도메인 키 목록
        project_name: 프로젝트 이름
        persist_dir: 저장 디렉토리 (None 이면 저장 안 함, dict 만 반환)

    Returns:
        {agent_filename: markdown_content, ...}  (c-*/x-* 전부 포함)
    """
    try:
        import architecture_patterns as ap
    except ImportError:
        raise ImportError(
            "architecture_patterns 모듈 필요 (v2.5.0+). "
            "scripts/ 경로에 architecture_patterns.py 가 있는지 확인."
        )

    # 도메인 엔트리 수집 (정적 + 동적 병합)
    domain_entries: dict[str, dict[str, Any]] = {}
    for key in domains:
        entry = get_domain(key)
        if entry:
            domain_entries[key] = entry

    # Composite 스펙 생성 (18 스펙 예상)
    specs = ap.build_composite_agents(
        domains=domains,
        domain_entries=domain_entries,
        project_name=project_name,
    )

    # 각 스펙마다 c-*.md + x-*.md 렌더링
    result: dict[str, str] = {}
    for spec in specs:
        kind = spec["kind"]
        c_md = ap.render_composite_agent_markdown(spec, side="c")
        x_md = ap.render_composite_agent_markdown(spec, side="x")
        result[f"c-{kind}.md"] = c_md
        result[f"x-{kind}.md"] = x_md

    # 파일로 저장 (옵션)
    if persist_dir is not None:
        persist_path = _Path(persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)
        for fname, content in result.items():
            (persist_path / fname).write_text(content, encoding="utf-8")

    return result


def list_composite_patterns_summary() -> str:
    """Composite 패턴 요약을 markdown 문자열로 반환 (bootstrap 출력용)."""
    try:
        import architecture_patterns as ap
    except ImportError:
        return "(architecture_patterns 미설치)"
    patterns = ap.list_patterns()
    lines = ["| 패턴 | 페어 수 | 활성 STEP | 토론 |", "|---|---|---|---|"]
    for p in patterns:
        active = p["active_steps"]
        if active == "always":
            active = "항상"
        else:
            active = ", ".join(active)
        debate = "✅" if p["debate_enabled"] else "—"
        lines.append(
            f"| {p['emoji']} {p['name']} | {p['pair_count']} | {active} | {debate} |"
        )
    return "\n".join(lines)
