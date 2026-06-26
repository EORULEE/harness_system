# VENDOR — llm-wiki-agent (벤더링 출처·일탈 기록)

## 출처
- 레포: https://github.com/SamurAIGPT/llm-wiki-agent
- 커밋: `f837f5bde3d72a600bcab558a469f1f74f00d9c3`
- 라이선스: **MIT** (LICENSE 원문 보존: `vendors/llm-wiki-agent/LICENSE` — 재배포 시 첨부 의무)
- 벤더링일: 2026-06-16
- 개념 계보: Vannevar Bush Memex(1945) → Karpathy "LLM-maintained wiki"

## 벤더링 범위 (byte-exact, 무수정)
| 파일 | sha256 | 역할 |
|---|---|---|
| `tools/build_graph.py` | `fe77a99bb7ddbad00b869ed4505aaa2e7d70a6bcc8dd7b0b06195fd1b102524e` | 지식그래프(EXTRACTED wikilink 엣지·Louvain 커뮤니티·vis.js HTML) |
| `tools/health.py` | `c2a6db70e500b6ca405e84866632c3757c77088e6d580f1255c493b1a3ed32b7` | 결정적 구조검사(빈파일·index 동기·log 커버리지) |
| `vis-network/vis-network.min.js` | `f53f833ddb9bf97efe856bb0637d4fe88f39e39999c7e94a4b8afc8de8a1a2e5` | graph.html 인라인용 vis-network **9.1.9**(visjs, Apache-2.0/MIT 듀얼, LICENSE 동봉). CDN 대체 = self-contained |

> 위 2파일은 **upstream 원본 그대로**(수정 0). 검증: `sha256sum`이 위 값과 일치해야 함.

## 의도적 일탈 (충돌 해소 — 계약 contract-wiki-vendor-2026-06-16)
1. **litellm 미사용**: `build_graph.py:71 call_llm`은 INFERRED(LLM) 엣지 전용 lazy import. 우리는 **EXTRACTED 경로만**(`build_graph(infer=False)`) 호출 → litellm 불필요·미설치. INFERRED/AMBIGUOUS 엣지는 v1 제외(필요 시 에이전트 모드로 별도).
2. **경로 비침습 재지정**: 벤더 원본은 `REPO_ROOT=__file__.parent.parent` 기준 `wiki/`·`graph/`를 가정. 원본을 고치지 않고 **wrapper가 모듈 상수를 monkeypatch**해 `vault/wiki/`·`vault/wiki/graph/`로 돌린다(`harness-wiki-{health,graph}/run_*.py`).
3. **미벤더링(의도)**: `ingest.py`·`lint.py`·`query.py`(litellm 의존 LLM 경로)·`file_to_md.py`·`pdf2md.py`(markitdown/별도 변환)·`heal.py`·`refresh.py`. 이들의 **워크플로 로직은 SKILL.md로 포팅**(에이전트 모드), 실행 바이너리로는 안 가져온다.
4. **루트 `CLAUDE.md`/`GEMINI.md`/`AGENTS.md` 미설치**: ambient 지시 파일 금지(하네스 hard rule). 스키마는 `page-schema.yaml`+`wiki-rules.md`로 변환.
5. **wikilink 해석 보강(함수 monkeypatch)**: 벤더 `build_extracted_edges`는 bare `[[stem]]`만 매칭 → 위키링크 `[[path/file|alias#anchor]]` 미해석. `harness-wiki-graph/run_graph.py`가 **벤더 파일 불변** 유지하고 해당 함수만 런타임 교체(경로/별칭/앵커 strip 후 stem·page_id 양쪽 해석). 1→41 엣지.
6. **graph.html self-contained**: 벤더 `render_html`은 `unpkg.com/vis-network` CDN `<script src>`를 박아넣음. wrapper가 빌드 후 그 태그를 **벤더 vis-network.min.js 인라인 `<script>`로 치환**(외부요청 0, 하네스 HTML 규율). 벤더 build_graph.py는 불변.

## 업스트림 갱신 절차
- 새 커밋 반영 시: 동일 경로 재다운로드 → sha256 갱신 → 본 표 갱신 → wrapper 호환성(상수명 WIKI_DIR/GRAPH_DIR 등) 재확인.
