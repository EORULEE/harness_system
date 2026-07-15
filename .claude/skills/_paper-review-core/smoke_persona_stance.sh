#!/bin/bash
# smoke_persona_stance.sh — persona stance × doc_type 불변식 golden 가드 (2026-07-14)
# persona 조합은 문서 기반(persona_resolve.py 없음)이라, 회귀 방지 = 문서 불변식 존재 검사.
# 검사: (A) paper 무회귀 선언 (B) doc_type=patent→patent-review 매핑 (C) patent-review 자기옹호 금지
#       (D) patent-assist 발명자 재정의 (E) golden 예시 C(patent) (F) 8역할 등록
DIR="$(cd "$(dirname "$0")" && pwd)"
PC="$DIR/persona-composition.md"; PY="$DIR/personas.yaml"
P=0; F=0
chk(){ if grep -qF "$2" "$1"; then echo "  PASS $3"; P=$((P+1)); else echo "  FAIL $3"; F=$((F+1)); fi; }

echo "=== persona stance × doc_type golden ==="
chk "$PC" "paper 무회귀(불변 보장)"                  "A paper 무회귀 선언"
chk "$PC" "이 변경 이전과 100% 동일" "A2 paper 100% 동일 명시"
chk "$PC" "doc_type=patent → \`personas.yaml/patent-review\`" "B patent→patent-review 매핑"
chk "$PC" "doc_type≠paper"                           "B2 비-paper 분기 규칙"
chk "$PY" "patent-review:"                            "C patent-review 페르소나 존재"
chk "$PY" "자기옹호 금지"                             "C2 patent-review 자기옹호 금지"
chk "$PY" "발명자(기술책임자)로서 자기 발명"          "D patent-assist 발명자 재정의"
chk "$PC" "예시 C — doc_type=patent"                 "E golden 예시 C(patent)"
chk "$PY" "techdoc-review:"                          "H techdoc-review 페르소나 존재"
chk "$PC" "algorithm-doc, product-spec, user-manual, protocol-spec} → \`personas.yaml/techdoc-review\`" "H2 코드문서→techdoc-review 매핑"
chk "$PC" "예시 D — doc_type=algorithm-doc"          "H3 golden 예시 D(techdoc)"
# paper stance 불변(저널 수석 편집위원 그대로여야)
chk "$PY" "상위 SCIE 저널 수석 편집위원"             "F paper self-review 저널편집위원 stance 불변"
chk "$PY" "9역할" "G 9역할 헤더"

echo "=== 결과: PASS=$P FAIL=$F ==="
[ "$F" -eq 0 ] && exit 0 || exit 1
