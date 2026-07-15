#!/usr/bin/env python3
"""paper_final_check.py — 범용 논문 구조 검수 게이트 (5계층 리뷰 계층1).

투고 전 최종 빌드 docx를 kordoc으로 Markdown 추출한 뒤, 내용 품질이 아니라
**구조적 결함**을 기계 검사한다. HARD 결함이 있으면 exit 1(투고 금지 게이트).

severity 체계 (codex 검토 2026-07-07 반영):
  HARD (exit 1) — 고신뢰 구조 결함: 참조하나 캡션 없음(parity)·placeholder·한글 잔재(영문 저널)
  WARN (exit 0) — 휴리스틱 경고: 초록 단어수·Highlights 자수·미참조 캡션·캡션 결번·한글 잔재(한글 저널)

검사 항목(계약 AC2~AC5):
  1. parity        — 본문 그림/표/식 참조 ↔ 캡션 대조(범위 'Figures 1-3'·복수·영문 Eq. 지원)
  2. caption_seq   — 캡션 번호 연속성(WARN)
  3. abstract_len  — 초록 단어수 ≤ 저널 abstract_word_limit(WARN; heading 변형 지원)
  4. highlights    — Highlights 항목당 글자수 ≤ 한도(WARN)
  5. placeholder   — TBD·TODO·[확인 필요]·XXX(HARD)
  6. lang_residue  — 한글 잔재(본문·표·수식 LaTeX). 참고문헌/감사글 zone 제외.
                     영문 저널(en/미지정)=HARD, 한글 저널(ko)=WARN(항상 검출은 하되 판정만 강등).

저널 파라미터·언어는 journal-profiles.yaml에서 읽는다(하드코딩 금지).

사용:
  python3 paper_final_check.py <build.docx> [--journal RS] [--profiles <path>] [--md <추출본>]
  exit 0 = PASS(HARD 결함 0), exit 1 = FAIL(HARD 결함), exit 2 = 실행 오류
"""
import sys
import os
import re
import json
import argparse
import subprocess

try:
    import yaml
