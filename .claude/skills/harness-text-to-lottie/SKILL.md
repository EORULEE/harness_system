---
name: harness-text-to-lottie
description: Lottie(Bodymovin) JSON 저작 — upstream text-to-lottie 스킬(diffusionstudio/lottie, vendored 스냅샷)을 source of truth로 따르는 thin wrapper. 산출물은 _output/figures/lottie/json/에 저장, Skottie/CanvasKit 공식 플레이어 검증 흐름 호환. 명시 호출 전용.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Write, Bash
---

# harness-text-to-lottie — upstream 규칙의 thin wrapper

> **이 파일은 저작 규칙을 정의하지 않는다.** 규칙 정본(source of truth) =
> `.claude/skills/_visual-core/vendors/diffusionstudio-lottie/upstream-SKILL.md`
> (diffusionstudio/lottie @ `3360f2e78be9…`, byte-exact 스냅샷 — `upstream-commit.txt` 참조).
> **저작 전 반드시 그 원본 전체를 Read하고 그대로 따른다.** 요약본 사용 금지.

## 절차

1. **brief 확인**: `_output/figures/lottie/prompts/<name>.brief.md` (없으면 `harness-lottie-planner` 먼저 제안).
2. **upstream-SKILL.md 전체 Read** — 특히 반드시 적용:
   - top-level `v/fr/ip/op/w/h/assets/layers` 구조 (Required top-level shape)
   - **shape elements의 group(`ty:"gr"`) 래핑 + 그룹 말미 `ty:"tr"`** — 위반 시 Skottie blank (#1 gotcha)
   - 색상 0–1 RGBA · keyframe `s`=배열 · slots/`sid` · bgColor 슬롯+배경 레이어 의무 · 마무리 체크리스트
3. **저작·저장**: 결과 JSON = `_output/figures/lottie/json/<name>.json` (**정본 저장처는 여기뿐**).
4. **JSON parse check** (정적, 항상): `python3 -c "import json;json.load(open('<file>'))"`
   (upstream checklist 1의 node 한 줄과 동등 — node 가용 시 그 명령 그대로도 가능).
5. **public/lottie.json flow**: upstream 플레이어는 `public/lottie.json`을 fetch하고 저장 시
   자동 full-reload된다(vite watch). 따라서 **공식 플레이어로 검증할 때만** 정본을
   `<player>/public/lottie.json`으로 **복사**한다(이동 금지). 슬롯 라벨이 필요하면
   `public/controls.json` 사이드카도 함께.
6. **frame pinning 검증 계획 수립**(실행은 게이트 뒤): `?frame=0|중간|마지막&paused=1` +
   `data-testid="lottie-canvas"` 스크린샷으로 nonblank·모션 위치 확인 — upstream 절차 그대로.
7. **HTML/HWP/DOCX 삽입 전 `harness-lottie-export-review` 수행** — PASS 없이는 삽입 금지.

## 검증 게이트 (정직 의무)

- 검증 기본 = **공식 Skottie/CanvasKit 플레이어**. custom viewer 제작 금지,
  lottie-web 재생으로 Skottie 검증 **대체 금지** (upstream "never hand-roll" 준수).
- 플레이어 프로젝트 미설치(`npm ci`/`npm run dev` 미실행) 상태에서는 4번 parse + 정적 lint까지만
  가능 — 그 상태로 **"렌더 검증 완료" 주장 금지**, "정적 검사만 수행, 렌더 검증은 설치 승인 대기"로 보고.
- npm install/dev 서버 = 별도 사용자 승인.

## 공통 제약

- 명시 호출 전용. 기존 파일 직접 수정 금지(신규 생성 + 플레이어 public/으로의 복사만).
- Lottie = 설명용 motion graphic — 정밀 과학 데이터 figure 아님, 특허 도면 정본 사용 금지.
- secret 원문 출력 금지. 생성 HTML에 CDN 핫링크 금지(`lottie-animation-rules.md` §3).
