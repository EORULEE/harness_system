#!/usr/bin/env python3
"""
hwp_edit_pyhwpx.py — 한컴오피스 COM 자동화로 .hwp 충실도 유지 편집

⚠️ Windows 전용 + 한컴오피스(아래아한글) 설치 필수.
   Linux 서버(gars*)에서는 실행 불가 — 사용자 본인 Windows PC에서 실행.

rhwp(Node 브리지)는 읽기 전용으로만 신뢰. 그림·표가 있는 실제 문서를
편집하려면 본 스크립트(pyhwpx)를 Windows에서 사용 — 한컴 엔진이 직접
처리하므로 그림·중첩표·표 크기가 완전 보존됨.

설치:
  pip install pyhwpx        # pywin32, pandas 등 자동 설치

사용:
  python hwp_edit_pyhwpx.py <in.hwp> <out.hwp> <찾을텍스트> <바꿀텍스트>

예:
  python hwp_edit_pyhwpx.py test.hwp test_fixed.hwp "Abnoramal" "Abnormal"

주의:
  - find/replace 는 hwp.find_replace_all(find, replace) 사용 (검증됨 2026-05-28).
    반환값은 개수가 아닌 bool 계열 — 실제 반영 여부는 검색으로 재확인 권장.
  - 한컴 창은 visible=False 로 숨겨 실행 (사용자 실수 클릭 위험 제거).
    단 편집 중 한컴을 직접 켜거나 조작하면 충돌 가능 — 피할 것. 다른 앱은 무관.
  - 보안 모듈 자동 등록(FilePathCheckerModule). 첫 실행 시 승인 필요할 수 있음.
"""

import sys


def main():
    if len(sys.argv) != 5:
        print("usage: python hwp_edit_pyhwpx.py <in.hwp> <out.hwp> <find> <replace>")
        sys.exit(2)

    in_path, out_path, find_text, replace_text = sys.argv[1:5]

    try:
        from pyhwpx import Hwp
    except ImportError:
        print("❌ pyhwpx 미설치. Windows에서: pip install pyhwpx")
        print("   (Linux 서버에서는 실행 불가 — 한컴오피스 COM 필요)")
        sys.exit(3)

    # visible=False: 한컴 창을 화면에 띄우지 않음 → 사용자 실수 클릭 위험 제거.
    # (단 같은 한컴 인스턴스를 사용자가 따로 켜고/끄면 여전히 충돌 가능 — 편집 중
    #  한컴 직접 조작은 피할 것. 다른 앱 사용은 무관.)
    try:
        hwp = Hwp(visible=False)
    except TypeError:
        # 구버전 pyhwpx 는 visible 키워드 미지원 → 생성 후 속성으로 숨김 시도
        hwp = Hwp()
        try:
            hwp.set_visible(False)
        except Exception:
            pass
    try:
        hwp.open(in_path)

        # 전체 찾아바꾸기 — 한컴 엔진이 그림/표 보존하며 처리
        # find_replace_all 은 개수가 아닌 성공여부(bool) 반환에 가까움.
        count = None
        if hasattr(hwp, "find_replace_all"):
            count = hwp.find_replace_all(find_text, replace_text)
        else:
            # fallback: HAction AllReplace
            hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
            hwp.HParameterSet.HFindReplace.FindString = find_text
            hwp.HParameterSet.HFindReplace.ReplaceString = replace_text
            hwp.HParameterSet.HFindReplace.ReplaceMode = 1
            hwp.HParameterSet.HFindReplace.IgnoreMessage = 1
            hwp.HAction.Execute("AllReplace", hwp.HParameterSet.HFindReplace.HSet)

        hwp.save_as(out_path)
        status = "성공" if count else "결과 미확인(검색으로 확인 권장)"
        print(f"✅ 저장: {out_path} (find_replace_all={count} {status}, 그림·표 보존)")
    finally:
        hwp.quit()


if __name__ == "__main__":
    main()
