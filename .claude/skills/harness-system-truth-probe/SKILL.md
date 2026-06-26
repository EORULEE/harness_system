---
name: harness-system-truth-probe
description: "내 하네스/시스템의 설치·설정·동작에 대한 자연어 질문에 기억이 아니라 실제 source로 답한다. system_truth_index(Evidence Index) → Serena/Grep → 실제 source Read 순서로 확인하고, file:line 근거와 함께 답한다. source를 확인하지 못하면 Unverified로 답한다. '내 시스템/설치/스킬/훅/settings/실제 동작'류 질문에 사용. 읽기 전용·hard block 없음."
disable-model-invocation: false
argument-hint: "<시스템 상태 질문 — 예: 'X 스킬 설치돼 있어?', '어떤 훅이 배선됐어?', 'Y가 활성이야?'>"
allowed-tools:
  - Read
  - Grep
  - Glob
---

# harness-system-truth-probe — source-backed 시스템 답변

내 하네스/시스템의 **설치·설정·동작**에 대한 자연어 질문에 **기억이 아니라 실제 source로** 답한다.
SYS:probe 명령을 외울 필요 없이, 자연어 질문에 advisory hook이 이 스킬을 떠올리게 한다.

## 발화 범위 (이 스킬을 쓸 때)
- "X 스킬/훅/MCP 설치·등록·활성돼 있어?", "어떤 훅이 배선됐어?", "settings에 뭐가 있어?"
- "Y 기능 실제로 동작해?", "스킬 목록", "이 시스템 어떤 기능 있어?"
- 그 외 **시스템 상태·구성·동작** 사실 질문.
- ❌ 비대상: 글쓰기·조사·구현 요청, 일반 개념 질문(시스템 사실이 아닌 것).

## 절차 (읽기 전용, 우선순위 순)
1. **Evidence Index 먼저**: `Read .claude/runtime/system_truth_index.json` (system_truth_indexer.py 산출 — pointer/cache, SoT 아님).
   index가 질문을 커버하면 가리키는 source 경로를 얻는다. (없거나 stale면 2로.)
2. **Grep 탐색(필수 경로)**: `Grep` 도구로 심볼·문자열을
   `scripts/ hooks/ .claude/settings.local.json .claude/skills/ ~/.claude/settings.json ~/.claude/skills/` 에서 찾는다.
   (심볼 단위가 필요하고 **serena MCP가 세션에 노출돼 있으면** 보조로 `find_symbol` 등을 쓸 수 있으나, 본 스킬의 보장 경로는 Grep/Read 뿐 — allowed-tools 정합.)
3. **실제 source Read**: 후보 파일을 `Read` 로 열어 **그 줄을 직접 확인**한다(설치=파일 존재, 등록=settings/MCP 라인, 활성=배선/플래그, 동작=코드 경로).
4. **답변 = 원문 근거 먼저, 해석 나중**: `file:line` 인용 + 관찰값 원문 → 결론.

## 판정 규칙
- **단정은 확인된 것만**: source를 직접 본 사실만 단정한다.
- **Unverified**: source를 찾지/확인하지 못하면 결론을 단정하지 말고 **"Unverified — <무엇을 못 봤는지>"** 로 답한다.
- **설치 ≠ 활성 ≠ 동작 구분**: 파일 존재(설치)·settings/MCP 등록·훅 배선(활성)·코드 실행경로(동작)를 분리해 표기.
- **기억 금지**: memory/이 SKILL 텍스트/과거 대화로 confident 단정하지 않는다(관련 정본 `feedback_source_verify_before_claim`).

## 감사 연계 (SYS:audit)
- 시스템 답변의 주장-근거 정합 **감사가 필요하면** 별도 신설 스킬 없이 **`harness-claim-evidence-audit`** 를 재사용한다
  (claim 추출 → 근거유형 태깅 → 일치 검증 → risk level, audit-only). 본 스킬은 probe(답변), claim-evidence-audit는 audit(검증).

## 안전
- **읽기 전용**(Read/Grep/Glob만). 파일 수정·생성 없음. **hard block 없음**(advisory).
- secret 원문 출력 금지(presence만). index는 SoT 아님 — 충돌 시 실제 source 우선.
