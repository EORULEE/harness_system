#!/usr/bin/env python3
"""pair_router.py — 도메인 스택 → 관련 c-/x- 페어 0~3개 자동 선택 (r5 adaptive).

얇은 결정적 선택기. 전체 6~8 영구 pair 를 부르지 않고 관련 0~3개만 고른다.
입력: domain_stack(5계층) + pair-topology(역할 축 매핑). 출력: selected_pairs.
정본 스키마: .claude/skills/_loop-core/schemas/pair-topology-schema.yaml
파일 수정 없음(순수 함수 + stdout).
"""
from __future__ import annotations
import argparse
import json

# 도메인 계층 신호 → 역할 축(pair-topology role_axes) 매핑
LAYER_TO_AXIS = {
    "science_domains":     "1-domain-science",
    "observation_domains": "3-geospatial-physical",
    "method_domains":      "4-code-ml-model",
    "validation_domains":  "5-experiment-stats-repro",
    "output_domains":      "6-writing-claims-citations",
}
MAX_PAIRS = 3


def select_pairs(active_layers: list[str], topology: str) -> dict:
    if topology == "none":
        return {"selected_pairs": [], "reason": "review_topology=none → pair 0"}
    axes = []
    for layer in active_layers:
        ax = LAYER_TO_AXIS.get(layer)
        if ax and ax not in axes:
            axes.append(ax)
    if topology == "intra-pair":
        axes = axes[:1] if axes else ["4-code-ml-model"]   # 단일 도메인 전문 → 1 pair
    else:  # cross-domain
        axes = axes[:MAX_PAIRS]                              # 관련 최대 3
    return {"selected_pairs": axes, "count": len(axes),
            "reason": f"topology={topology} → 관련 {len(axes)} pair(전체 6~8 호출 안 함)"}


def main() -> int:
    ap = argparse.ArgumentParser(description="pair router (deterministic, 0~3 pairs)")
    ap.add_argument("--topology", required=True, choices=["none", "intra-pair", "cross-domain"])
    ap.add_argument("--active-layers", default="", help="콤마구분: science_domains,method_domains,...")
    args = ap.parse_args()
    layers = [s.strip() for s in args.active_layers.split(",") if s.strip()]
    out = select_pairs(layers, args.topology)
    out["_note"] = "primary science 전용 pair 최대 2 · 3번째+ 도메인=domain profile/temporary specialist · x-agent Write/Edit 금지"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
