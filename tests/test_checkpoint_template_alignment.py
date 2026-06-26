#!/usr/bin/env python3
"""parser ↔ checkpoint 템플릿 라벨 정합 테스트.
project_checkpoint_prompt.md 의 표준 섹션 라벨이 session_continuity_worker.py 의 parser와
정확히 정합하는지 검증. worker 로직은 변경하지 않음(읽기만). 결정적·오프라인."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from session_continuity_worker import (COMPLETED_LABELS, LOCKED_LABELS, _norm_label,
                                        extract_from_checkpoint, extract_labeled_bullets)

PROMPT = os.path.expanduser("~/.claude/lib/project_checkpoint_prompt.md")
fails = []
def chk(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c:
        fails.append(m)

# --- 1) 템플릿이 parser 라벨을 사용하는지 ---
t = open(PROMPT, encoding="utf-8").read() if os.path.isfile(PROMPT) else ""
labels = [_norm_label(s) for s in re.findall(r'^##\s+(.*\S)\s*$', t, re.M)]
comp_set = {_norm_label(x) for x in COMPLETED_LABELS}
lock_set = {_norm_label(x) for x in LOCKED_LABELS}
chk("완료" in labels and "완료" in comp_set, "템플릿 `## 완료` ∈ parser COMPLETED_LABELS")
chk("고정 사실" in labels and "고정 사실" in lock_set, "템플릿 `## 고정 사실` ∈ parser LOCKED_LABELS")
chk(any("작업 목표" in l for l in labels), "템플릿 `## 작업 목표`(objective parser 라벨)")
chk(any("다음 첫 행동" in l for l in labels), "템플릿 `## 다음 첫 행동`(next_action parser 라벨)")

# --- 2) 템플릿 골격으로 만든 체크포인트가 실제로 추출되는지(end-to-end) ---
sample = ("## 작업 목표\n보고서 작성\n"
          "## 다음 첫 행동: 목차 4 작성\n"
          "## 완료\n- 목차 1 작성\n- 목차 2 작성\n"
          "## 고정 사실\n- 언어 한국어\n- 총 5개\n"
          "## 변경 파일\n- scripts/x.py\n")
o = extract_from_checkpoint({"text": sample})
chk(o.get("current_objective") == "보고서 작성", "objective 추출 정확")
chk(o.get("next_action") == "목차 4 작성", "next_action 추출 정확")
comp, _, _ = extract_labeled_bullets(sample, COMPLETED_LABELS)
lock, _, _ = extract_labeled_bullets(sample, LOCKED_LABELS)
chk(comp == ["목차 1 작성", "목차 2 작성"], f"completed verbatim={comp}")
chk(lock == ["언어 한국어", "총 5개"], f"locked_facts verbatim={lock}")

# --- 3) 규칙: 빈 고정 사실 섹션 → [] / 다른 섹션 bullet 미혼입 ---
empty = "## 완료\n- A\n## 고정 사실\n## 변경 파일\n- f.py\n"
le, _, _ = extract_labeled_bullets(empty, LOCKED_LABELS)
ce, _, _ = extract_labeled_bullets(empty, COMPLETED_LABELS)
chk(le == [], f"빈 고정사실 섹션 → [] ({le})")
chk(ce == ["A"] and "f.py" not in ce, "완료 섹션이 변경파일 bullet 미혼입")

print(f"\n== template-parser 정합: {'PASS' if not fails else 'FAIL ' + str(fails)} ==")
sys.exit(0 if not fails else 1)
