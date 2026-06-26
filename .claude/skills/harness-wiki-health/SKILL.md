---
name: harness-wiki-health
description: "vault/wiki의 구조 건강검사(결정적·LLM 0). 빈/스텁 파일·index↔디스크 동기·log 커버리지를 점검. ingest/lint 전 pre-flight로 매 세션 안전 실행. 명시 호출 전용."
disable-model-invocation: true
allowed-tools: [Bash, Read]
---

# harness-wiki-health — 위키 구조 건강검사 (결정적)

> vendored `_wiki-core/vendors/llm-wiki-agent/tools/health.py`(byte-exact)를 wrapper로 실행.
> **LLM 호출 0** — 토큰 비용 없음, 매 세션 lint/ingest 전에 먼저 돌린다.
> 거버넌스 정본 = [[_wiki-core/wiki-rules.md]].

## 무엇을 검사하나 (결정적)
- **빈/스텁 파일**: frontmatter 외 본문 < 100자 (rate-limit 손상 등)
- **index 동기**: `vault/wiki/index.md` 항목 ↔ 디스크 실제 파일 (stale/missing)
- **log 커버리지**: `sources/*.md` 중 `log.md`에 ingest 기록 없는 것

## 실행
```bash
python3 .claude/skills/harness-wiki-health/run_health.py          # 리포트 stdout
python3 .claude/skills/harness-wiki-health/run_health.py --json   # 기계판독
python3 .claude/skills/harness-wiki-health/run_health.py --save   # vault/wiki/health-report.md 저장
```
- 위키 경로 기본 = `<project>/vault/wiki` (환경변수 `WIKI_ROOT`로 override).

## 사용 시점
- ingest/lint 전 **pre-flight**(빈 파일 lint는 토큰 낭비 → health 먼저).
- 결과 해석만 보고, 수정은 ingest/lint 또는 사람 결정. 자동 수정 안 함.
