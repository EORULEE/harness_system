#!/usr/bin/env python3
"""test_secret_masking.py — secret_masking 마스킹 + capture_worker enqueue 파이프라인 검증.

읽기 입력은 tests/fixtures/secret_samples.txt(가짜 키 전용). 키 원문은 출력하지 않는다.
실행: python3 tests/test_secret_masking.py   (프로젝트 루트에서)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from secret_masking import mask_secrets, residual_count  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "secret_samples.txt"

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    print(("PASS" if cond else "FAIL"), name)
    if cond:
        passed += 1
    else:
        failed += 1


# ── (1) fixture 각 줄 마스킹 ──────────────────────────────────────────
print("=== (1) fixture 마스킹 (가짜 키, 값 미출력) ===")
for line in FIXTURE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    label, text, expect = line.split("|", 2)
    masked = mask_secrets(text)
    if expect == "__UNCHANGED__":
        check(f"{label}: 비밀 아님 → 불변", masked == text and residual_count(masked) == 0)
    else:
        # placeholder 삽입 + 값-형식 잔존 0 (키 원문 비출력 위해 결과는 not-print)
        ok = (expect in masked) and (residual_count(masked) == 0)
        check(f"{label}: → {expect} & residual 0", ok)

# ── (2) GEMINI_API_KEY= 키이름 보존 확인 ────────────────────────────
print("=== (2) 키 이름 보존(값만 마스킹) ===")
m = mask_secrets("GEMINI_API_KEY=AQ.FAKE0000000000000000TEST")
check("GEMINI_API_KEY= 보존 + 값 마스킹", m == "GEMINI_API_KEY=[REDACTED_GEMINI_API_KEY]")

# ── (3) capture_worker enqueue → archive 파이프라인 (임시 cwd) ───────
print("=== (3) capture_worker enqueue/process → archive 마스킹 ===")
tmp = tempfile.mkdtemp(prefix="capw-")
cwd = os.getcwd()
try:
    os.chdir(tmp)
    import capture_worker  # scripts/ on path

    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "curl -H 'X-goog-api-key: AQ.FAKE0000000000000000TEST' https://x"},
        "tool_response": {"stdout": "AIzaSyFAKE0000000000000000000000TEST", "exit_code": 1, "stderr": "error: boom"},
    }
    capture_worker.enqueue_event(event)
    capture_worker.process_queue()
    arch = list(Path(".claude/runtime/_capture_archive").glob("*.json"))
    blob = "\n".join(p.read_text(encoding="utf-8") for p in arch)
    check("archive 생성됨", len(arch) >= 1)
    check("archive residual(값-형식 키) == 0", residual_count(blob) == 0)
    check("archive 에 placeholder 존재", "[REDACTED_GEMINI_API_KEY]" in blob)
finally:
    os.chdir(cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n=== {passed} pass / {failed} fail ===")
sys.exit(1 if failed else 0)
