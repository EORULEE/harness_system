---
name: harness-sweep-summary
description: "sweep child run들의 metrics.json을 읽어 leaderboard.csv + 요약 생성(primary 정렬·k-seed 평균/표준편차). 단일지표 정렬 경고·유의성 not_computed(날조 금지). 결정적. 'sweep 요약/leaderboard' 시 명시 호출."
disable-model-invocation: true
allowed-tools: [Bash, Read]
---

# harness-sweep-summary — sweep leaderboard

> sweep 묶음 run → leaderboard. 정본 `docs/leeer-experiment-registry-design.md` §5/§7.

## 실행
```bash
python3 .claude/skills/harness-sweep-summary/sweep_summary.py <runs_parent_dir> --metric <m> [--goal max|min] [--use last|best]
```
- 각 run `metrics/metrics.json`의 primary(best/last) 추출 → 정렬 + 같은 base의 seed 묶어 k-seed mean/std.
- 산출 `leaderboard.csv`(rank·exp_id·value·seed·k_seed_mean/std·significant).

## 안전·규율
- 수치 **추출만**(변경 0). **significant=not_computed**(유의성·다중검정 날조 금지 — 통계는 사람/별도).
- 단일지표만으로 결론 금지(여러 metric은 compare 병행). secret 금지.
