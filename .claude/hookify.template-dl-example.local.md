---
name: template-dl-example
enabled: false
event: bash
action: block
pattern: \brm\b.*\.(ckpt|pth|pt|safetensors|h5)\b
---
🧩 **[템플릿 — enabled:false] 딥러닝 규칙 작성 예시**

이 파일은 "딥러닝 학습 시 하지 마" 류 규칙을 어떻게 만드는지 보여주는 견본입니다.
위 예시는 *체크포인트 파일(.ckpt/.pth/...) 삭제*를 차단합니다.

**새 규칙 추가 방법:**
1. `.claude/hookify.<이름>.local.md` 복사
2. `enabled: true`, `event: bash|file`, `action: block|warn`, `pattern:` 또는 `conditions:` 설정
3. 본문에 차단 이유 + 대안 작성
4. 적용 대상 프로젝트의 `.claude/`에 둘 것 (규칙은 **cwd 기준** 로딩 — 프로젝트별)

**딥러닝 프로젝트(예: 서버 00_KMA)에서 자주 쓰는 패턴:**
- 학습 중 체크포인트 `rm` 차단 (위 예시)
- `--resume` 없이 재학습 시작 경고: `event: bash`, `pattern: train\.py(?!.*--resume)`
- seed 미설정 학습 경고 등

실제 금지사항이 정해지면 `enabled: true`로 바꾸고 해당 프로젝트 `.claude/`에 복사하세요.
