---
name: harness-systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior (incl. HWP/DOCX/Lottie/browser/serve_html issues) — enforces root-cause investigation FIRST (reproduce, read errors, check recent changes, trace data flow) before proposing any fix. Symptom fixes are failure. Explicit call only.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash
---

# harness-systematic-debugging (근본원인 우선)

bug·test 실패·이상 동작에서 **fix 전에 근본원인 조사**를 강제하는 thin wrapper. 정본 = `_dev-discipline-core/systematic-debugging-rules.md` · 출처 = `vendors/obra-superpowers/upstream-systematic-debugging.md`(MIT).

## 4단계 (순서 고정)
1. **근본원인 조사**: 에러 정독 → 일관 재현 → 최근 변경 diff → 경계별 증거 → 데이터 흐름 역추적.
2. **패턴 분석**: 정상 코드 완독 → 정상↔고장 차이 전수.
3. **가설·검증**: 단일 가설("X 근본, 근거 Y") → 최소 변경 → 한 변수씩.
4. **구현**: 실패 테스트 먼저 → 근본만 단일 fix → 회귀 확인. **3+ 실패 → 아키텍처 의심**(에스컬레이션).

## 하네스 도메인
Lottie 빈캔버스·HWP 한컴 hang·serve_html cold-path·DOCX 등 — 규율 파일의 적용 예 참조. fix 후 그림은 **Read 재검증**([[feedback-figure-read-verify]]).

## 경계
명시 호출 전용·advisory. Bash는 **진단(재현·로그·diff) 읽기용**; 실제 fix 적용은 별도 승인 일반 흐름. 최종권위 stop-guard/hookify.
