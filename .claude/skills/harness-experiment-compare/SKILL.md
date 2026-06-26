---
name: harness-experiment-compare
description: "여러 실험 run의 metrics.json을 횡단 비교표(run × metric)로. 모델/seed/파라미터 비교. 수치 추출만·'우위' 단정·유의성 날조 금지(차이만). 결정적. '실험 비교/비교표' 시 명시 호출."
disable-model-invocation: true
allowed-tools: [Bash, Read]
---

# harness-experiment-compare — 실험 횡단 비교표

> 여러 run metrics.json → 비교표. 정본 `docs/leeer-experiment-registry-design.md`.

## 실행
```bash
python3 .claude/skills/harness-experiment-compare/compare.py <run_dir1> <run_dir2> ... [--metrics m1,m2]
python3 .claude/skills/harness-experiment-compare/compare.py --parent <dir> [--metrics m1,m2]
```
- validation/primary 지표를 run별 표로. metric 미지정 시 공통 지표 자동.

## 안전
- 수치 **추출만**(변경 0). **통계근거 없는 '우위' 단정·유의성 날조 금지**(차이 표기만, k-seed/검정은 sweep-summary). secret 금지.
