---
name: harness-experiment-register
description: "기존 실험 결과 폴더/로그/metric을 표준 Experiments/runs/<exp_id>/로 등록. 원본 무이동(manifest/link 참조), metric은 원본에서 추출만(history.pickle·csv·json, 변경 0), 새 성능claim·유의성 날조 0. 증류·결론은 2-pass(c-/x-). 에이전트 모드. '실험 등록' 시 명시 호출."
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Task]
---

# harness-experiment-register — 실험 등록 (에이전트 모드)

> 정본 `docs/leeer-experiment-registry-design.md`. 이번 세션 ICEYE·OPERA 수동 등록을 코드화.
> ⚠️ **원본 무이동·수치 무변경·날조 0.** stop-guard·hookify 최종권위.

## 절차
1. **골격 생성**: `python3 new_run.py <Experiments_dir> <exp_id> [project] [machine]` (runs/<exp_id>/ 골격, 기존이면 거부).
2. **원본 metric 추출(변경 0)**: history.pickle/metrics.csv/json/log에서 실수치 → `metrics/metrics.csv`(전체)+`metrics/metrics.json`(요약 best/last). **수치 손대지 말 것.** 없으면 "미보유" 표기(역추적 또는 [source needed]).
3. **experiment.yaml 채움**: git.commit(없으면 unknown)·dataset·config(model/seed)·metrics.primary·integrity(in_sample·**significance=not_computed**). 원본 경로=link.
4. **data/raw_links.yaml**: 원본 위치·dataset link(복사 X).
5. **logs/**: 원본 로그 path 기록(복사 선택).
6. **2-pass(c-/x-)**: card 결론·claim 후보 적대검증(과장·환각·소스 미지지 차단, Task).
7. **review/experiment_card.md** + EXP_INDEX append(`harness-experiment-indexer --append-missing` 또는 직접 1행) + (선택) Wiki experiment/claim(`harness-wiki-ingest`).

## 금지
원본 이동/삭제 · metric 수치 변경 · **새 성능 claim 생성** · **통계 유의성 날조** · secret 출력 · checkpoint 덮어쓰기.
