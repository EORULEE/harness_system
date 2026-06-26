---
name: harness-lottie-planner
description: Lottie 애니메이션 제작 전 animation brief 작성. 목적·용도·장면 순서·duration·fps·frame count·aspect ratio·motion language를 정리해 _output/figures/lottie/prompts/에 저장. 명시 호출 전용.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Write
---

# harness-lottie-planner — Animation Brief 게이트

Lottie 제작(`harness-text-to-lottie`) **앞단**. 산출물 = **animation brief** 1개.

## 절차

1. `.claude/skills/_visual-core/lottie-prompt-schema.yaml`을 Read — brief의 표준 형식.
2. 사용자 요청에서 schema 필드를 채운다: purpose, usage(html-report/html-slide/gif-export/standalone),
   scenes(장면 순서·프레임 구간), timing(fps·frame_count·duration), canvas(w/h/aspect),
   motion_language(ease-in/out, camera push/pan/zoom — upstream 프롬프트 가이드 용어),
   controls_requested, background, assets(근거 SVG/데이터 — 있으면 결과가 크게 좋아짐), constraints.
3. **입력이 부족하면 질문은 최대 3개만** — 가장 결정적인 빈 필드 순(usage > scenes/assets > timing).
   3개로 부족한 나머지는 schema 기본값 + "가정" 표기로 채운다.
4. 저장: `_output/figures/lottie/prompts/<name>.brief.md` (yaml 블록 + 장면 서술).
   brief에 한계 고지 포함: 설명용 motion graphic / 과학 데이터 figure 아님 / 특허 도면 정본 금지.

## 공통 제약 (전 Lottie 스킬 동일)

- 명시 호출 전용(`disable-model-invocation: true`). 기존 파일 직접 수정 금지 — 신규 생성만.
- npm install/dev 서버 실행 금지(별도 승인 게이트). secret 원문 출력 금지.
- 규칙 정본 = `_visual-core/vendors/diffusionstudio-lottie/upstream-SKILL.md` +
  `_visual-core/lottie-animation-rules.md`(하네스 레이어).
