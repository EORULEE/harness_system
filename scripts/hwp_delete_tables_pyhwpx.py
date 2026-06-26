#!/usr/bin/env python3
"""
hwp_delete_tables_pyhwpx.py — 특정 마커 텍스트를 포함한 표(가이드박스)를 삭제

⚠️ Windows 전용 + 한컴오피스. 위험 작업이므로 안전장치 내장:
   - 선택된 컨트롤(표)의 텍스트에 marker가 있을 때만 DeleteCtrl
   - marker 없으면 즉시 중단 (실제 내용 표 보호)
   - 항상 새 출력 파일로 저장 (원본 보존)

용도: 제안서 템플릿의 "작성 요령 ... 삭제할 것" 가이드박스 일괄 제거 등.

사용:
  python hwp_delete_tables_pyhwpx.py <in> <out> <marker> [max_count]
예:
  python hwp_delete_tables_pyhwpx.py 통합.hwp 정리.hwp "작성 완료 후 요령은 삭제할 것" 15
"""

import sys


def main():
    if len(sys.argv) < 4:
        print("usage: python hwp_delete_tables_pyhwpx.py <in> <out> <marker> [max_count]")
        sys.exit(2)
    in_path, out_path, marker = sys.argv[1:4]
    max_count = int(sys.argv[4]) if len(sys.argv) >= 5 else 30

    try:
        from pyhwpx import Hwp
    except ImportError:
        print("❌ pyhwpx 미설치. Windows에서: pip install pyhwpx")
        sys.exit(3)

    try:
        hwp = Hwp(visible=False)
    except TypeError:
        hwp = Hwp()
        try:
            hwp.set_visible(False)
        except Exception:
            pass

    deleted = 0
    skipped = 0
    try:
        hwp.open(in_path)
        for i in range(max_count):
            hwp.MoveDocBegin()
            # marker는 가이드박스에만 존재 → find 성공 시 커서가 그 표 셀 안에 위치
            if not hwp.find(marker, direction="Forward"):
                break  # 더 이상 없음
            # 커서가 든 표(컨트롤) = 가이드박스 → ParentCtrl로 획득
            ctrl = hwp.ParentCtrl
            if ctrl is None:
                print(f"⚠️ ParentCtrl 없음 (deleted={deleted}) — 중단")
                break
            # 안전 확인: 컨트롤 종류가 표인지 (가능하면)
            try:
                cid = ctrl.CtrlID
            except Exception:
                cid = "?"
            # 커서를 표 밖으로 빼서 삭제 (표 안에서 DeleteCtrl 실패 방지)
            try:
                hwp.MoveDocBegin()
            except Exception:
                pass
            ok = hwp.DeleteCtrl(ctrl)
            if ok:
                deleted += 1
            else:
                skipped += 1
                print(f"⚠️ DeleteCtrl 실패 (ctrlID={cid}, deleted={deleted}) — 중단")
                break

        hwp.save_as(out_path)
        print(f"✅ 저장: {out_path} (삭제 {deleted}개, 스킵 {skipped})")
    finally:
        hwp.quit()


if __name__ == "__main__":
    main()
