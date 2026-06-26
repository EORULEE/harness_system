# loop-visual-routing-policy.md — 그림 생성 목적별 라우팅 정책

> r3 후보(harness-2026-06-23-r3-loop-rc) 증분. r2 불변. "그림 그려줘/개념도 만들어줘/인포그래픽
> 만들어줘" 자연어 요청을 **목적과 정확도 요구**에 따라 5경로 중 적절한 곳으로 라우팅한다.
> **새 이미지 생성 모델·별도 오케스트레이터를 만들지 않는다** — 기존 Claude SVG·NotebookLM·Gemini·
> Lottie·Claude Design 구성만 재사용한다. 정본 그림 규율 = 글로벌 `feedback_figure_generation_routing`
> + `references/figure-generation-routing.md`.

## 1. 자동 선택 우선순위
| 우선 | 조건 | 경로 |
|---|---|---|
| **A** | 정확한 과학·기술 도식(개념도·구조·흐름도·아키텍처·특허 선화·정확한 화살표/라벨) | **Claude SVG** |
| **B** | 제공 자료(논문·PDF·보고서) 기반 요약 인포그래픽·source-grounded deck | **NotebookLM** |
| **C** | 사실적·창의적·고품질 이미지(hero image·콘셉트 일러스트·텍스트 포함 인포그래픽·스타일 변환) | **Gemini Nano Banana Pro** |
| **D** | 움직임 필요(궤도·관측·처리 흐름 모션) | **Lottie** |
| **E** | 슬라이드·HTML 전체 배치(생성물 배치·레이아웃·디자인 시스템) | **Claude Design** |

## 2. ⚠️ 하드룰 (안전 — 위반 시 HOLD)
- **논문 정량 figure(성능 그래프·정량 chart·측정값 plot)·특허 정본 도면에는 생성형 이미지 모델(Nano Banana Pro) 금지.**
  → **실제 데이터 기반 chart/SVG 경로**(Claude SVG 또는 데이터 플로팅)로 강제 라우팅.
- **안전룰 > 사용자 선택**: 정량/특허 figure 요청이면 AskUserQuestion 에서 **'Gemini Nano Banana Pro로 생성' 옵션을 제시하지 않으며**, 사용자가 명시 선택해도 **거부(HOLD)** 하고 데이터 chart/SVG 로 전환(메뉴 우회 차단).
- 생성형 이미지(Nano Banana Pro) 속 **수치·인용·라벨을 사실 근거로 사용하지 않는다**(장식/콘셉트 전용).
- 어떤 경로 산출도 **과학적 정본이라고 주장하지 않는다**(특허 정본·논문 정량근거 아님). 실제 그림은 **추출 우선**(자작 금지) — `feedback_figure_sourcing`.

## 3. 경로별 정의

### A. Claude SVG  (로컬·승인 불필요 가능)
- **대상**: 논문용 개념도 · 위성/센서/지표/수체 관측 구조 · 처리 흐름도 · 모델 아키텍처 · 특허 참고용 선화 · 수정 가능한 벡터 · 정확한 화살표/라벨/도형.
- **출력**: SVG + (필요 시) PNG/PDF preview + editable source.
- **규칙**: 실제 수치·센서명·축척·라벨은 **source 에서 확인** · scientific figure ↔ 장식 illustration 구분 · 특허 정본 주장 금지 · **외부 업로드 없이 로컬 생성**.
- **승인**: 불필요(단순 로컬 SVG는 사용자가 "바로 만들어줘"라고 명시하면 추가 승인 없이 생성). **단 source 는 content-lock allow 내(비민감)만** — `references/private/**`·Data·Experiments·secret 을 source 로 쓰면 "바로 만들어줘" 예외 적용 안 됨(민감자료 사용 = human-gated).

### B. NotebookLM  (업로드 = human-gated)
- **대상**: 논문/PDF/보고서 **근거** 인포그래픽 · 여러 문서 핵심 설명 그림 · source-grounded slide deck · 교육/설명용 시각 요약.
- **입력**: 승인된 source 파일 · 핵심 주장 · audience · 스타일 · content-lock.
- **출력 후보**: infographic PNG · slide deck PPTX/PDF.
- **규칙**: **업로드 전 AskUserQuestion 승인** · private·Data·Experiments 원본·secret 업로드 금지 · **업로드 allow-list SoT = `Report/design/content-lock.yaml`**(allow/allow_conditional 만 후보, default-deny; `references/private/**`·Data·Experiments·secret·env·vault·memory 는 deny 명시) · 생성 후 모든 수치/인용/문구 **원문과 검증** · SVG 출력이라 주장 금지.

