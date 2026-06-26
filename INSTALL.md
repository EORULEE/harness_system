# 설치

## 요구사항
- Python 3.9+ · Node 18+ · Claude Code

## 설치 (프로젝트-로컬)
1. 이 디렉터리를 당신 프로젝트 루트에 풀거나 복사 (CLAUDE.md · .claude/ · hooks/ · scripts/ · tests/ 포함).
2. (선택) 전역 적용: `.claude/skills/` 를 `~/.claude/skills/` 로 복사하면 모든 프로젝트가 스킬을 상속.
3. 검증: `bash bootstrap.sh` 또는 SMOKE_SUITE.md 의 smoke 실행.

## 구성 (당신 것으로)
- 훅 배선은 `.claude/settings.json` 에 프로젝트-로컬(`$CLAUDE_PROJECT_DIR/hooks/*.mjs`)로 되어 있음.
- LLM/계정 연동(글쓰기·리뷰 등)은 각자의 API 키·CLI 로 구성. 이 패키지엔 어떤 키도 없음.
- c-/x- 적대검증 페어는 프로젝트별로 직접 생성(deep-interview/loop-engineering 스킬 참고).
