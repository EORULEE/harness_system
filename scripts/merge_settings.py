#!/usr/bin/env python3
"""merge_settings.py — Claude Code settings.json 훅 병합.

동작 원칙
- 기존 사용자의 settings.json은 최대한 보존한다.
- 단, 하네스가 관리하는 동일 hook command는 교체 대상으로 보고 최신 템플릿으로 덮어쓴다.
- event/matcher/command 조합이 동일하면 중복 추가하지 않는다.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


MANAGED_MARKERS = [
    # Node.js hook (v2.4.5-hardened Node.js 전환 이후 표준)
    "hooks/session-start.mjs",
    "hooks/user-prompt-submit.mjs",
    "hooks/pre-tool-use-task.mjs",
    "hooks/post-tool-use.mjs",
    "hooks/subagent-stop.mjs",
    "hooks/stop.mjs",
    # Legacy bash hook (pre-Node.js 전환 시절; 업그레이드 시 교체 대상)
    "hooks/session-start.sh",
    "hooks/user-prompt-submit.sh",
    "hooks/pre-tool-use-task.sh",
    "hooks/post-tool-use.sh",
    "hooks/subagent-stop.sh",
    "hooks/stop.sh",
    # Python script markers
    "session_logger.py turn-end",
    "capture_worker.py",
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def hook_key(entry: dict[str, Any], matcher: str | None) -> tuple[str | None, str]:
    return matcher, entry.get("command", "")


def is_harness_managed_command(command: str) -> bool:
    return any(marker in command for marker in MANAGED_MARKERS)


def merge_hooks(base: dict[str, Any], template: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    merged = deepcopy(base)
    merged.setdefault("hooks", {})
    report: list[str] = []

    for event_name, matcher_groups in template.get("hooks", {}).items():
        merged["hooks"].setdefault(event_name, [])
        existing_groups = merged["hooks"][event_name]

        # 이전 하네스 버전이 심어 둔 command는 제거하고 최신 템플릿으로 교체
        for group in existing_groups:
            kept = []
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                if is_harness_managed_command(cmd):
                    report.append(f"REPLACE {event_name} matcher={group.get('matcher') or '*'} command={cmd}")
                    continue
                kept.append(hook)
            group["hooks"] = kept

        existing_keys = set()
        for group in existing_groups:
            matcher = group.get("matcher")
            for hook in group.get("hooks", []):
                existing_keys.add(hook_key(hook, matcher))

        for tpl_group in matcher_groups:
            matcher = tpl_group.get("matcher")
            new_hooks = []
            for hook in tpl_group.get("hooks", []):
                key = hook_key(hook, matcher)
                if key in existing_keys:
                    report.append(f"SKIP {event_name} matcher={matcher or '*'} command={hook.get('command')}")
                    continue
                new_hooks.append(deepcopy(hook))
                existing_keys.add(key)
                report.append(f"ADD  {event_name} matcher={matcher or '*'} command={hook.get('command')}")

            if not new_hooks:
                continue

            target_group = None
            for group in existing_groups:
                if group.get("matcher") == matcher:
                    target_group = group
                    break
            if target_group is None:
                target_group = {"hooks": []}
                if matcher is not None:
                    target_group["matcher"] = matcher
                existing_groups.append(target_group)
            target_group.setdefault("hooks", []).extend(new_hooks)

        # 빈 그룹 정리
        merged["hooks"][event_name] = [g for g in existing_groups if g.get("hooks")]

    for k, v in template.items():
        if k.startswith("_") and k not in merged:
            merged[k] = deepcopy(v)
    return merged, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("target")
    ap.add_argument("--report")
    args = ap.parse_args()

    template = load_json(Path(args.template))
    target_path = Path(args.target)
    base = load_json(target_path)
    merged, report = merge_hooks(base, template)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    else:
        print("\n".join(report))


if __name__ == "__main__":
    main()
