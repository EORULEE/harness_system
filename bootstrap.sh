#!/usr/bin/env bash
# bootstrap.sh — Linux/Mac 1줄 부트스트랩
#
# 사용:
#   unzip claude-harness-2026-05-08.zip -d ~/
#   bash ~/files_origin/bootstrap.sh

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "===================================================="
echo "  Claude Harness Bootstrap (Linux/Mac)"
echo "  Source: $SCRIPT_DIR"
echo "===================================================="
echo ""

echo "[1/3] 환경 셋업..."
bash "$SCRIPT_DIR/harness-v2.7/setup_wsl.sh"

echo ""
echo "[2/3] Global memory 복원..."
bash "$SCRIPT_DIR/global_memory/restore.sh"

echo ""
echo "[3/3] 글로벌 CLAUDE.md 복사..."
mkdir -p ~/.claude
cp "$SCRIPT_DIR/user-config/global-CLAUDE.md" ~/.claude/CLAUDE.md
echo "  ✅ ~/.claude/CLAUDE.md 복사 완료"

echo ""
echo "===================================================="
echo "✅ 부트스트랩 완료"
echo "===================================================="
echo ""
echo "다음 단계:"
echo "  source ~/.bashrc"
echo "  claude /login"
echo "  claude-team"
echo ""
echo "프로젝트별 셋업:"
echo "  bash $SCRIPT_DIR/harness-v2.7/setup_full.sh \"\$(pwd)\""
