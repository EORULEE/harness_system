#!/usr/bin/env python3
"""code_claim_lint — 코드-동작 주장인데 file:line 인용이 없는 문장을 surface 하는 self-check 보조기.

dev-discipline 'code-claim evidence gate'(Layer 2)의 전송-직전 self-check 절차를 도구화한 것.
정본 규율 = .claude/skills/_dev-discipline-core/code-claim-evidence-rules.md

⚠️ heuristic 보조기지 완전 탐지기가 아니다. flag=0 이 "검증 완료"를 보증하지 않는다.
   목적 = "그 함수 안 읽고 추론으로 단정"한 문장 후보를 눈에 띄게 해, 사람/모델이 처리하게 함.
   flag 있으면 → 생산 함수 읽고 file:line 인용 추가 or "확실치 않음" 강등.

사용:  python3 scripts/code_claim_lint.py <draft.md | ->
종료:  flagged>0 → exit 1 (advisory gate) · 0 → exit 0
"""
import re
import sys

# 동작 주장 동사 (EN + KO) — "이 코드/값이 무엇을 한다"
VERB = re.compile(
    r"\b(comput\w*|calculat\w*|measur\w*|return\w*|read\w*|writ\w*|stor\w*|"
    r"averag\w*|mask\w*|filter\w*|aggregat\w*|map\w*|select\w*|sort\w*)\b"
    r"|(계산|측정|반환|평균값?|저장|마스킹|마스크|필터|집계|산출|선정|정렬|"
    r"읽(어|는|고)|쓰(는|고)|처리하)",
    re.IGNORECASE,
)
# 코드 토큰: 백틱·함수호출·점표기·snake_case·CamelCase
CODE = re.compile(
    r"`[^`]+`"
    r"|\b\w+\s*\("
    r"|\b\w+\.\w+"
    r"|\b\w*_\w+\b"
    r"|\b[a-z]+[A-Z]\w*\b"
)
# file:line 인용 또는 '라인/line N'
CITE = re.compile(
    r"\b[\w./-]+\.(py|js|mjs|ts|tsx|sh|ya?ml|json|c|cc|cpp|h|hpp|java|go|rs|rb|php|sql)\s*:\s*\d+\b"
    r"|\b(라인|line|L)\s*[:#]?\s*\d+\b",
    re.IGNORECASE,
)
# 주장이 아닌 것(질문·향후·예시) + 규범/메타("~해야/금지/동반/류"는 주장이 아니라 규칙 서술)은 제외
NONCLAIM = re.compile(
    r"(\?|할까|일까|예:|e\.g\.|예를 들|TODO|향후|나중에"
    r"|동반한다|금지|강등|surface|보조기|해야 |류\s|must\b|should\b)",
    re.IGNORECASE,
)

SENT_SPLIT = re.compile(r"(?<=[.。!?])\s+|(?<=다\.)\s*|\n")


def segments(text: str):
    """fenced code block 제외하고 (lineno, segment) 산출."""
    out, in_fence, lineno = [], False, 0
    for raw in text.splitlines():
        lineno += 1
        s = raw.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue
        if s.startswith("#") or s.startswith(">"):  # 헤딩·인용블록 스킵
            continue
        for seg in SENT_SPLIT.split(s):
            seg = seg.strip()
            if seg:
                out.append((lineno, seg))
    return out


def lint(text: str):
    flags = []
    for lineno, seg in segments(text):
        if NONCLAIM.search(seg):
            continue
        if VERB.search(seg) and CODE.search(seg) and not CITE.search(seg):
            flags.append((lineno, seg))
    return flags


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: code_claim_lint.py <file|->", file=sys.stderr)
        return 2
    src = sys.argv[1]
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    flags = lint(text)
    if not flags:
        print("code_claim_lint: OK — 인용 없는 코드-동작 주장 0 (단, flag 0 ≠ 검증완료; 핵심 주장 육안 재검토)")
        return 0
    print(f"code_claim_lint: ⚠️ {len(flags)} 건 — file:line 인용 없는 코드-동작 주장(생산 함수 읽고 인용 추가 or '확실치 않음' 강등):")
    for lineno, seg in flags:
        clip = seg if len(seg) <= 140 else seg[:137] + "..."
        print(f"  L{lineno}: {clip}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
