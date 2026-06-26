---
name: harness-experiment-indexer
description: "Experiments/runs를 스캔해 EXP_INDEX.csv 정합성 점검(누락/고아/불완전 run 리포트). --append-missing 시 누락 run을 stub 행으로 추가(기존행·수치 불변). 결정적·pyyaml 불필요. '실험 색인 갱신/점검' 시 명시 호출."
disable-model-invocation: true
allowed-tools: [Bash, Read]
---

# harness-experiment-indexer — EXP_INDEX 정합성·갱신

> `Experiments/runs/*/` ↔ `EXP_INDEX.csv` 대조. 정본 `docs/leeer-experiment-registry-design.md`.

## 실행
```bash
python3 .claude/skills/harness-experiment-indexer/indexer.py <Experiments_dir>                  # 정합성 리포트(쓰기 0)
python3 .claude/skills/harness-experiment-indexer/indexer.py <Experiments_dir> --append-missing # 누락 run stub append만
```
- 점검: disk-only(INDEX 누락)·index-only(stale)·불완전 run(yaml/metrics 결손).
- `--append-missing`: 누락 run을 `status=needs_fill` stub로 **append만**(기존행·수치 절대 불변). 실값은 register/사람이 채움.

## 안전
- 기존 EXP_INDEX 행·metric **수정 0**·삭제 0. raw·실험 산출 미접촉. secret 출력 금지.
