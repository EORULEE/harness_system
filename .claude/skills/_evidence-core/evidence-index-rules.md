# Evidence Index 규율 (v1, 2026-06-16)

> 목적: 시스템 동작 설명 전에 **빠르게 근거를 찾고, 필요할 때만 실제 파일을 읽는다.** [[feedback-source-verify-before-claim]]의 verify-or-abstain를 속도와 양립시키는 구조. advisory(최종권위 stop-guard/hookify).

## 6대 규칙 (사용자 명시)
1. **index = source of truth 아님, pointer/cache다.** 답의 권위는 항상 실제 파일.
2. **파일 hash가 바뀌면 stale 표시.** probe가 `files_hash[path].sha256` vs 현재 파일 비교 → 불일치=stale.
3. **위험 claim은 index만으로 확정 X → 실제 source file을 읽는다.** (risk: must_read, 또는 stale, 또는 내용/동작/정확값 질문)
4. **secret 원문을 index에 저장하지 않는다.** indexer가 최종 redaction 패스(AIza/sk-/ghp_/xox 패턴 제거).
5. **env/secret 경로는 presence만 기록**(stat: 존재·mtime). **내용 읽지 않음·hash 안 함**(collector: presence_only).
6. **raw output은 `.claude/runtime/`에 저장**(index.json·.sha256·.log).

## index_ok vs must_read (claim 분류)
| index로 답 OK (신선도 검증된 경우) | 반드시 파일 read |
|---|---|
| 스킬 **존재/위치/개수** | 스킬 **본문 동작·로직** |
| frontmatter **dmi·allowed-tools** | 함수 **로직·정확 컬럼·필드값** |
| hookify **action(block/warn)** | hookify **패턴/조건 본문** |
| settings **skillOverrides 키·model** | 코드 **분기·계산·정규식 매치** |
| 훅/cycle/lottie **파일 존재** | stop-guard **차단 조건** |
| router **alias 목록** | 현재 **md5/줄수/정확 텍스트** |

> ⚠️ **애매하면 read.** index는 "어디를 읽을지"를 빠르게 알려주는 용도. "build_table 컬럼이 뭐?"(이전 실패) 같은 정확값은 **anchor로 위치만 얻고 그 줄을 read**.

## probe 사용 흐름 (`scripts/system_truth_probe.py`)
1. `probe.py <domain>` → 해당 도메인 index 항목 + **신선도(fresh/STALE)** + risk + "must_read?" 표시.
2. fresh + index_ok + 질문이 존재/메타 → index로 즉답(evidence=index, 단 "index 기준" 명시).
3. STALE 또는 must_read 또는 내용질문 → **pointed 파일을 Read**(+anchor line) → evidence=그 파일(:line).
4. `probe.py --stale` → 전 도메인 신선도 감사(변경된 파일 목록).

## ast-grep 구조 anchor (must_read 코드 도메인 옵션, 2026-06-16)
must_read 코드 도메인(`stop_guard`·`scripts`·hooks)에서 "process.exit/sys.exit/함수정의" 같은 **구조적** claim은 — rg(텍스트)는 주석·문자열을 오탐하므로 — **ast-grep로 실제 AST 노드만** 정밀 추출 후 그 줄을 read:
- `ast-grep scan -c .claude/skills/_evidence-core/astgrep/sgconfig.yml hooks scripts`
- 일회성: `ast-grep -p 'process.exit($C)' -l js hooks/` · `ast-grep -p 'sys.exit($C)' -l py scripts/`
- **입증**(smoke): 주석+문자열+호출 3개 중 ast-grep=1(호출만)·rg=3(전부) → ast-grep이 구조 정확.
- ⚠️ **옵션·보완**: ast-grep 미설치면 rg+파일 read로 그대로 동작(필수 의존 아님). **Markdown·f-string 내용은 ast-grep 미지원 → rg 유지.** 정확값/로직은 anchor 후 **여전히 파일 read**(index/anchor는 위치만).

## 자동 갱신 (2026-06-16)
- **기본(무수정·권장): probe 조회 전 자동 갱신** — `system_truth_probe.py`가 매 조회 전 `indexer --if-stale`(mtime 게이트, fresh면 ~0.6s 생략, 변경 시만 재인덱싱) 자동 실행. **hook/settings 무수정**. `--no-refresh`로 끔.
- **`indexer --if-stale`**: index 없음/source-map 변경/추적파일 mtime 변경/스킬 수 변경 시만 재빌드, 아니면 생략. cron·세션시작·수동 어디서나 가벼움.
- **SessionStart 배선 = ✅ 적용됨(2026-06-16, 사용자 승인)**: `settings.local.json` `hooks.SessionStart`에 병렬 명령 추가됨 — `python3 "$CLAUDE_PROJECT_DIR/scripts/system_truth_indexer.py" --if-stale >/dev/null 2>&1 || true`(출력 억제·무중단). 기존 session-start.mjs는 무변경. 즉 **세션 시작 시 1회 + probe 조회마다** 자동 갱신. rollback=settings에서 그 명령 줄 제거.

## 범용 채택 (다른 프로젝트, 2026-06-16 템플릿화)
Evidence Index는 **ROOT-portable**(indexer/probe가 parent-of-scripts/ 기준) → 다른 하네스 프로젝트도 사용 가능:
1. `scripts/system_truth_{indexer,probe}.py` 복사.
2. `system-source-map.template.yaml` → `.claude/skills/_evidence-core/system-source-map.yaml`로 복사 후 harness 라벨·프로젝트-특화 도메인(OPTIONAL anchors) 수정.
3. `python3 scripts/system_truth_indexer.py` 1회 → `.claude/runtime/system_truth_index.json` 생성. 이후 probe가 `--if-stale` 자동 갱신.
- **검증됨**: 템플릿+스크립트를 임시 프로젝트 ROOT서 실행 → 7도메인·probe 동작(포터블 입증). source-map은 **프로젝트 구조에 맞게** 각자 작성(<project> 전용 anchor=research_report/multi_research/writing-router/lottie는 OPTIONAL).

## 경계
advisory. index는 보조 — 최종 답은 항상 실제 파일이 권위. indexer/probe는 읽기중심(대상 쓰기 0, 산출은 `.claude/runtime/`만). 외부도구·MCP 없음. 관련 [[feedback-source-verify-before-claim]]·글로벌 §1 probe.
