# Claude Code Harness — Public Core

개인정보 없는 보편 코어. 응답 규율(CLAUDE.md) + dev-discipline(systematic-debugging·verification·code-claim evidence gate·TDD) + loop engineering · deep-interview · adaptive verification 스킬 + 검증 smoke.

## 처음 설치 — **`SETUP.md` 먼저** (전체 설정 안내)
```bash
# GitHub 에서
git clone https://github.com/EORULEE/harness_system.git harness && cd harness
# 또는 배포된 번들 파일에서
#   git clone harness-public-core-v2.bundle harness && cd harness
bash selftest.sh      # 요구사항·smoke(22)·스킬(49)·훅·도구·계정/MCP 상태 한 번에
```
Claude Code 첫 세션을 열면 온보딩이 **SETUP.md 기준 전체 설정(코어·Wiki·계정·MCP)을 안내·질문**합니다.

## 이미 쓰던 프로젝트(연구 폴더 등)에 붙이기 — 딱 2줄
```bash
bash install_into_project.sh /경로/내-기존프로젝트   # 하네스를 그 폴더에 얹음 (add-only)
cd /경로/내-기존프로젝트 && claude                   # 끝. 나머지는 Claude 가 대화로 안내
```
- 연구 데이터는 **안 건드림**(add-only; 기존 CLAUDE.md 끝에 import 1줄 추가·settings 병합, 각 .bak 백업). 기존 `CLAUDE.md`/`settings.json` 은 보존·병합(`.bak` 백업).
- 끝나면 그 폴더에서 selftest 자동 실행으로 검증. 되돌리기 절차는 `SETUP.md` 연동 섹션.

### 폴더 구조 (한눈에)
- `CLAUDE.md` 규율 · `.claude/` (settings·skills·hookify 규칙) · `hooks/` · `scripts/` · `tests/` (smoke)
- `fleet-dashboard/` — **콜렉터 코드**(fleet_summary·ledger_evidence). 지우지 말 것.
- `_output/` — **런타임 출력**(loop ledger `_output/loops·contracts·ralph`, release 마커). 실행 중 생성됨.

- 📖 **쉬운 사용설명서(HTML): [`docs/guide/index.html`](docs/guide/index.html)** — 30초 시작·"그냥 이렇게 말하세요"·시나리오·FAQ (+ [요청 치트시트](docs/guide/cheatsheet.html))
- **처음 설치 전체: `SETUP.md`** · 규율: `CLAUDE.md` · 검증: `SMOKE_SUITE.md` · 계정: `ACCOUNTS.md` · LLM 위키: `WIKI.md` · 설치 상세: `INSTALL.md`
- **포함**: 49 스킬(dev-discipline·code-claim 게이트·loop·deep-interview·ralph·writing·adaptive·**LLM Wiki** 등) + 20 훅 + 22 smoke + **verification-gate v1.1**(근거 없는 단정 차단 — `docs/VGATE.md`, 기본 report 모드). 코어는 계정 0으로 작동.
- **미포함**(개인정보 보호): KB(reference manager·notes app)·Drive·Fleet·일부 글쓰기 스킬 + MCP 서버 — 설치자가 자기 계정/것으로 구성.
