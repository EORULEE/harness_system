# 설치

## 요구사항
- Python 3.9+ · Node 18+ · Claude Code

## 설치 (프로젝트-로컬)
**A. 새로 써보기** — clone 한 이 폴더에서 바로 `bash selftest.sh` 후 `claude`.
**B. 기존 프로젝트에 연동**(권장, 폴더 안 옮김):
```bash
bash install_into_project.sh /경로/내-기존프로젝트   # 기존 CLAUDE.md/settings 보존·병합, 연구파일 무변경
cd /경로/내-기존프로젝트 && claude
```
**C. 수동**: 이 디렉터리의 `CLAUDE.md · .claude/ · hooks/ · scripts/ · tests/ · _output/` 를 당신 프로젝트 루트에 복사(기존 CLAUDE.md/settings 있으면 덮지 말고 병합).
- (선택) 전역 적용: `.claude/skills/` 를 `~/.claude/skills/` 로 복사하면 모든 프로젝트가 스킬을 상속.
- 검증: 설치한 폴더에서 `bash selftest.sh` (smoke 11/11 확인).

## 구성 (당신 것으로)
- 훅 배선은 `.claude/settings.json` 에 프로젝트-로컬(`$CLAUDE_PROJECT_DIR/hooks/*.mjs`)로 되어 있음.
- LLM/계정 연동(글쓰기·리뷰 등)은 각자의 API 키·CLI 로 구성. 이 패키지엔 어떤 키도 없음.
- c-/x- 적대검증 페어는 프로젝트별로 직접 생성(deep-interview/loop-engineering 스킬 참고).