except ImportError:
    yaml = None

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
def _default_profiles():
    """프로젝트-로컬 우선(자기완결), 없으면 글로벌 폴백."""
    cands = [
        os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."),
                     ".claude/skills/_paper-review-core/journal-profiles.yaml"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".claude/skills/_paper-review-core/journal-profiles.yaml"),
        os.path.expanduser("~/.claude/skills/_paper-review-core/journal-profiles.yaml"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[-1]

DEFAULT_PROFILES = _default_profiles()
PLACEHOLDER_PAT = re.compile(
    r"(?<![A-Za-z])(TBD|TODO|FIXME|XXX+|\[?확인\s*필요\]?|\bplaceholder\b|lorem ipsum)",
    re.IGNORECASE,
)
# 참고문헌·감사글·저자정보 zone 시작(이후 라인은 lang_residue 제외 — 서지 한글 오탐 차단)
BIB_ZONE = re.compile(
    r"^\s*(참고\s*문헌|References|Bibliography|감사의?\s*글|Acknowledge?ments?|"
    r"저자\s*정보|Author\s+Contributions?|Affiliations?|ORCID)\b",
    re.IGNORECASE,
)


def die(msg, code=2):
    print(f"[paper_final_check] 오류: {msg}", file=sys.stderr)
    sys.exit(code)


def extract_markdown(docx_path, md_override=None):
    if md_override:
        with open(md_override, encoding="utf-8") as f:
            return f.read()
    out = docx_path + ".kordoc.md"
    try:
        subprocess.run(
            ["npx", "-y", "kordoc@latest", docx_path, "-o", out, "--silent"],
            check=True, capture_output=True, timeout=420,
        )
    except FileNotFoundError:
        die("npx/kordoc 미설치 — kordoc MCP 환경 필요(또는 --md로 추출본 지정)")
    except subprocess.CalledProcessError as e:
        die(f"kordoc 추출 실패: {e.stderr.decode('utf-8', 'replace')[:300]}")
    except subprocess.TimeoutExpired:
        die("kordoc 추출 타임아웃")
    with open(out, encoding="utf-8") as f:
        return f.read()


def load_journal(journal, profiles_path):
    """journal-profiles에서 파라미터+언어. 미지정 시 default(관대·언어 None)."""
    info = {"abstract_word_limit": None, "highlights_char_limit": None, "language": None}
    if yaml is None or not os.path.exists(profiles_path):
        return info
    with open(profiles_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    default = data.get("default", {}) or {}
    prof = (data.get("profiles", {}) or {}).get(journal) if journal else None
    src = prof if prof else default
    for k in ("abstract_word_limit", "highlights_char_limit"):
        info[k] = src.get(k) if src.get(k) is not None else default.get(k)
    lang = src.get("language")
    info["language"] = None if lang in (None, "follow_manuscript") else lang
    return info


def _boundary(w):
    return r"(?<![가-힣])" if re.match(r"[가-힣]", w) else r"(?<![A-Za-z])"


def _valid(n):
    return 1 <= n <= 199


def _expand_numlist(s):
    """'1-3', '1 and 2', '1, 2, 4' → {1,2,3,...}. 범위·복수·리스트 파싱(F-03)."""
    nums = set()
    s = s.replace("–", "-").replace("&", " and ")
    for part in re.split(r"[,\s]+and\s+|,", s):
        part = part.strip()
        rng = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b and b - a < 100:
                nums.update(range(a, b + 1))
        else:
            m = re.match(r"^(\d+)", part)
            if m:
                nums.add(int(m.group(1)))
    return {n for n in nums if _valid(n)}


def _caption_nums(md, kind_words):
    nums = set()
    for w in kind_words:
        for m in re.finditer(rf"(?:^|\n)\s*{_boundary(w)}{w}s?\.?\s*(\d+)", md):
            n = int(m.group(1))
            if _valid(n):
                nums.add(n)
    return nums


def _ref_nums(md, kind_words):
    """본문 참조 — 범위/복수 포함. 'Figures 1-3', 'Figs. 1 and 2', '그림 1·2'."""
    nums = set()
    for w in kind_words:
        for m in re.finditer(rf"{_boundary(w)}{w}s?\.?\s*([\d]+(?:\s*[-–,]\s*\d+|\s+and\s+\d+|[·]\s*\d+)*)", md):
            nums |= _expand_numlist(m.group(1).replace("·", ","))
    return nums


def check_parity(md):
    """HARD: 참조하나 캡션 없음. WARN: 미참조 캡션(orphan)."""
    hard, warn = [], []
    for label, words in [("그림/Figure", ["그림", "Figure", "Fig"]),
                         ("표/Table", ["표", "Table"])]:
        caps = _caption_nums(md, words)
        refs = _ref_nums(md, words)
        missing = sorted(refs - caps)
        orphan = sorted(caps - refs)
        if missing:
            hard.append(f"{label}: 본문 참조하나 캡션 없음 → {missing}")
        if orphan:
            warn.append(f"{label}: 미참조 캡션 → {orphan}")
    # 식/Eq — 영문 Eq.(F-01: 두 분기 모두 카운트)
    eq_refs = set()
    for m in re.finditer(r"(?:식\s*\(?(\d+)\)?)|(?:Eq(?:uation)?s?\.?\s*\(?(\d+)\)?)", md, re.IGNORECASE):
        n = m.group(1) or m.group(2)
        if n and _valid(int(n)):
            eq_refs.add(int(n))
    eq_nums = set(int(m.group(1)) for m in re.finditer(r"\((\d+)\)\s*\$", md) if _valid(int(m.group(1))))
    if eq_refs and eq_nums:
        miss = sorted(eq_refs - eq_nums)
        if miss:
            hard.append(f"식/Eq: 본문 참조하나 수식 없음 → {miss}")
    detail = "; ".join(hard + warn) if (hard or warn) else "parity OK"
    return ("hard" if hard else "warn", not hard, detail, bool(warn))


def check_caption_seq(md):
    fails = []
    for label, words in [("그림", ["그림", "Figure", "Fig"]), ("표", ["표", "Table"])]:
        caps = sorted(_caption_nums(md, words))
        if caps:
            gaps = sorted(set(range(1, max(caps) + 1)) - set(caps))
            if gaps:
                fails.append(f"{label} 캡션 결번 → {gaps} (최대 {max(caps)})")
    return ("warn", True, "; ".join(fails) if fails else "caption 연속 OK", bool(fails))


def check_abstract_len(md, limit):
    if not limit:
        return ("warn", True, "abstract 한도 미지정(skip)", False)
    # heading 변형(F-04): '# Abstract', 'Abstract:', 'ABSTRACT', '초록', 번호
    m = re.search(
        r"(?:^|\n)\s*#*\s*(?:\d+\.?\s*)?(?:초록|Abstract)\s*[:：]?\s*(?:\([^)]*\))?\s*\n+(.+?)"
        r"(?=\n\s*#*\s*(?:키워드|Keywords|Highlights|\d+\.|서론|Introduction|Figure|Table|그림|표|References|참고문헌)|\Z)",
        md, re.IGNORECASE | re.DOTALL)
    if not m:
        return ("warn", True, "abstract 섹션 미검출(skip)", False)
    words = len(re.findall(r"\S+", m.group(1)))
    ok = words <= limit
    return ("warn", True, f"abstract {words}단어 (한도 {limit})" + ("" if ok else " ← 초과(경고)"), not ok)


def check_highlights(md, limit):
    if not limit:
        return ("warn", True, "highlights 한도 미지정(skip)", False)
    m = re.search(r"(?:하이라이트|Highlights)\s*(?:\([^)]*\))?\s*\n(.+?)(?=\n\s*(?:\d+\.|서론|Introduction|초록|Abstract)|\Z)",
                  md, re.IGNORECASE | re.DOTALL)
    if not m:
        return ("warn", True, "highlights 섹션 미검출(skip)", False)
    items = [re.sub(r"^[•\-\*·]\s*", "", ln).strip() for ln in m.group(1).splitlines() if ln.strip()]
    over = [(i + 1, len(it)) for i, it in enumerate(items) if len(it) > limit]
    return ("warn", True, f"highlights {len(items)}항목, 한도 {limit}자" + ("" if not over else f" ← 초과 {over}(경고)"), bool(over))


def check_placeholder(md):
    hits = [m.group(0) for m in PLACEHOLDER_PAT.finditer(md)]
    return ("hard", not hits, "placeholder 없음" if not hits else f"placeholder 잔재 {len(hits)}건 → {sorted(set(hits))[:8]}", False)


def check_lang_residue(md, language):
    """한글 잔재 — 항상 검출(스캔). 참고문헌/감사글 zone 제외(F-05).
    영문 저널(en/미지정)=HARD, 한글 저널(ko)=WARN(F-06)."""
    in_bib = False
    body_hits, eq_hits = [], []
    for i, ln in enumerate(md.splitlines(), 1):
        if BIB_ZONE.match(ln):
            in_bib = True
        if in_bib:
            continue  # 서지·저자·소속 zone 제외
        if HANGUL.search(ln):
            if re.search(r"\$.*[가-힣].*\$", ln) or re.match(r"\s*\(\d+\)\s*\$", ln):
                eq_hits.append(i)
            else:
                body_hits.append(i)
    total = len(body_hits) + len(eq_hits)
    is_ko = (language == "ko")
    sev = "warn" if is_ko else "hard"
    if total == 0:
        return (sev, True, "한글 잔재 없음", False)
    detail = (f"한글 잔재 {total}건 (본문 {len(body_hits)}줄, 수식내부 {len(eq_hits)}줄"
              + (f" ← OMML 수식 한글 L{eq_hits[:5]}" if eq_hits else "")
              + (") [한글 저널=경고]" if is_ko else ") [영문 저널=HARD, 참고문헌 zone 제외]"))
    # ko: WARN(ok=True, warn플래그) / en: HARD(ok=False)
    return (sev, is_ko, detail, is_ko)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--journal", default=None)
    ap.add_argument("--profiles", default=DEFAULT_PROFILES)
    ap.add_argument("--md", default=None, help="추출 md 직접 지정(kordoc 우회)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.md and not os.path.exists(args.docx):
        die(f"파일 없음: {args.docx}")
    md = extract_markdown(args.docx, args.md)
    jr = load_journal(args.journal, args.profiles)

    raw = [
        ("parity", check_parity(md)),
        ("caption_seq", check_caption_seq(md)),
        ("abstract_len", check_abstract_len(md, jr["abstract_word_limit"])),
        ("highlights", check_highlights(md, jr["highlights_char_limit"])),
        ("placeholder", check_placeholder(md)),
        ("lang_residue", check_lang_residue(md, jr["language"])),
    ]
    results = []
    hard_fail = False
    for name, (sev, ok, detail, warned) in raw:
        status = "PASS"
        if sev == "hard" and not ok:
            status = "FAIL"; hard_fail = True
        elif warned or (not ok):
            status = "WARN"
        results.append({"check": name, "severity": sev, "status": status, "detail": detail})

    if args.json:
        print(json.dumps({"verdict": "FAIL" if hard_fail else "PASS",
                          "journal": args.journal, "language": jr["language"],
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== paper_final_check: {os.path.basename(args.docx)} "
              f"(저널={args.journal or 'default'}, 언어={jr['language'] or 'n/a'}) ===")
        for r in results:
            print(f"  [{r['status']:4s}] {r['check']:14s} {r['detail']}")
        print(f"=== 판정: {'FAIL — 투고 금지(HARD 결함)' if hard_fail else 'PASS — HARD 결함 0(WARN은 검토 권고)'} ===\n")

    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
