# profile-resolution-rules.md — 프로파일 로딩 규약 (AC23)

> domain/format 프로파일이 **"디렉터리에 추가만 하면 인식"(skill 코드 변경 0, AC3·AC4)**
> 되도록 하는 단일 로딩 **규약**. 본 문서는 규약(spec)만 정의한다.
> **로더 구현은 Phase B**(`harness-domain-profile-manager` skill)에서, 본 규약을 따른다.
> Phase A는 규약 문서 + 템플릿까지만(로더 스크립트 미생성 — 승인 범위 외).

## 1. 디렉터리 레이아웃 (고정 규약)
```
.claude/skills/_domain-profiles/<domain-name>/domain.yaml
.claude/skills/_format-profiles/hwp/<format-name>/format.yaml
.claude/skills/_format-profiles/docx/<format-name>/format.yaml
```
- `<...-name>` = 프로파일 식별자(kebab-case). `custom-template`은 복사용 본보기.

## 2. domain.yaml 필수 키
`name` · `description` · `persona_seed` · `terminology`(list) · `citation_norms` · `audience_default`.

## 3. format.yaml 필수 키
`name` · `family`(hwp|docx) · `engine`(hwp: hancom-com | docx: python-docx|hancom-com) ·
`reference_template`(경로 or "") · `notes`.

## 4. 로딩 절차 (Phase B 로더가 구현할 규약)
1. 해당 디렉터리를 **스캔**(하위 디렉터리 = 프로파일 후보).
2. 각 후보의 yaml 로드 → **필수 키 검증**.
3. **fail-loud(AC25)**: 깨진 yaml·필수 키 누락 → **명확한 에러로 보고**, silent-skip 금지.
4. 유효 프로파일 목록 반환. skill은 이름으로 **선택만** 한다(코드 변경 0).

## 5. 코드 변경 0 보장 (AC3·AC4)
- 새 도메인/양식 = **새 디렉터리 + yaml 1개 추가**. skill·로더 코드 **무수정**.
- smoke(Phase C)가 더미 프로파일 추가→인식, 깨진 yaml→fail-loud 둘 다 검증
  (로더가 Phase B에서 생성된 뒤).

## 6. 도구 정책
- 로더는 **오프라인·결정적**(실제 모델 호출·네트워크·원본수정 없음, AC20).
- 프로파일 추가 시 grep anchor: 디렉터리 존재 + 필수 키 존재로 인식(line number 비의존).
