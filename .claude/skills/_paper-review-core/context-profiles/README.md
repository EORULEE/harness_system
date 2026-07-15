# context-profiles/ — 문서유형과 직교하는 맥락·권위 오버레이 (T1 스캐폴드, 2026-07-10)

> 계약: `_output/contracts/contract-review-t1-typeagnostic-20260710.md` (AC-C1~C5).
> **스캐폴드·스키마·패턴만** — 실 비-paper overlay 파일(RFP·법규)은 **T2**(해당 유형 실문서 도착 시 생성).
> 코드 0: 런타임 로더 없음. 리뷰(프롬프트 구동)가 이 규약을 텍스트로 읽어 적용.

## 왜 필요한가 (문서유형과 직교)
`doc-type-profiles/<type>` = **문서가 본질적으로 무엇인가**(목적·독자·평가축). 그러나 같은 유형도 맥락에 따라
적용 규범·판정이 다르다 — 이 **직교 정보**를 context overlay 로 분리한다(유형×맥락 조합 폭발 방지):

| doc_type | context/authority overlay 예 |
|---|---|
| paper | 저널·학회·분야 (→ **`journal-profiles.yaml` = 이 패턴의 첫 실 인스턴스**) |
| patent | 관할/절차(US·EP·KR·PCT), 출원 단계(pre_filing/examination/amendment), 특허 종류(utility/design) |
| proposal | 공고문·RFP·평가표 |
| slide | 발표 목적·청중·시간·전달 방식(라이브/비동기/인쇄) |
| report | 과업지시서, 규제 기준, 보고서 하위유형(상태/감사/평가) |

## 오버레이 우선순위 (review-rubric "오버레이 우선순위 (B)" 와 동일)
doc_type 해소(persona-composition 3-b: 명시>추론>generic) 후, rubric 병합 4층:
`명시 외부기준·요구사항 > context/authority overlay > 문서유형 기본 프로필 > 공통 코어`.
→ context overlay(명시 시)는 문서유형 기본 프로필보다 **우선**(예: RFP 평가표가 proposal 기본축을 덮음).

## 스키마 (context_profile — journal_profile 과 같은 패턴, 필드는 상이)
```yaml
schema: context_profile
version: 1
doc_type: <paper|patent|proposal|slide|report>   # 어느 유형의 맥락인가
authority: <US|EP|KR|저널KEY|발주기관|...>        # 권위/맥락 식별자
# ── 법규·표준 overlay 메타(있을 때) ──
effective_as_of: 2026-04-01        # 이 규범이 유효한 기준일
last_verified: 2026-07-10          # 사람이 마지막 확인한 날
legal_basis: []                    # 예: [EPC_Art_83, EPC_Art_84] — 근거 조항(external_rule 증거의 normative_basis 원천)
# ── 심사 오버레이 ──
verdict_vocab: []                  # 이 맥락의 판정 어휘(미지정 시 rubric 기본: paper=accept류 / 비-paper=ready류)
weights: {}                        # 축별 가중(미지정 = 균등)
required_inputs: []                # 이 맥락 평가에 필요한 입력(부재 시 해당 축 = not_assessed_missing_input)
language: follow_document
notes: >
  맥락별 관행·주의. 법률 결론이 아니라 "잠재 요건 충돌 — 전문가(변리사 등) 검토 필요"로 출력하는 안전장치 유지.
```

## 하위호환 (paper journal — 무변경)
`journal-profiles.yaml`(schema: journal_profile) = **이 패턴(문서유형 직교 오버레이)의 첫 실 인스턴스**. paper 경로 무변경·무회귀.
journal_profile 과 context_profile 은 **같은 역할·패턴**(맥락별 가중·언어·판정 오버레이)이나 **필드가 다르다** — journal_profile 은 journal 고유 필드(reference_style·abstract_word_limit)를 갖고, context_profile 의 법규 필드(authority·legal_basis 등)는 갖지 않는다. **엄밀한 is-a/포함관계 아님**(동일 스키마로 통합하지 않음, T1 범위 밖).
paper 리뷰는 계속 `journal-profiles.yaml` 을 쓴다(이 디렉토리로 이관하지 않음).

## external_rule 증거와의 연결
finding 의 `evidence.type=external_rule` 은 `normative_basis`(출처)를 갖는다(review-rubric "증거 규칙").
- context overlay 가 있으면 → `normative_basis` 가 그 `legal_basis`/`authority`/`version` 을 참조.
- **없어도** → `normative_basis` 를 문자열(예: "RFP 평가항목 4.2")로 직접 기재해 **독립 동작**(T1 스캐폴드 미완성이어도 리뷰 가능).

## T2 (실파일 도착 시)
실제 patent(US/EP/KR)·proposal(RFP)·slide(발표맥락) 문서를 리뷰할 때, 그 유형의 `doc-type-profiles/<type>/profile.yaml`
와 함께 이 디렉토리에 `<doc_type>-<authority>.yaml` 실 overlay 를 유형별 deep-interview 로 생성한다(법요건·발표맥락은 비자명).
