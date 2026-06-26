#!/usr/bin/env python3
"""
hwp_merge_pyhwpx.py — 여러 .hwp/.hwpx를 하나로 병합 (한컴 COM, 충실도 보존)

⚠️ Windows 전용 + 한컴오피스 필수. 한컴 엔진이 직접 처리 → 그림·표 완전 보존.
   rhwp로는 병합 시 충실도 손실 → pyhwpx 사용.

병합 방식: 첫 파일을 열고, 이후 파일들을 문서 끝에 insert_file로 순차 삽입.
  insert_file(keep_section=1) 로 각 파일의 페이지/구역 설정 보존.

사용:
  python hwp_merge_pyhwpx.py <out.hwp> <in1.hwp> <in2.hwp> [in3.hwp ...]
예:
  python hwp_merge_pyhwpx.py 통합.hwp III.hwp IV.hwp

옵션(환경변수):
  HWP_MERGE_PAGEBREAK=1  각 파일 사이에 쪽 나눔 삽입 (기본: 삽입 안 함, insert_file이 구역 유지)
"""

import os
import sys


def main():
    if len(sys.argv) < 4:
        print("usage: python hwp_merge_pyhwpx.py <out> <in1> <in2> [in3 ...]")
        sys.exit(2)

    out_path = sys.argv[1]
    in_files = sys.argv[2:]

    try:
        from pyhwpx import Hwp
    except ImportError:
        print("❌ pyhwpx 미설치. Windows에서: pip install pyhwpx")
        sys.exit(3)

    pagebreak = os.environ.get("HWP_MERGE_PAGEBREAK") == "1"

    try:
        hwp = Hwp(visible=False)
    except TypeError:
        hwp = Hwp()
        try:
            hwp.set_visible(False)
        except Exception:
            pass

    try:
        # 첫 파일 열기
        hwp.open(in_files[0])
        print(f"  [base] {in_files[0]}")

        # 이후 파일들 끝에 삽입
        for f in in_files[1:]:
            hwp.MoveDocEnd()
            if pagebreak:
                try:
                    hwp.BreakPage()
                except Exception:
                    pass
            # keep_* = 원본 서식/구역 보존, move_doc_end=True 로 끝에서 삽입
            hwp.insert_file(
                f,
                keep_section=1, keep_charshape=1,
                keep_parashape=1, keep_style=1,
                move_doc_end=True,
            )
            print(f"  [+merge] {f}")

        hwp.save_as(out_path)
        print(f"✅ 병합 저장: {out_path} ({len(in_files)}개 파일, 그림·표 보존)")
    finally:
        hwp.quit()


if __name__ == "__main__":
    main()
