# code-claim evidence gate (코드-동작 주장 증거 게이트)

> 하네스 advisory. 대상 = **"이 코드가 무엇을 한다 / 이 값이 무엇을 측정·계산·반환한다"** 류 *분석·설명* 주장.
> `evidence-before-completion`(완료 주장: 테스트/빌드/배포)의 **형제** — 그쪽은 *완료*, 이쪽은 *동작/의미* 주장.
> 근본 동기: 결정적 코드를 안 읽고 주변 단서(crop 크기·주석·valid%·변수명)로 추론하다 틀리는 반복 실패(정본 [[feedback_read_producing_function]]). 글로벌 §1 probe·§3 원문인용의 코딩 구체화.

## 왜 글(rule)이 아니라 절차인가
규율 텍스트는 "불확실을 인식할 때만" 발동하는데, 이 실패는 **틀린 채 확신**할 때 일어나 트리거가 안 켜진다. 그래서 advisory 한 줄로는 못 막는다. 해법 = ① 읽기를 싸게(serena) ② 증거를 주장의 *전제*로(self-check) ③ 고위험은 독립 검증(cross-model). **잔여 위험 0 아님** — 최종 backstop은 사람.

## Layer 1 — serena-first (읽기를 싸게)
코드-동작/값-의미를 주장하기 전, 그 값을 **생산하는 심볼로 점프**해 전체 파일을 안 읽고도 결정적 라인을 본다.
- `mcp__serena__find_symbol`(정의)·`find_referencing_symbols`(사용처)·`get_symbols_overview`(파일 구조)로 **생산 함수**를 직접 연다. grep→Read offset 도 가능.
- **컨테이너 ≠ 측정**: 잘라낸 영역(crop)·래스터 전체 valid·배열 shape 는 *처리 컨테이너*일 뿐, 실제 산출이 쓰는 **마스크/부분집합/필터/평균 대상**과 다르다. "valid 100%" ≠ "전체가 대상".
- 못 열었으면 추론으로 채우지 말고 "확실치 않음".

## Layer 2 — evidence gate (주장의 전제 = 인용)
"X 가 Y 를 계산/측정/반환/저장/마스킹한다" 류 **모든 동작 주장**은 그 동작을 만드는 **`file:line` 원문 인용**을 동반한다(원문 먼저, 해석 나중 — 글로벌 §3).
- 인용 없으면 → 그 함수를 읽거나, 주장을 **"확실치 않음(미독)"** 으로 강등. 둘 중 하나. 무근거 단정 금지.
- 1차·2차·보조 필드(마스크/필터/정렬키) 임의 생략 금지(글로벌 §3).

### 전송 직전 self-check (절차)
draft 를 보내기 전 **`scripts/code_claim_lint.py`** 로 자기 draft 를 스캔 → 동작 주장인데 `file:line` 인용이 없는 문장을 surface → 각각 (a) 생산 함수 읽고 인용 추가 or (b) "확실치 않음" 강등.
```bash
python3 scripts/code_claim_lint.py <draft.md|->        # flagged 있으면 exit 1 (advisory)
```
heuristic 보조기(완전 탐지 아님) — flag 0 이 "검증 완료" 보증은 아니다. **flag 가 있으면 반드시 처리**, 없어도 핵심 주장은 육안 재검토.

## Layer 3 — cross-model 독립 검증 (고위험 옵트인, 본 파일럿 범위 밖)
correctness-critical 주장만: x-에이전트/Codex 에게 *유일 임무 = "그 값을 생산하는 함수를 직접 열어 읽고 주장을 반박하라"*. 다른 모델 = 다른 블라인드. 비용 때문에 결정적 주장에만. (files_origin 파일럿은 1·2층; 3층은 `/codex:adversarial-review` 명시 호출로.)

## 경계
advisory(stop-guard·hookify 하위). 적용 = `dev-discipline-trigger-policy.md` 의 code-analysis 트리거. 단순 질문·prose·번역엔 적용 0.
