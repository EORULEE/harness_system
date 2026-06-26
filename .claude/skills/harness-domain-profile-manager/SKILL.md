---
name: harness-domain-profile-manager
description: "Writing Suite의 도메인 프로파일을 찾고 선택한다(reference only). _domain-profiles/ 의 프로파일을 스캔해 요청 도메인에 맞는 것을 고르고, 없으면 custom-template 기반 초안을 제안한다. 여러 프로파일 조합 지원. runtime/hook 아님 — 단순 참조 레이어. 명시 호출 전용."
disable-model-invocation: true
argument-hint: "<domain_profile name 또는 도메인 키워드>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-domain-profile-manager — 도메인 프로파일 선택 (reference only)

Writing Suite가 쓸 **도메인 프로파일**을 찾고 선택한다. 프로파일은 글쓰기 페르소나·용어·인용 규범의 **참조 데이터**일 뿐, 실행 코드도 hook도 아니다.

## ⚠️ 충돌 회피 (중요)
- 본 스킬은 `scripts/domain_detector.py`·`scripts/domain_templates.py`(**프로젝트 부트스트랩용** 도메인 탐지)와 **별개**다. 그것들을 호출·수정·대체하지 않는다.
- 본 스킬 = **Writing Suite 전용 프로파일 선택 reference 레이어**. 런타임 분류기 아님.

## 입력
- 도메인 이름(예: `remote-sensing`) 또는 도메인 키워드.

## 절차 (읽기 전용)
1. `.claude/skills/_domain-profiles/` 하위 디렉터리를 **Glob/Grep으로 스캔** → 존재하는 프로파일 목록.
2. 각 `domain.yaml`을 Read → `name`·`description` 확인(로딩 규약 = `_writing-core/profile-resolution-rules.md`).
3. 요청 도메인과 매칭:
   - **있으면**: 해당 프로파일(들) 선택. **여러 프로파일 조합** 가능(예: `remote-sensing` + `hydrology`) → 우선순위·병합 방식을 제안.
   - **없으면**: `_domain-profiles/custom-template/domain.yaml`을 본보기로 **새 프로파일 초안을 응답으로 제안**(필수 키 채운 yaml 텍스트). **자동 생성/적용하지 않는다** — 사용자가 검토 후 직접 추가.
4. 선택 결과를 **plan 형태로 출력**: 선택된 profile name(들) · 누락 시 초안 · 적용 대상 document_type.
   - 선택된 domain_profiles는 contract의 `domain_profiles` 필드로 전달된다(`_writing-core/writing-contract-schema.yaml`).

## 출력 (draft/plan only)
- 선택된 domain_profiles 목록(또는 "없음 → 초안 제안").
- custom-template 기반 신규 프로파일 **초안 텍스트**(필요 시).
- 다음 단계: `harness-writing-planner`에 전달할 domain_profiles.

## 규칙 (공통)
- 명시 호출 전용. **기존 파일 직접수정 금지**. 실제 Write/Edit 금지 — 출력은 draft/plan.
- 프로파일 부재 시 **자동 적용 금지**(초안 제안만, 사용자 승인).
- 모델 정책은 `_writing-core/model-policy.yaml` 참조(모델명 하드코딩 금지, role만).
- 수치·DOI·citation·저자·연도·metric·센서·데이터셋·표/그림 번호·수식 임의 변경 금지. 새 factual claim 생성 금지. secret 원문 출력 금지.
- 목적 = clarity·precision·technical integrity·reviewer readability.
- **AI 탐지 회피 목적 금지**: Do not use this skill to evade AI detection or disguise authorship. The purpose is clarity, precision, technical integrity, reviewer readability, and safe document preparation. (이 스킬은 AI 탐지 회피나 저자성 은폐를 위한 humanizer가 아니다.)
