#!/usr/bin/env python3
"""Canary impl for Dev Discipline Suite (DEV:tdd). Pure function, no external deps."""
import re


def slugify(text: str) -> str:
    """문자열을 kebab-case ASCII slug로 변환(순수함수).

    소문자화 → 공백·언더스코어를 하이픈으로 → [a-z0-9-] 외 제거 →
    연속 하이픈 단일화 → 앞뒤 하이픈 제거.
    """
    s = text.lower()
    s = re.sub(r"[\s_]+", "-", s)     # 공백·언더스코어 → 하이픈
    s = re.sub(r"[^a-z0-9-]", "", s)  # 허용문자 외 제거
    s = re.sub(r"-+", "-", s)         # 연속 하이픈 단일화
    return s.strip("-")               # 앞뒤 하이픈 제거
