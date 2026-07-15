# 처음 설치 — 전체 설정 가이드 (First Setup)

이 하네스를 받은 직후 **한 번만** 거치면 되는 설정. **개인 계정 없이 작동(로컬 요구사항: python3+PyYAML·node≥18 — SETUP §0)**하고, 아래 선택 통합은 본인 계정/폴더로 추가합니다(없으면 Claude로 대체되거나 생략).

> Claude Code 첫 세션을 열면 이 순서를 **자동으로 안내·질문**합니다(온보딩). 직접 보려면 이 문서.

## 0. 요구사항 — 기존 환경을 바꾸지 마세요 (격리 env 권장)
- **Claude Code**(호스트) · **python3 ≥3.9 + PyYAML** · **node ≥18**
- 외부 pip 의존은 **PyYAML 하나뿐**(나머지는 전부 표준 라이브러리). 시스템 python/node 를 *업그레이드·교체하지 말고* 격리 환경을 쓰세요 — 당신이 이미 쓰던 conda·프로젝트 환경이 망가지지 않습니다.

> **"격리 env" 가 뭔가요?** = 이 하네스 전용 python 공간(방)을 따로 하나 만드는 것. *PyYAML 설치 ≠ 격리 env* — **① 방을 만들고 ② 그 방에 PyYAML 을 넣는** 2단계입니다(아래 한 줄이 둘을 합침). `conda`·`venv` 가 그 방을 만드는 도구이고, **docker 와 개념은 같지만 훨씬 가볍습니다**(docker=OS 통째 격리/과함, conda·venv=python 만 격리/권장). 이미 python ≥3.9 인 conda env 가 있으면 새로 안 만들고 거기에 `conda install pyyaml` 만 해도 됩니다.

**옵션 A — conda (이미 쓰고 있다면 권장)**
```bash
conda create -n harness python=3.12 pyyaml -y
export PYTHON="$(conda run -n harness which python)"   # 훅이 이 python 을 쓰도록 고정
```
**옵션 B — venv (conda 없을 때)**
```bash
python3 -m venv ~/.harness-venv && ~/.harness-venv/bin/pip install pyyaml
export PYTHON="$HOME/.harness-venv/bin/python3"
```
**node — 시스템 교체 말고 nvm**
```bash
nvm install 18          # 또는 그 이상. 시스템 node 는 그대로 둠.
```
> 훅은 `PYTHON` 환경변수를 1순위로 따릅니다(없으면 시스템 python3). `export PYTHON=...` 를 셸 프로필(`~/.bashrc` 등)에 넣어두면 매번 적용됩니다. node 는 nvm 으로 격리하면 시스템에 무영향.
> 빠른 확인: `bash selftest.sh` 의 `[A]` 가 python·PyYAML·node 를 각각 ✓/⚠ 로 알려줍니다.

## 1. 받기 & 설치 확인 (필수)
```bash
git clone harness-public-core-v1.bundle harness
cd harness
bash selftest.sh        # 요구사항·코어 smoke(22)·스킬(49)·훅·도구·계정/MCP 상태 한 번에
```

## 2. 코어 — 설정 0으로 바로 작동
응답규율(`CLAUDE.md`) · dev-discipline(systematic-debugging·verification·**code-claim 게이트**·TDD) · loop · deep-interview · ralph · system-truth-probe · adaptive-verification · **verification-gate v1.1**(`docs/VGATE.md` — 근거 없는 '불가/원인/없다' 단정 검사, 기본=report 관찰모드·차단은 mode.txt 로 opt-in). **추가 설정 불필요.**

## 3. 선택 통합 — 본인 것으로 설정 (한 번)
### 3a. LLM Wiki — `WIKI.md`
```bash
export WIKI_ROOT=~/notes/wiki && mkdir -p "$WIKI_ROOT"   # 본인 노트 폴더
# 결정적 도구(lint/health/graph)는 계정 0으로 작동. ingest/query 는 Claude 가 수행.
```
### 3b. Gemini (글쓰기 백엔드) — `ACCOUNTS.md §2`
Google AI Studio 키 → `~/.claude/gemini.env` 에 `GEMINI_API_KEY=...` (없으면 글쓰기는 Claude로 작성).
### 3c. Codex + ChatGPT (코드 적대검토) — `ACCOUNTS.md §3`
Codex Claude Code 플러그인 설치 + ChatGPT 인증 (없으면 Claude 리뷰로 대체).
### 3d. 연구·코드 MCP — `ACCOUNTS.md §4`
**본인 계정/키로** `semantic-scholar`·`paper-search`·`github`·`serena` 추가(일부 키 필요; 생략 가능).
```bash
bash scripts/setup_mcp.sh      # 본인 키로 자동 등록(이미 있으면 skip). 키는 저장 안 함.
claude mcp list                # 각 서버 '✔ Connected' 확인
```

## 4. 마무리
```bash
touch .claude/.onboarded     # 설정/결정 끝나면 → 시작 안내 종료
```

