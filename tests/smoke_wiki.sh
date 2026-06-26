#!/usr/bin/env bash
# smoke_wiki — LLM Wiki 결정적 도구(schema_lint·health·graph)가 WIKI_ROOT 기반으로 작동하는지.
# 샘플 위키 생성 → 3 도구 실행 → 통과 확인. (ingest/query는 에이전트 모드라 제외.)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SK="$ROOT/.claude/skills"
W="$(mktemp -d)/wiki"; trap 'rm -rf "$(dirname "$W")"' EXIT
mkdir -p "$W/concepts" "$W/entities"
P=0; F=0; ok(){ echo "  ✓ $1"; P=$((P+1)); }; no(){ echo "  ✗ $1"; F=$((F+1)); }

cat > "$W/index.md" <<'EOF'
---
title: "Index"
type: domain
tags: []
last_updated: 2026-01-01
---
- [[concepts/sample]]
- [[entities/thing]]
EOF
cat > "$W/log.md" <<'EOF'
---
title: "Log"
type: domain
tags: []
last_updated: 2026-01-01
---
- 2026-01-01 sample
EOF
cat > "$W/concepts/sample.md" <<'EOF'
---
title: "Sample Concept"
type: concept
tags: [x]
last_updated: 2026-01-01
sources: []
as_of: 2026-01-01
---
이 개념은 [[entities/thing]] 과 연결된다.
EOF
cat > "$W/entities/thing.md" <<'EOF'
---
title: "Thing"
type: entity
tags: [y]
last_updated: 2026-01-01
sources: []
as_of: 2026-01-01
---
[[concepts/sample]] 에서 참조됨.
EOF

# T1 schema_lint PASS
WIKI_ROOT="$W" python3 "$SK/_wiki-core/schema_lint.py" 2>&1 | grep -q "PASS" && ok "T1 schema_lint PASS(스키마 검증)" || no "T1 schema_lint"
# T2 health 실행(리포트 생성)
WIKI_ROOT="$W" python3 "$SK/harness-wiki-health/run_health.py" >/dev/null 2>&1 && ok "T2 health 리포트 생성" || no "T2 health"
# T3 graph 빌드(노드/엣지 + self-contained html)
WIKI_ROOT="$W" python3 "$SK/harness-wiki-graph/run_graph.py" >/dev/null 2>&1
[ -f "$W/graph/graph.html" ] && grep -q "vis" "$W/graph/graph.html" 2>/dev/null && ok "T3 graph self-contained HTML(wikilink 파싱)" || no "T3 graph"
# T4 graph 외부요청 0(self-contained)
[ -f "$W/graph/graph.html" ] && ! grep -qE "https?://(cdn|unpkg|jsdelivr)" "$W/graph/graph.html" && ok "T4 graph 외부 CDN 0(self-contained)" || no "T4 외부요청"

echo "[wiki] PASS $P / FAIL $F"; [ $F -eq 0 ]
