---
name: block-windows-system-change
enabled: true
event: bash
action: warn
pattern: taskkill(\.exe)?\s+[^|]*/[fF]\b|sc(\.exe)?\s+(config|failure|delete|stop)\b|reg(\.exe)?\s+(add|delete)\b|winget\s+(install|uninstall|upgrade)\b|bcdedit|powercfg(\.exe)?\s+/(change|setactive|hibernate|import)\b|Set-Service|Stop-Service|safeboot
---
⚠️ **[system-change] OS 시스템을 변경하는 명령입니다.**

사용자 규칙(2026-06-18, 강력): **"시스템은 왠만하면 건드리면 절대 안 돼."**

변경 전 3가지 확인:
1. 근본 원인을 **100% 확정**했는가? (추측·부분 진단으로 변경 금지)
2. 전원·드라이버·예약작업·시작프로그램까지 **전수 진단**했는가?
3. 사용자에게 **명시적 승인**을 받았는가?

되돌릴 수 없는 제거·삭제·레지스트리·서비스·드라이버·전원·bcdedit·안전모드는 특히 신중.
진단(읽기: tasklist·sc query·reg query·powercfg /query·Get-WinEvent)만이면 무시 가능.

(근거: memory [[feedback-dont-touch-system]] — ExplorerPatcher 성급 제거가 자가치유로
무효화되고 검은화면·신뢰손상을 부른 2026-06-18 사건. 해결은 제거 아닌 호환 복원이었음.)
