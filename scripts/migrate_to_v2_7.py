#!/usr/bin/env python3
"""migrate_to_v2_7.py — 옛 하네스 → v2.7.3 마이그레이션

전략 (5단계):
  1. 작업 결과 백업 — `.claude/_migrate_bak.<timestamp>/` 안전 보존
  2. 옛 하네스 코드·에이전트·skills 삭제
  3. 새 v2.7.3 install.sh 실행 (의존성 자동, hooks·agents 디렉토리 새로)
  4. 작업 결과 복원 — 백업의 memory/instincts/references/campaigns/discoveries/debate/runtime 을
     새 .claude/ 로 복귀
  5. (옵션) campaign.yaml 의 domains 자동 인식 → bootstrap 재실행으로 agents/ 만 frontmatter 갱신

사용:
  python migrate_to_v2_7.py /path/to/old-project [옵션]

옵션:
  --bootstrap            마이그레이션 후 bootstrap 자동 (agents/ 새 frontmatter)
  --skip-install         install.sh 안 돌림 (이미 install 됐을 때)
  --dry-run              실제 변경 없이 시뮬만
  --keep-old-agents      옛 agents/ 보존 (frontmatter 없는 것도)
  --source <path>        하네스 v2.7 소스 경로 (default: 이 스크립트 부모)
"""

from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# 보존·폐기 분류 (CRITICAL — 사용자 작업 결과 vs 옛 하네스 코드 분리)
# ═══════════════════════════════════════════════════════════════

# 보존: 이전 작업 결과 (사용자가 시간 들여 만든 것)
PRESERVE = [
    # 하네스 v2 메모리
    ".claude/memory",
    ".claude/instincts",
    ".claude/references",
    ".claude/campaigns",
    ".claude/discoveries",
    ".claude/debate",
    ".claude/runtime",
    ".claude/embeddings",
    ".claude/file-history",
    # 동적 도메인 등록 + 도메인 스캔 캐시
    ".claude/domain_cache.json",
    # 사용자 본인 commands (있다면)
    ".claude/commands",
]

# 폐기: 옛 하네스 코드 (새 v2.7.3 으로 교체)
PURGE_PROJECT_ROOT = [
    "scripts",
    "hooks",
    "tests",
    "prompts",
    "skills",
    "examples",
    "codex-prompts",
    "docs",
    "CLAUDE.md",
]

# 폐기: 옛 .claude 의 하네스 자산 (새로 생성됨)
PURGE_CLAUDE = [
    ".claude/agents",        # frontmatter 없는 옛 .md
    ".claude/skills",        # 옛 SKILL.md (새 install 이 다시 배포)
    ".claude/settings.json", # 옛 hook 설정
]


# ═══════════════════════════════════════════════════════════════
# 핵심 로직
# ═══════════════════════════════════════════════════════════════

def backup(target: Path, timestamp: str, dry: bool) -> Path:
    """1단계: 보존 대상을 .claude/_migrate_bak.<ts>/ 로 백업."""
    bak = target / ".claude" / f"_migrate_bak.{timestamp}"
    print(f"\n▶ [1/5] 백업 — {bak.relative_to(target)}/")
    if dry:
        print("  (dry-run — 실제 백업 생략)")
        return bak

    bak.mkdir(parents=True, exist_ok=True)
    moved = []
    for rel in PRESERVE:
        src = target / rel
        if not src.exists():
            continue
        dst = bak / rel.replace(".claude/", "")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        moved.append(rel)
    print(f"  ✅ 보존 항목 {len(moved)}개 백업:")
    for m in moved:
        print(f"     {m}")
    return bak


def purge_old(target: Path, keep_old_agents: bool, dry: bool) -> int:
    """2단계: 옛 하네스 코드 폐기."""
    print(f"\n▶ [2/5] 옛 하네스 폐기")
    purged = 0
    paths = list(PURGE_PROJECT_ROOT) + list(PURGE_CLAUDE)
    if keep_old_agents:
        paths = [p for p in paths if p != ".claude/agents"]
    for rel in paths:
        p = target / rel
        if not p.exists():
            continue
        if dry:
            print(f"  (dry-run) 폐기 예정: {rel}")
        else:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            print(f"  🗑  {rel}")
        purged += 1
    print(f"  → {purged} 항목 폐기")
    return purged


