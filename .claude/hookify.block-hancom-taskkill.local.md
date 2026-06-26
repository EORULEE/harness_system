---
name: block-hancom-taskkill
enabled: true
event: bash
action: block
pattern: (taskkill|tskill|Stop-Process)\b.*\b(hwp|hancom|hangul|한컴|한글)
---
🚫 **차단: WSL에서 한컴(HWP) 프로세스 taskkill**

WSL에서 한컴 interop 프로세스를 taskkill로 반복 강제종료하면 9p/drvfs 마운트가
다운되어 `/mnt/*` 접근이 끊깁니다(파일시스템 복구에 재시작 필요).

대안: 한컴 COM 작업은 정상 종료(`hwp.Quit()`)로 닫고, 멈춘 경우 Windows측에서
직접 처리하세요. 자동화로 taskkill 반복 금지.

(근거: 메모리 feedback_hancom_interop_caution — "WSL 한컴 강제종료 반복 시 drvfs 다운")
