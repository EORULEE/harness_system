---
name: harness-lottie-export-review
description: 생성된 Lottie JSON의 삽입 전 검토 — JSON parse·top-level·group wrapping·keyframe·bgColor/controls·blank render 위험·frame 검증 계획·HTML/발표자료 적합성을 검사해 PASS/HOLD 판정. HTML/HWP/DOCX 삽입 전 의무 게이트. 명시 호출 전용.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Write, Bash
---

# harness-lottie-export-review — 삽입 전 검토 게이트

체크리스트 정본 = `.claude/skills/_visual-core/lottie-export-review-rules.md` (A1~A9 정적 검사 ·
B 렌더 검증 계획 · C 삽입 판단 · D 판정 기준). 구조 규칙의 상위 근거 =
`_visual-core/vendors/diffusionstudio-lottie/upstream-SKILL.md`.

## 절차

1. 대상: `_output/figures/lottie/json/<name>.json` (다른 경로면 정본 위치로 먼저 정리 제안).
2. **A 정적 검사 전 항목 실행** (설치 불요): JSON parse → top-level 필드(`v/fr/ip/op/w/h/assets/layers`)
   → shape group wrapping(`gr`/`it`/말미 `tr`) → keyframe 구조(`s`=배열, `t`, 루프 일치)
   → 색 0–1 RGBA → 레이어 op 커버 → bgColor/controls.json 필요 여부 → blank render 위험
   → secret 패턴. 검사는 Read+python3 one-liner 수준의 읽기 실행만.
3. **B 렌더 검증 계획 수립**: frame 0/중간/마지막 3점 `?frame=N&paused=1` 계획.
   Skottie preview 필요 여부 판정(신규/구조 변경=필요). **실행은 설치 승인 게이트 뒤** —
   미실행이면 보고서에 "렌더 검증 미실행(게이트 대기)" 정직 명기, 완료 주장 금지.
4. **C 삽입 판단**: HTML 리포트 삽입 가능성(vendored lottie-web 확보 여부·self-contained·CDN 금지),
   발표자료는 HTML 슬라이드=임베드 / PPT·HWP=GIF/MP4/keyframe export 필요 여부 제안.
   과학 데이터 figure·특허 도면 정본 용도 = 무조건 HOLD.
5. **판정·보고**: `_output/figures/lottie/reviews/<name>.review.md` — 항목별 결과표 + **PASS/HOLD** + 사유 + 후속 조치.

## 공통 제약

- 명시 호출 전용. 검토 대상·기존 파일 수정 금지(보고서 신규 생성만).
- npm install/dev 서버 실행 금지(별도 승인). secret 원문 출력 금지.
- Lottie = 설명용 motion graphic — 정밀 figure·특허 도면 정본 아님.
