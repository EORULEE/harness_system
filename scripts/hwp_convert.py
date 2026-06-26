#!/usr/bin/env python3
"""
hwp_convert.py — HWP/HWPX ↔ DOCX 양방향 변환 (한컴 COM, 충실도 보존)

⚠️ Windows 전용 + 한컴오피스 필수. 한컴 엔진이 직접 변환 → 그림·표 최대 보존.
   (Linux는 한컴 미지원 → 변환 불가. 읽기는 rhwp 사용.)

방향은 확장자로 자동 결정:
  .hwp/.hwpx → .docx/.pdf/.html  ✅ 자동화 정상 (검증: 그림·표 보존)
  .docx/.doc → .hwp              ⚠️ 자동화 불안정 — 한컴 외부문서 가져오기가
                                    COM 자동화에서 빈 문서로 열림(2026-05-28 실측).
                                    → DOCX→HWP는 한컴에서 수동으로 열어 저장 권장.
  변환 후 빈 결과(PageCount<=1) 감지 시 경고.

검증된 동작: HWP→DOCX (OOXML save) — test.hwp 5p/표7/그림1 → docx 정상 보존.

한컴 format 코드 (open/save_as):
  HWP=한글, HWPML2X=한글XML, OOXML=docx, DOCRTF=doc, HTML, PDF, UNICODE, TEXT

사용:
  python hwp_convert.py <in> <out>
예:
  python hwp_convert.py report.hwp report.docx     # HWP→DOCX
  python hwp_convert.py report.docx report.hwp     # DOCX→HWP
  python hwp_convert.py report.hwp report.pdf      # HWP→PDF
"""

import os
import sys

# 확장자 → 한컴 format 코드
EXT_FORMAT = {
    ".hwp": "HWP",
    ".hwpx": "HWPX",
    ".docx": "OOXML",
    ".doc": "DOCRTF",
    ".pdf": "PDF",
    ".html": "HTML",
    ".htm": "HTML",
    ".txt": "TEXT",
    ".rtf": "RTF",
}


def fmt_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXT_FORMAT:
        raise ValueError(f"지원하지 않는 확장자: {ext} (지원: {', '.join(EXT_FORMAT)})")
    return EXT_FORMAT[ext]


def main():
    if len(sys.argv) != 3:
        print("usage: python hwp_convert.py <in> <out>")
        print("  예: hwp_convert.py report.hwp report.docx  (HWP→DOCX)")
        print("      hwp_convert.py report.docx report.hwp  (DOCX→HWP)")
        sys.exit(2)

    in_path, out_path = sys.argv[1], sys.argv[2]
    in_fmt = fmt_for(in_path)
    out_fmt = fmt_for(out_path)

    try:
        from pyhwpx import Hwp
    except ImportError:
        print("❌ pyhwpx 미설치. Windows에서: pip install pyhwpx")
        print("   (Linux는 한컴 COM 불가 — 변환 불가)")
        sys.exit(3)

    try:
        hwp = Hwp(visible=False)
    except TypeError:
        hwp = Hwp()
        try:
            hwp.set_visible(False)
        except Exception:
            pass

    try:
        # HWP/HWPX는 format="" 자동인식이 안전, 그 외(docx 등)는 명시
        open_fmt = "" if in_fmt in ("HWP", "HWPX") else in_fmt
        foreign_in = in_fmt not in ("HWP", "HWPX")
        hwp.open(in_path, format=open_fmt)  # 반환값 unreliable

        # ⚠️ PageCount 접근은 HWP 입력에서 hang 유발 가능 → foreign 입력일 때만 검사.
        if foreign_in:
            try:
                pages = int(hwp.PageCount)
            except Exception:
                pages = -1
            if pages <= 1:
                print(f"❌ 외부문서 로드 실패(빈 문서, PageCount={pages}): {in_path}")
                print("   한컴 COM이 docx/doc 가져오기를 자동화에서 지원 못 함(2026-05-28 실측). "
                      "한컴에서 수동으로 열어 .hwp로 저장하세요.")
                sys.exit(1)

        ok = hwp.save_as(out_path, format=out_fmt)
        print(f"{'✅' if ok else '⚠️'} 변환: {in_path} ({in_fmt}) → {out_path} ({out_fmt}) | save_as={ok}")
    finally:
        hwp.quit()


if __name__ == "__main__":
    main()