def install_v27(target: Path, source: Path, dry: bool) -> bool:
    """3단계: 새 v2.7.3 install.sh 실행."""
    print(f"\n▶ [3/5] 새 v2.7.3 install — source={source.name}")
    install_sh = source / "install.sh"
    if not install_sh.exists():
        print(f"  ❌ install.sh 없음: {install_sh}")
        return False
    if dry:
        print(f"  (dry-run) bash {install_sh} {target}")
        return True

    # bash 실행
    cmd = ["bash", str(install_sh), str(target)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  ✅ install 성공")
            # 마지막 5줄 출력
            for line in (result.stdout.splitlines() + result.stderr.splitlines())[-5:]:
                print(f"     {line}")
            return True
        else:
            print(f"  ❌ install 실패 (exit {result.returncode})")
            print(result.stderr[-500:])
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ install timeout (300s)")
        return False


def restore(target: Path, bak: Path, dry: bool) -> int:
    """4단계: 백업한 작업 결과를 새 .claude/ 로 복원."""
    print(f"\n▶ [4/5] 작업 결과 복원 — {bak.relative_to(target)}/ → .claude/")
    if dry:
        print("  (dry-run — 실제 복원 생략)")
        return 0
    if not bak.exists():
        print(f"  ⚠️  백업 없음 — skip")
        return 0

    restored = 0
    for item in bak.iterdir():
        # _migrate_bak 안의 각 디렉토리/파일 → .claude/<name>
        target_path = target / ".claude" / item.name
        if item.is_dir():
            if target_path.exists():
                # 새 install 이 만든 빈 디렉토리는 백업으로 덮어쓰기
                shutil.rmtree(target_path)
            shutil.copytree(item, target_path)
        else:
            shutil.copy2(item, target_path)
        restored += 1
        print(f"  ↩  {item.name}")
    print(f"  → {restored} 항목 복원")
    return restored


def maybe_bootstrap(target: Path, source: Path, do_bootstrap: bool, dry: bool) -> bool:
    """5단계 (옵션): bootstrap 으로 agents/ 새 frontmatter 생성."""
    print(f"\n▶ [5/5] Bootstrap — agents/ frontmatter 갱신")
    if not do_bootstrap:
        print("  (--bootstrap 미지정 — 스킵)")
        print(f"  수동 권장: cd {target} && python scripts/campaign_manager.py bootstrap "
              f'"<프로젝트명>" --auto-detect --overwrite')
        return False

    # 기존 캠페인의 domains 필드 자동 인식
    campaigns_dir = target / ".claude" / "campaigns"
    if not campaigns_dir.exists():
        print("  ⚠️  campaigns/ 없음 — bootstrap 스킵 (domains 정보 없음)")
        return False

    domains: list[str] = []
    for camp_yaml in campaigns_dir.glob("*/campaign.yaml"):
        try:
            text = camp_yaml.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip().startswith("- ") and not line.strip().startswith("- name:"):
                    d = line.strip().lstrip("- ").strip().strip('"').strip("'")
                    if d and d not in domains:
                        domains.append(d)
                if line.strip().startswith("domains:"):
                    rest = line.split(":", 1)[1].strip()
                    if rest.startswith("[") and rest.endswith("]"):
                        for d in rest.strip("[]").split(","):
                            d = d.strip().strip('"').strip("'")
                            if d and d not in domains:
                                domains.append(d)
        except OSError:
            continue

    if not domains:
        print("  ⚠️  campaign.yaml 에서 domains 추출 실패 — bootstrap 스킵")
        return False

    domain_str = ",".join(domains)
    proj_name = target.name
    print(f"  도메인 추출: {domain_str}")
    if dry:
        print(f"  (dry-run) python scripts/campaign_manager.py bootstrap "
              f'"{proj_name}" --domains {domain_str} --overwrite')
        return True

    cmd = [
        sys.executable, str(target / "scripts" / "campaign_manager.py"),
        "bootstrap", proj_name,
        "--domains", domain_str, "--overwrite",
    ]
    result = subprocess.run(cmd, cwd=target, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        print(f"  ✅ bootstrap 완료 — agents/ 새 frontmatter 18+개 생성")
        return True
    else:
        print(f"  ❌ bootstrap 실패: {result.stderr[-300:]}")
        return False


# ═══════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="대상 프로젝트 폴더")
    ap.add_argument("--source", default=None,
                    help="하네스 v2.7 소스 (default: 이 스크립트의 부모/..)")
    ap.add_argument("--bootstrap", action="store_true",
                    help="마이그레이션 후 bootstrap 자동 (agents 새 frontmatter)")
    ap.add_argument("--skip-install", action="store_true",
                    help="install.sh 안 돌림")
    ap.add_argument("--keep-old-agents", action="store_true",
                    help="옛 agents/ 보존 (frontmatter 없는 .md 들도)")
    ap.add_argument("--dry-run", action="store_true",
                    help="실제 변경 없이 시뮬")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"❌ 대상 폴더 없음: {target}")
        sys.exit(1)

    source = Path(args.source).resolve() if args.source else \
             Path(__file__).resolve().parent.parent
    if not (source / "install.sh").exists():
        print(f"❌ source/install.sh 없음: {source}")
        sys.exit(1)

    print("═" * 70)
    print("🚀 하네스 마이그레이션 — 옛 → v2.7.3")
    print("═" * 70)
    print(f"  대상: {target}")
    print(f"  소스: {source}")
    print(f"  옵션: bootstrap={args.bootstrap}, skip_install={args.skip_install}, "
          f"keep_old_agents={args.keep_old_agents}, dry={args.dry_run}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = backup(target, timestamp, args.dry_run)
    purge_old(target, args.keep_old_agents, args.dry_run)

    if not args.skip_install:
        if not install_v27(target, source, args.dry_run):
            print("\n❌ install 실패 — 수동 복원 필요. 백업 위치:")
            print(f"   {bak}")
            sys.exit(2)
    else:
        print("\n▶ [3/5] install 스킵 (--skip-install)")

    restore(target, bak, args.dry_run)
    maybe_bootstrap(target, source, args.bootstrap, args.dry_run)

    print()
    print("═" * 70)
    print("✅ 마이그레이션 완료")
    print("═" * 70)
    print(f"  백업: {bak}")
    print(f"  → 문제 시 복원:")
    print(f"     cp -r {bak}/* {target}/.claude/")
    print()
    print(f"  📋 다음 단계:")
    print(f"     1. cd {target}")
    print(f"     2. claude code  (재시작 — frontmatter 등록)")
    print(f"     3. /agents       (페어 등록 확인)")
    if not args.bootstrap:
        print(f"     4. (수동) python scripts/campaign_manager.py bootstrap "
              f'"<프로젝트명>" --auto-detect --overwrite')


if __name__ == "__main__":
    main()
