# Lottie 저작 — 하네스 레이어 규칙 (v6)

> ⚠️ **이 문서는 Lottie JSON 저작 규칙의 요약본이 아니다.**
> 저작 규칙(top-level 구조, 레이어, 그룹 래핑, ks 변환, 키프레임, slots, bgColor 의무,
> ?frame 검증, 체크리스트)의 **정본 = `vendors/diffusionstudio-lottie/upstream-SKILL.md`**.
> Lottie를 저작·수정하는 모든 작업은 **그 원본을 직접 Read한 뒤** 수행한다.
> 본 문서는 하네스 환경에 필요한 **추가 규칙만** 정의한다.

## 1. 출력 경로 (하네스 표준)

| 산출물 | 경로 |
|---|---|
| animation brief | `_output/figures/lottie/prompts/<이름>.brief.md` |
| 생성 Lottie JSON | `_output/figures/lottie/json/<이름>.json` (**유일한 정본 저장처**) |
| 프리뷰(스크린샷·GIF 등) | `_output/figures/lottie/previews/` |
| export review 보고 | `_output/figures/lottie/reviews/<이름>.review.md` |

- `public/lottie.json`은 저장처가 아니라 **공식 플레이어 검증 시점에만 복사**하는 작업 사본이다
  (upstream 흐름: App.tsx가 `/lottie.json`을 fetch, vite 플러그인이 저장 시 full-reload).
- 기존 파일 직접 수정 금지 — 신규 파일 생성만.

## 2. 검증 게이트 (Skottie 우선 원칙)

- **검증 = 공식 Skottie/CanvasKit 플레이어가 기본.** lottie-web 재생으로 Skottie 검증을 **대체 금지**
  (upstream-SKILL.md의 "never hand-roll a custom viewer" 준수; custom viewer 제작 금지).
- 공식 플레이어 프로젝트가 로컬에 없거나 `npm ci`/`npm run dev` 미실행 상태에서는:
  - 가능한 것 = **정적 lint만** (JSON parse, 구조 검사 — `lottie-export-review-rules.md`).
  - **금지** = "렌더 검증 완료" 주장. 정직 표기: "정적 lint 통과, Skottie 렌더 검증은 미실행(설치 게이트 대기)".
- `npm install`/`npm ci`/`npm run dev`/node_modules 생성 = **별도 사용자 승인 필수**.
- 렌더 검증 방법(승인 후) = upstream-SKILL.md의 frame pinning(`?frame=N&paused=1`,
  `data-testid="lottie-canvas"`) 절차 그대로.

## 3. 삽입 전 검토 의무

- HTML 리포트·HWP·DOCX·슬라이드에 Lottie(또는 그 파생 GIF/MP4/정지프레임)를 넣기 **전에**
  `harness-lottie-export-review` 수행 → PASS 판정 필요.
- 생성 HTML에 **CDN `<script>` 핫링크 절대 금지** — vendored 고정 파일만
  (2024-10 lottie-player npm 공급망 공격 실사례. L0 분석 리스크표).
- 서드파티(외부 출처) Lottie JSON 임베드 시 expressions(JS 평가 표면) 검사·제거 후 사용.

## 4. 용도 한계 (모든 산출물에 적용)

- Lottie는 **설명용 motion graphic**이다 — 정밀 과학 데이터 figure가 아니다.
  수치·좌표·축이 정확해야 하는 그림(논문 figure, 측정 결과)은 기존 figure 파이프라인 사용.
- **특허 도면 정본으로 사용 금지.**

## 5. Secret 정책

- brief·JSON·review 어디에도 자격증명(API key/token/비밀번호) 원문 금지.
- 외부 자산 URL을 brief에 적을 때 쿼리스트링의 토큰류 제거. 산출 후 secret scan
  (`scripts/secret_masking.py` 패턴) residual 0 확인.
