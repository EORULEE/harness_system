# Secret Scan Notes
secret 스캔 시 2개 테스트 파일이 secret 패턴에 매치되나 **전부 의도된 FAKE**(실키 아님):
- `tests/smoke_stop_guard_notification.sh` · `tests/smoke_active_context_emit.sh`
이들은 **secret-masking 안전장치가 작동하는지 검증**하는 테스트 입력으로, `sk-FAKETESTKEY...`·`ghp_FAKETESTKEY...` 처럼 `FAKE`/`TEST` 마커를 포함한다. **실제 credential residual = 0.**
