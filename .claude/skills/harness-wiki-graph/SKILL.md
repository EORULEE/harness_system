---
name: harness-wiki-graph
description: "vault/wiki의 지식그래프 생성(결정적). 페이지의 [[wikilink]]를 EXTRACTED 엣지로 파싱→Louvain 커뮤니티→self-contained graph.html(vis.js). litellm 미사용(INFERRED/LLM 경로 제외). 명시 호출 전용."
disable-model-invocation: true
allowed-tools: [Bash, Read]
---

# harness-wiki-graph — 지식그래프 빌드 (결정적·EXTRACTED만)

> vendored `_wiki-core/vendors/llm-wiki-agent/tools/build_graph.py`(byte-exact)를 wrapper로 실행.
> **결정적 경로만**: `[[wikilink]]` → EXTRACTED 엣지 + Louvain 커뮤니티 검출. **litellm 불필요**(INFERRED/AMBIGUOUS LLM 엣지는 v1 제외).
> 거버넌스 정본 = [[_wiki-core/wiki-rules.md]].

## 산출
- `vault/wiki/graph/graph.json` — 노드(type별 색)·EXTRACTED 엣지
- `vault/wiki/graph/graph.html` — 인터랙티브 vis.js 시각화 (self-contained, 외부요청 0)

## 실행
```bash
python3 .claude/skills/harness-wiki-graph/run_graph.py           # 빌드
python3 .claude/skills/harness-wiki-graph/run_graph.py --open    # 빌드 후 브라우저 열기(로컬)
```
- 위키 경로 기본 = `<project>/vault/wiki` (환경변수 `WIKI_ROOT`로 override).
- 의존성: `networkx`(커뮤니티 검출). 미설치 시 경고 후 그래프는 생성되나 커뮤니티 비활성.

## 주의
- INFERRED(의미추론) 엣지가 필요하면 v1 범위 밖 — 에이전트 모드로 별도 설계(litellm 도입 금지).
- HTML 열람 제공은 로컬=브라우저, 헤드리스=본인 호스팅).
