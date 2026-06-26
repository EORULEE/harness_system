---
name: block-git-no-verify
enabled: true
event: bash
action: block
pattern: git\s+(commit|push|merge|rebase)\b[^"']*--no-(verify|gpg-sign)|git\s+commit\b[^"']*\s-n\b
---
🚫 **차단: git --no-verify / --no-gpg-sign**

훅(pre-commit 등)을 건너뛰거나 서명을 우회하는 것은 **사용자가 명시적으로 요청한
경우에만** 허용됩니다. 훅이 실패하면 우회하지 말고 근본 원인을 고쳐 새 커밋을 만드세요.

정말 필요하면 사용자에게 먼저 확인받고, 이 규칙을 일시적으로
`enabled: false`로 바꾼 뒤 진행하세요.

(근거: 글로벌 CLAUDE.md — "훅 스킵(--no-verify) 금지, 사용자 명시 요청 시 예외")
