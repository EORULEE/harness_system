# Lottie Export Review 규칙 (harness-lottie-export-review의 체크리스트 정본)

> 대상: `_output/figures/lottie/json/*.json`. 판정 = **PASS / HOLD** (중간 없음).
> 구조 규칙의 근거는 전부 `vendors/diffusionstudio-lottie/upstream-SKILL.md` — 항목별로 원본 섹션을 참조한다.

## A. 정적 검사 (설치 불요 — 항상 수행)

| # | 검사 | 기준 (upstream 근거) |
|---|---|---|
| A1 | JSON parse | 유효 JSON, 주석·trailing comma 없음 (checklist 1) |
| A2 | top-level 필드 | `v, fr, ip, op, w, h, assets, layers` 전부 존재, `op > ip`, `w/h > 0` (Required top-level shape) |
| A3 | shape group wrapping | 모든 shape primitive/fill/stroke가 `ty:"gr"`의 `it` 안, 각 그룹 마지막에 `ty:"tr"` — **위반 = Skottie blank 렌더** (Shapes — the #1 Skottie gotcha) |
| A4 | keyframe 구조 | 애니메이션 속성 `a:1`의 `k`가 키프레임 배열, 각 `s`는 배열, `t`는 프레임 번호, 루프면 첫·끝값 일치 (Animating a property) |
| A5 | 색상 범위 | fill/stroke `c`가 0–1 RGBA (0–255 발견 = HOLD) |
| A6 | 레이어 가시구간 | 각 레이어 `op`가 애니메이션 구간 커버 (checklist 3) |
| A7 | bgColor/controls | bgColor 슬롯 + 배경 레이어(마지막) + controls.json 라벨 필요 여부 판단 — 플레이어 검증·배포용이면 필요(upstream 의무), 리포트 임베드 단독이면 배경을 리포트 테마색으로 베이크했는지 확인 |
| A8 | blank render 위험 | A3 위반, 빈 `layers`, `ip==op`, 전 레이어 `o:0`, 조성 밖 좌표(전부 w×h 밖) 탐지 |
| A9 | secret | 자격증명 패턴 0건 |

## B. 렌더 검증 계획 (수립은 항상, 실행은 설치 게이트 뒤)

- frame 검증 3점: **frame 0 / 중간(op//2) / 마지막(op-1)** — 각각 `?frame=N&paused=1`로 고정 후
  `data-testid="lottie-canvas"` 스크린샷, nonblank + 의도 모션 위치 확인.
- Skottie preview 필요 여부 판정: 신규 제작·구조 변경 = 필요 / 슬롯 기본값만 변경 = 정적 검사로 충분.
- 미실행 시 보고서에 "렌더 검증 미실행(게이트 대기)" 명기 — 완료 주장 금지.

## C. 삽입·전달 판단

- **HTML 리포트**: 삽입 가능성 판정(vendored lottie-web 경로 확보 여부, self-contained 유지, CDN 금지).
  slots(`sid`) 사용 JSON은 lottie-web ≥5.11.0에서 지원 — 장수명 리포트는 베이크(슬롯값 인라인) 권장.
- **발표자료**: HTML 슬라이드 = 직접 임베드 / PPT·HWP = 네이티브 재생 불가 →
  GIF/MP4/keyframe PNG export 필요 여부와 변환 방법 제안 (HWP 내 GIF 재생은 미검증 — 실물 테스트 전 단정 금지).
- **용도 게이트**: 과학 데이터 figure·특허 도면 정본 용도면 무조건 HOLD.

## D. 판정

- **PASS** = A 전 항목 통과 + (렌더 검증 완료 또는 "미실행" 정직 명기 + 삽입 용도가 정적 검사로 충분한 경우).
- **HOLD** = A 위반 1개 이상, blank 위험, 용도 게이트 저촉, 렌더 검증이 필수인데 미실행.
- 보고서: `_output/figures/lottie/reviews/<이름>.review.md` — 체크리스트 결과표 + 판정 + 사유 + 후속 조치.