### C. Gemini Nano Banana Pro  (유료/API = human-gated · 현재 미배선)
- **대상**: 사실적 위성/지구/수체 콘셉트 일러스트 · 발표 hero image · 고품질 시각 설명 · 한/영 텍스트 포함 인포그래픽 · 스타일 변환/이미지 편집.
- **규칙**: 품질 우선 경로 · **유료 API/외부 생성 전 AskUserQuestion 승인** · **계정·quota 상태 먼저 확인** · **API 접근 없으면 Gemini 앱용 prompt package 만 생성**(정직 표기) · 이미지 속 수치/인용 사실근거 사용 금지 · **논문 정량 figure·특허 정본에 사용 금지**(§2 하드룰).
- **현 상태**: Nano Banana Pro 이미지 생성 **미배선**(현 gemini는 텍스트 전용) → 기본 산출 = prompt package. 배선 시 §승인 후 호출.

### D. Lottie  (export review = 삽입 전 결정적 게이트)
- **대상**: HTML 보고서 간단 설명 애니메이션 · 위성 궤도/관측/처리 흐름 모션.
- **규칙**: 기존 `harness-lottie-*` + player 사용 · **export review PASS 전 삽입 금지**(harness-lottie-export-review = **deterministic 검증 게이트**, parse·keyframe·blank render 위험 → PASS/HOLD. 사람 승인이 아니라 검증 통과가 삽입 조건. 외부 공개 시에만 human-gated).

### E. Claude Design  (sync·Published = human-gated)
- **대상**: 생성된 SVG/PNG/Lottie 를 슬라이드·HTML 배치 · 발표 전체 레이아웃 · 프로젝트 디자인 시스템 적용.
- **규칙**: 이미지 자체의 과학적 정본 아님 · **content-lock 유지** · **design-sync·Published 는 사용자 승인**.

## 4. 실행 전 계획(8항목) — 그림 요청 시 필수
1. 그림 용도  2. 선택한 생성 경로  3. 선택 이유  4. 입력 자료  5. 산출 형식
6. 수치·인용·라벨 보호 항목  7. 외부 업로드·비용 여부  8. 검증 방법

그다음 **AskUserQuestion** 7 선택지:
`추천 경로로 생성` · `Claude SVG로 생성` · `NotebookLM으로 생성` · `Gemini Nano Banana Pro로 생성` ·
`두 가지 경로로 비교` · `계획 수정` · `취소`.

- **예외**: 단순 로컬 SVG는 사용자가 **"바로 만들어줘"** 라고 명시하면 추가 승인 없이 생성(단 source 비민감, §3.A).
- **정량/특허 figure 요청 시**: `Gemini Nano Banana Pro로 생성` 옵션을 **선택지에서 제외**(§2 하드룰) — 대신 `Claude SVG로 생성`(데이터 chart/SVG)을 추천.

## 5. 반드시 사용자 승인 (human-gated)
NotebookLM 자료 업로드 · Gemini 유료/API 호출 · Claude Design sync · 외부 공개 · 원본 이미지 편집 · 민감자료 사용.
- **업로드/공개 allow-list SoT** = `Report/design/content-lock.yaml`(allow/allow_conditional 만 후보, **default-deny**). `references/private/**`(초소형SAR 원본 등)·Data·Experiments·secret·env·vault·memory·ACTIVE_CONTEXT 는 **deny 명시(절대 sync/업로드 금지)**.

## 6. 산출물 경로 (프로젝트 루트 상대)
```
Report/design/briefs/        # animation/figure brief
Report/design/assets/svg/    # Claude SVG editable source
Report/design/assets/raster/ # PNG/JPG (NotebookLM·Gemini 산출·preview)
Report/design/assets/lottie/ # Lottie JSON
Report/design/references/    # prompt package·source 참조
Report/design/exports/       # PPTX/PDF/배치 산출
Report/design/reviews/       # 검증 리포트(PASS/HOLD)
```

## 7. 경로별 validation_mode (loop-verifier-policy 정합)
| 경로 | validation_mode | 검증 항목 |
|---|---|---|
| Claude SVG | deterministic-only | XML/SVG parse · 텍스트/라벨 확인 · viewBox/종횡비 · PNG preview 렌더(Read 시각검증) · source 수치 대조 |
| NotebookLM | deterministic-only + human-gated | source allow-list · 수치/인용/주장 대조 · visual/factual 오류 검사 |
| Nano Banana Pro | deterministic-only + human-gated | prompt 준수 · 텍스트 오탈자 · 센서/위성/물리 구조 오류 · content-lock 위반 · 해상도/종횡비 |
| Lottie | deterministic-only | parse · keyframe · blank render 위험 · export review PASS/HOLD |
| Claude Design | deterministic-only + human-gated | content-lock · 배치 렌더 검증 · sync/publish 승인 |

**모든 경로 공통**: secret residual 0 · source attribution · **사용자 시각 검토**(생성 래스터/렌더는 Read 로 시각검증 — `feedback_figure_read_verify`) · PASS/HOLD 판정.
