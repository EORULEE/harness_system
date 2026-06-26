# LLM Wiki — 사용법

마크다운 기반 지식 위키. 페이지 = **프론트매터 + 본문 + `[[wikilink]]`**. 결정적 도구(lint·health·graph)는 계정 없이 바로 작동, 에이전트 도구(ingest·query)는 Claude가 수행.

> 개인정보 보호로 **promote(클라우드/NAS 동기)·storage-audit 는 미포함** — 로컬 위키 운영만.

## 1. 위키 위치 설정 (WIKI_ROOT)
기본 = `<project>/vault/wiki`. 본인 노트 폴더로 바꾸려면:
```bash
export WIKI_ROOT=/path/to/your/wiki     # 예: ~/notes/wiki
mkdir -p "$WIKI_ROOT"
```

## 2. 페이지 구조 (프론트매터)
모든 페이지 공통 필수: `title` · `type` · `tags` · `last_updated`.
type = `source | entity | concept | synthesis | domain | method | dataset | sensor | metric`.
```markdown
---
title: "Relative Temperature"
type: concept
tags: [thermal]
last_updated: 2026-06-26
sources: []
as_of: 2026-06-26
---
상대 지표온도는 [[entities/landsat]] 로 산출한다.   ← [[wikilink]] 로 페이지 연결
```
- `source` 타입은 추가 필수: `source_file·sha256·trust·trust_boundary·date`.
- 인용은 **실재하는 것만**(`cite: ref:<KEY>`), 없으면 "DOI-only" 정직 표기 — **날조 금지**.

## 3. 결정적 도구 (계정 0, 바로 실행)
```bash
# 스키마 검증 (필수 필드·타입 위반 탐지)
WIKI_ROOT=$WIKI_ROOT python3 .claude/skills/_wiki-core/schema_lint.py

# 건강성 리포트 (고아 페이지·로그 커버리지 등)
WIKI_ROOT=$WIKI_ROOT python3 .claude/skills/harness-wiki-health/run_health.py
WIKI_ROOT=$WIKI_ROOT python3 .claude/skills/harness-wiki-health/run_health.py --json

# 지식 그래프 빌드 → graph/graph.html (self-contained, 외부요청 0)
WIKI_ROOT=$WIKI_ROOT python3 .claude/skills/harness-wiki-graph/run_graph.py
# 그래프 열람: 로컬 브라우저로 graph/graph.html 열기
```

## 4. 에이전트 도구 (Claude 가 수행 — 명시 호출)
Claude Code 세션에서 자연어로:
- **ingest**: "이 소스를 위키에 ingest 해줘" → 소스카드 + entity/concept 페이지 + 모순 플래그 생성(2-pass 증류).
- **lint**: "위키 lint 해줘" → 스키마 + 링크 무결성 리포트.
- **query**: "위키에서 X 가 뭐야?" → 위키 근거로 답 + (선택) synthesis 페이지 저장.

## 5. 검증
`bash tests/smoke_wiki.sh` → schema_lint·health·graph 작동 확인(4/4). selftest 에도 포함.

## 한계
- ingest/query 는 Claude(에이전트)가 수행하므로 Claude Code 필요.
- 인용 실재검증은 선택 — reference manager(MCP) 연결 시 강화, 없으면 수동.