## 작동 / 미작동 한눈에
| 기능 | 필요한 것 | 설정 안 하면 |
|---|---|---|
| 규율·dev-discipline·loop·deep-interview·ralph·adaptive | — | ✅ 그대로 작동 |
| LLM Wiki — lint·health·graph | `WIKI_ROOT`(폴더만) | ✅ 작동 |
| LLM Wiki — ingest·query | Claude | ✅ 작동(에이전트) |
| 글쓰기 — Gemini 백엔드 | Gemini 키 | Claude로 작성(대체) |
| 코드 적대검토 | Codex+ChatGPT | Claude 리뷰(대체) |
| 논문/코드 조사 | MCP 서버 | 생략 |

**요약**: clone → `bash selftest.sh` → (원하는 통합만 3 에서 설정) → `touch .claude/.onboarded`. 코어는 즉시, 나머지는 본인 계정으로.

## 기존 연구 프로젝트에 연동하기 (폴더 안 옮김)
이미 작업 중인 프로젝트가 있으면, **그 폴더를 옮기지 말고** 하네스를 그 폴더에 얹습니다. 연구 데이터는 그대로:
```bash
bash install_into_project.sh /경로/내-연구프로젝트
# 그다음:  cd /경로/내-연구프로젝트  &&  claude
```
이 스크립트가 하는 일:
- hooks·scripts·tests·.claude/skills·_output(콜렉터) 를 그 폴더에 **추가**(기존 파일 보존, add-only)
- 그 폴더에 **이미 `CLAUDE.md` 가 있으면**: 당신 내용은 **그대로 두고**, 하네스 규율은 `CLAUDE.harness.md` 에 넣은 뒤 당신 `CLAUDE.md` 끝에 **`@CLAUDE.harness.md` import 한 줄만 추가** → **당신 규율 + 하네스 규율이 둘 다 활성**(텍스트 중복 없음). 그 줄만 지우면 하네스 규율 비활성. (없으면 그냥 `CLAUDE.md` 로 복사)
- **`settings.json` 은 훅을 병합**(기존 훅 보존 + 하네스 훅 추가, 동일 항목은 중복 안 함, 기존은 `.bak` 백업)
- 끝나면 그 폴더에서 `selftest.sh` 자동 실행해 검증(smoke 22 자동실행)
- 되돌리기: 추가된 위 폴더들 + `settings.json`(.bak 복원) + CLAUDE.md 의 import 두 줄만 제거. **연구 파일은 처음부터 안 건드림.**

## 자주 묻는 것 / 문제 해결

**Q. 이미 글로벌 Claude 설정(`~/.claude/CLAUDE.md`·settings·hooks·skills)이 있어요. 충돌하나요?**
아니요 — 이 하네스는 **clone 폴더 안의 `.claude/`(프로젝트 로컬)** 로만 동작합니다. 훅 경로가 전부 `$CLAUDE_PROJECT_DIR/hooks/...` 라서 당신의 **글로벌 `~/.claude/` 를 덮어쓰지 않습니다.**
- Claude Code 는 글로벌 + 프로젝트 설정을 **합쳐서**(가산) 적용합니다 — 이 폴더에서 작업할 때만 이 하네스의 규율/훅이 *추가로* 켜집니다(당신 글로벌 규칙은 그대로 유지).
- 런타임 메모리는 `~/.claude/projects/<이 폴더 해시>/` 에만 기록 — **프로젝트별로 분리**되어 당신의 다른 프로젝트·글로벌 CLAUDE.md 에 영향이 없습니다.
- 만약 당신 글로벌 훅과 동작이 겹쳐 시끄러우면, 이 프로젝트 `.claude/settings.json` 에서 해당 훅 줄만 빼면 됩니다(프로젝트 한정).

**Q. `bash selftest.sh` 의 smoke 가 실패하면?**
거의 항상 **환경 문제이지 당신 글로벌 설정 탓이 아닙니다**(smoke 는 임시폴더에서 자기완결로 돌고 글로벌 `~/.claude` 를 읽지 않음). 순서대로 확인:
1. **`[A]` 부터** — `python3 ≥3.9` · `PyYAML` · `node ≥18` 가 ✓ 인지. ⚠ 면 §0 의 격리 env(conda/venv/nvm)로 먼저 맞추세요(시스템 변경 금지).
2. 그래도 특정 smoke 만 ✗ 면 그 이름으로 직접 실행해 메시지 확인: `bash tests/smoke_<이름>.sh`
3. `node` 가 없거나 <18 이면 **훅만 비활성**이고 코어 로직 smoke 는 동작합니다([D]/[B] 로 구분).

**Q. 마음에 안 들면 어떻게 지우나요?**
글로벌을 안 건드리므로 **clone 폴더만 삭제**하면 끝입니다(원하면 `~/.claude/projects/<이 폴더 해시>/` 도 정리). 시스템 python/node 는 애초에 안 바꿨으니 되돌릴 것이 없습니다.
