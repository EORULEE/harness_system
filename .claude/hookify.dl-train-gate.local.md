---
name: dl-train-gate
enabled: true
event: bash
action: warn
pattern: (python[0-9.]*\s+\S*train\S*\.py|\btorchrun\b|accelerate\s+launch|\bpapermill\b.*train)(?!.*(\btee\b|2>&1|>\s*\S+\.log|--log|--logdir|tensorboard|wandb|mlflow))
---
⚠️ **딥러닝 학습 실행 감지 — 2대 규율 확인 (feedback-dl-workflow)**

1. **학습 로그/메트릭 영속화했나?** 이 명령에 로그·추적이 안 보입니다 → 택1 이상:
   • **TensorBoard**(`SummaryWriter`/`--logdir runs/<exp>`) ✅  • stdout→파일 `... 2>&1 | tee logs/train_<exp>.log`
   • CSV/JSONL 메트릭  • W&B/MLflow.  (config·seed·per-epoch metric·최종결과 보존, 삭제 금지.
   TB는 코드 내 SummaryWriter면 명령에 안 보일 수 있음 — 이미 쓰고 있으면 무시.)

2. **전처리 + 학습 코드 사용자 검토·승인 받았나?**
   전처리+학습 코드 구현이 완료됐다면 **본 학습 실행 전 사용자 검토 필수**
   (데이터분할·dtype·라벨·손실·LR·증강·평가지표). 승인 전엔 스모크(1-epoch)만,
   본 학습은 승인 후. 미승인 자동 본학습 = 규율 위반.

(warn-only — 차단 아님. 로그 캡처가 포함된 명령엔 발화 안 함. 근거: memory feedback-dl-workflow)
