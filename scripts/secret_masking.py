#!/usr/bin/env python3
"""secret_masking.py — 자격증명(API key·token) 평문 저장 방지용 **공용** 마스킹.

session_logger(turn-start 프롬프트 캡처) + capture_worker(PostToolUse 이벤트 enqueue) 공용.
**redaction 전용** — enforcement/차단 아님. keyfile(예: ~/.claude/gemini.env)의 정당한 키는
대상 아님(이 모듈은 로그·큐·아카이브에 흘러든 평문 복제본만 마스킹).

치환 규칙(요청 사양):
  - Google/Gemini 계열(AIza…, AQ.…, GEMINI_API_KEY=…, X-goog-api-key: …) → [REDACTED_GEMINI_API_KEY]
  - 그 외 자격증명(Bearer …, sk-…, sk-ant-…, ya29.…, ghp_…, glpat-…, AKIA…, *_key/secret/token=…)
    → [REDACTED_SECRET]

값 자체는 절대 출력하지 않는다(치환만). 키 이름(GEMINI_API_KEY 등)은 보존하고 값만 가린다.
"""
from __future__ import annotations

import re

GEMINI_PLACEHOLDER = "[REDACTED_GEMINI_API_KEY]"
SECRET_PLACEHOLDER = "[REDACTED_SECRET]"

# 순서 중요: KEY=VALUE/헤더(값만 치환)를 먼저 처리한 뒤, 값 자체 포맷을 처리.
SECRET_PATTERNS = [
    # KEY=VALUE / 헤더 — 키 이름 보존, 값만 마스킹
    (re.compile(r"(GEMINI_API_KEY\s*[=:]\s*)([A-Za-z0-9._\-]{6,})"),
     r"\1" + GEMINI_PLACEHOLDER),
    (re.compile(r"(X-goog-api-key\s*:\s*)([A-Za-z0-9._\-]{6,})", re.IGNORECASE),
     r"\1" + GEMINI_PLACEHOLDER),
    (re.compile(r"((?:api[_-]?key|secret|token|password|passwd)\s*[=:]\s*)([A-Za-z0-9._\-]{16,})",
                re.IGNORECASE),
     r"\1" + SECRET_PLACEHOLDER),
    # Bearer 토큰 (Authorization 헤더 등) — long token 형태
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1" + SECRET_PLACEHOLDER),
    # 값 자체 포맷 — Google/Gemini
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), GEMINI_PLACEHOLDER),   # 구형 Google API key
    (re.compile(r"AQ\.[A-Za-z0-9._\-]{6,}"), GEMINI_PLACEHOLDER),   # 신형 Google API key
    # 값 자체 포맷 — 기타 자격증명
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), SECRET_PLACEHOLDER),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), SECRET_PLACEHOLDER),
    (re.compile(r"ya29\.[0-9A-Za-z._\-]{20,}"), SECRET_PLACEHOLDER),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), SECRET_PLACEHOLDER),
    (re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"), SECRET_PLACEHOLDER),
    (re.compile(r"AKIA[0-9A-Z]{16}"), SECRET_PLACEHOLDER),
]

# 잔존(residual) 스캔용 — **값 자체 포맷만**(치환 후 0이어야 함). 보고 시 값은 절대 출력 금지.
RESIDUAL_VALUE_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[A-Za-z0-9._\-]{6,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z._\-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def mask_secrets(text):
    """문자열에서 자격증명 패턴을 마스킹해 반환. 비문자열·빈값은 그대로 반환."""
    if not text or not isinstance(text, str):
        return text
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def count_matches(text):
    """마스킹될 자격증명 매치 총 개수(보고용). 값은 반환하지 않음."""
    if not text or not isinstance(text, str):
        return 0
    return sum(len(pat.findall(text)) for pat, _ in SECRET_PATTERNS)


def residual_count(text):
    """마스킹 후에도 남은 **값-형식** 자격증명 개수(0 기대). 값은 반환하지 않음."""
    if not text or not isinstance(text, str):
        return 0
    return sum(len(pat.findall(text)) for pat in RESIDUAL_VALUE_PATTERNS)
