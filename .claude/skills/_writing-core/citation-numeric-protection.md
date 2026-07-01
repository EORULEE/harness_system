# citation-numeric-protection.md — 인용·수치 보호 규칙

> writer/polish 단계에서 **인용과 수치가 변형·날조되지 않도록** 보호.

## 1. 수치 보호
- 사용자 제공 수치·표·통계는 **bit-identical 보존**. polish가 수치를 바꾸지 않는다.
- 모델이 생성한 수치는 전부 "[확인 필요]"(계산 근거 없으면 사용 금지).
- 반올림·단위 변환은 **명시적 요청 시에만**, 원값 병기.

## 2. 인용 보호
- 인용 키·저자·연도·DOI는 **라이브러리 실재 항목만**(Zotero MCP 검증, 글로벌 KB 정책).
- 'S23' 같은 내부 라벨 금지 → 실제 출처(DOI/URL/APA)로.
- 없는 인용 생성 금지 → "출처 미확보".

## 3. polish 시 불변식
- writing-polish/html-copy-polish는 **문체만** 손본다. 인용·수치·고유명사 불변.
- 변경 전후 인용/수치 **diff 0** 확인(자동 대조 권장).

## 4. 연결
- citation 검증은 [[zotero]]·[[obsidian]] KB 정책과 연계. 미검증은 보고.
