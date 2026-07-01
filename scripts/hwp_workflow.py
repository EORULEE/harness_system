#!/usr/bin/env python3
"""
hwp_workflow.py — HWP/HWPX 통합 워크플로우 (rhwp 읽기 + pyhwpx 편집)

읽기·검색은 rhwp(Node WASM, 어디서나), 편집은 pyhwpx(한컴 COM, Windows).
edit 명령은 "편집 전 미리보기 → pyhwpx 편집 → 편집 후 rhwp 검증"을 한 번에.

환경 자동 감지:
  - WSL이면 pyhwpx를 Windows Python으로 interop 실행 + 경로 자동 변환(wslpath)
  - 네이티브 Windows면 그대로
  - Linux 서버(한컴 없음)면 edit 불가 → read/search만

사용:
  python3 hwp_workflow.py read   <file>
  python3 hwp_workflow.py search <file> <query> [case]
  python3 hwp_workflow.py edit   <in> <out.hwp|.hwpx> <find> <replace> [case]

환경변수(선택):
  HWP_WIN_PYTHON  Windows Python 경로 강제 지정 (자동탐색 실패 시)
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ────────────────────────── 환경 감지 ──────────────────────────

def is_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def is_windows() -> bool:
    return platform.system() == "Windows"


def find_bridge() -> Path | None:
    """rhwp Node 브리지(hwp_extract.mjs) 탐색."""
    for c in [HERE.parent / "hooks" / "hwp_extract.mjs",
              Path("hooks") / "hwp_extract.mjs",
              HERE / "hwp_extract.mjs"]:
        if c.exists():
            return c
    return None


def find_pyhwpx_script() -> Path | None:
    c = HERE / "hwp_edit_pyhwpx.py"
    return c if c.exists() else None


def find_win_python() -> str | None:
    """편집용 Windows Python 탐색."""
    env = os.environ.get("HWP_WIN_PYTHON")
    if env and Path(env).exists():
        return env
    if is_windows():
        return sys.executable
    if is_wsl():
        # /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe
        cands = sorted(glob.glob(
            "/mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe"
        ), reverse=True)
        if cands:
            return cands[0]
        # py 런처 fallback
        for p in ("py.exe", "python.exe"):
            w = shutil.which(p)
            if w:
                return w
    return None


def to_win_path(p: str) -> str:
    """편집용: WSL 경로 → Windows 경로 변환."""
    if is_wsl():
        try:
            return subprocess.run(["wslpath", "-w", str(Path(p).resolve() if Path(p).exists() else p)],
                                  capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            # 출력 파일은 아직 없을 수 있음 → 절대경로 가정 후 변환
            try:
                return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True).stdout.strip() or p
            except Exception:
                return p
    return p


# ────────────────────────── rhwp 읽기 ──────────────────────────

def rhwp_run(args: list[str]) -> tuple[int, str, str]:
    bridge = find_bridge()
    node = shutil.which("node")
    if not bridge:
        return (3, "", "[hwp_extract.mjs 미발견]")
    if not node:
        return (3, "", "[node 미설치]")
    r = subprocess.run([node, str(bridge), *args], capture_output=True, text=True, timeout=120)
    return (r.returncode, r.stdout, r.stderr)


def rhwp_search_count(file: str, query: str, case: bool = False) -> int:
    code, out, err = rhwp_run(["search", file, query, "true" if case else "false"])
    if code != 0:
        return -1
    try:
        return len(json.loads(out))
    except (json.JSONDecodeError, ValueError):
        return -1


# ────────────────────────── pyhwpx 편집 ──────────────────────────

def pyhwpx_replace(in_file: str, out_file: str, find: str, repl: str) -> tuple[bool, str]:
    script = find_pyhwpx_script()
    if not script:
        return (False, "[hwp_edit_pyhwpx.py 미발견]")
    pyexe = find_win_python()
    if not pyexe:
        return (False, "[Windows Python 미발견 — 한컴 COM 편집 불가. HWP_WIN_PYTHON 지정]")

    # pyhwpx는 Windows 경로 필요
    # ⚠️ WSL 가드 (2026-05-28 검증): 한컴 COM이 WSL-네이티브 경로(/tmp, /home 등)를
    # \\wsl.localhost UNC로 읽으면 .hwp 파일이 손상됨. 입출력은 반드시 Windows FS(/mnt/*).
    if is_wsl():
        for label, pth in (("입력", in_file), ("출력", out_file)):
            rp = str(Path(pth).resolve()) if Path(pth).exists() else os.path.abspath(pth)
            if not rp.startswith("/mnt/"):
                return (False,
                        f"[경로 오류] WSL에서 한컴 편집은 {label} 파일이 Windows 드라이브(/mnt/c, /mnt/d)에 "
                        f"있어야 합니다. 현재: {pth} (WSL-네이티브 경로는 한컴이 읽다 손상). "
                        "파일을 /mnt/d/... 등으로 옮겨 다시 시도하세요.")

    script_arg = to_win_path(str(script)) if is_wsl() else str(script)
    in_arg = to_win_path(in_file) if is_wsl() else in_file
    out_arg = to_win_path(out_file) if is_wsl() else out_file

    r = subprocess.run([pyexe, script_arg, in_arg, out_arg, find, repl],
                       capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    msg = (r.stdout or "").strip() + (("\n" + r.stderr.strip()) if r.stderr.strip() else "")
    return (ok, msg)


# ────────────────────────── 명령 ──────────────────────────

def cmd_read(file: str):
    code, out, err = rhwp_run(["extract", file])
    if code != 0:
        print(f"❌ 읽기 실패: {err}", file=sys.stderr)
        sys.exit(1)
    print(out)


def cmd_search(file: str, query: str, case: bool):
    code, out, err = rhwp_run(["search", file, query, "true" if case else "false"])
    if code != 0:
        print(f"❌ 검색 실패: {err}", file=sys.stderr)
        sys.exit(1)
    try:
        hits = json.loads(out)
        print(f"'{query}' {len(hits)}건")
        for h in hits[:20]:
            print("  ", h)
    except (json.JSONDecodeError, ValueError):
        print(out)


def cmd_edit(in_file: str, out_file: str, find: str, repl: str, case: bool):
    print("━━━ HWP 편집 워크플로우 (rhwp 미리보기 → pyhwpx 편집 → rhwp 검증) ━━━")

    # 1) 편집 전 미리보기 (rhwp)
    before = rhwp_search_count(in_file, find, case)
    if before < 0:
        print(f"⚠️ 미리보기 검색 실패 (rhwp). 입력 파일 확인: {in_file}", file=sys.stderr)
    else:
        print(f"[1/3] 미리보기: '{find}' {before}건 발견")
        if before == 0:
            print(f"      ⚠️ '{find}' 가 없습니다. 편집 중단 (오타·대소문자 확인).")
            sys.exit(1)

    # 2) pyhwpx 편집 (충실도 유지)
    print(f"[2/3] pyhwpx 편집: '{find}' → '{repl}' (그림·표 보존, 숨김 모드)")
    ok, msg = pyhwpx_replace(in_file, out_file, find, repl)
    if msg:
        for line in msg.splitlines():
            print("      " + line)
    if not ok:
        print("❌ pyhwpx 편집 실패", file=sys.stderr)
        sys.exit(1)

    # 3) 편집 후 검증 (rhwp)
    after_old = rhwp_search_count(out_file, find, case)
    after_new = rhwp_search_count(out_file, repl, case)
    print(f"[3/3] 검증: 출력본 '{find}'={after_old}건, '{repl}'={after_new}건")
    if after_old == 0 and after_new >= 1:
        print(f"✅ 성공: '{find}'→'{repl}' 치환 완료, {out_file} (그림·표 보존)")
    elif after_old < 0:
        print(f"⚠️ 검증 불가(rhwp가 출력 못 읽음). 파일은 저장됨: {out_file}")
    else:
        print(f"⚠️ 검증 경고: 기대와 다름 (old={after_old}, new={after_new}). 수동 확인 권장.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    a = sys.argv[2:]

    if cmd == "read" and len(a) >= 1:
        cmd_read(a[0])
    elif cmd == "search" and len(a) >= 2:
        cmd_search(a[0], a[1], len(a) >= 3 and a[2].lower() == "true")
    elif cmd == "edit" and len(a) >= 4:
        case = len(a) >= 5 and a[4].lower() == "true"
        cmd_edit(a[0], a[1], a[2], a[3], case)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
