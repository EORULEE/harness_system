#!/usr/bin/env python3
"""Canary test for Dev Discipline Suite (DEV:tdd). Self-contained, no external deps.
Run: python3 test_slugify.py  ->  exit 0 if all pass, 1 otherwise."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slugify import slugify  # RED: slugify.py가 없으면 ImportError (올바른 실패 이유)

CASES = [
    ("AC1", "Hello World", "hello-world"),
    ("AC2", "foo_bar Baz", "foo-bar-baz"),
    ("AC3", "a--b__c  d", "a-b-c-d"),
    ("AC4", "  --Trim-- ", "trim"),
    ("AC5", "Café!@#123", "caf123"),
    ("AC6", "", ""),
]

def main():
    fails = 0
    for ac, inp, exp in CASES:
        got = slugify(inp)
        ok = got == exp
        print(f"  {'PASS' if ok else 'FAIL'} {ac}: slugify({inp!r}) = {got!r}" + ("" if ok else f"  (기대 {exp!r})"))
        if not ok:
            fails += 1
    total = len(CASES)
    print(f"== {total - fails}/{total} PASS, {fails} FAIL ==")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
