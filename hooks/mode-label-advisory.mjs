#!/usr/bin/env node
/**
 * mode-label-advisory.mjs — UserPromptSubmit 훅 (명시 모드 라벨 감지 넛지).
 *
 * 목적: 사용자가 메시지 맨 앞에 `A0:`/`A1:`/`B:`/`C:` 접두를 붙이면, 그 모드의
 *       의무(특히 A1 = 2-pass, c측 + Codex x측 교차)를 advisory(additionalContext)로
 *       주입해 모델이 자가분류·기억에 의존하지 않고 그 모드 규율을 지키게 한다.
 * 설계: system-question-advisory.mjs 와 동형(정규식 게이트, 항상 exit 0, advisory only).
 *       - **강제·차단 아님**. 최종권위 = stop-guard·hookify(advisory 하위).
 *       - 접두 라벨이 **없으면 침묵**(기존 자동분류 그대로 병행 — 이 훅은 명시 라벨만 처리).
 *       - 대소문자 무시. 한국어 콜론(：)도 허용. 메시지 맨 앞(트림 후)만 인정.
 * 출력: UserPromptSubmit 의 additionalContext (exit 0). 매치 없으면 무출력.
 * 안전: 어떤 예외에도 exit 0 (절대 차단/에러 전파 안 함). hard block 없음.
 */
import { readFileSync } from "node:fs";

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { process.exit(0); }

let prompt = "";
try {
  const j = JSON.parse(raw || "{}");
  const ev = j.hook_event_name || j.hookEventName || j.event;
  if (ev && ev !== "UserPromptSubmit") process.exit(0);
  prompt = j.prompt || j.user_prompt || j.message || "";
} catch { process.exit(0); }

if (!prompt || typeof prompt !== "string") process.exit(0);
const p = prompt.trim();

// --- 맨 앞 라벨 감지: A0/A1/B/C + (: 또는 ：) ---
//   예: "A1: 이 데이터 분석해줘", "b: 이거 구현", "C：실험 돌려".
//   markdown 굵게(**A1:**)·인용(> A1:)도 관대하게: 앞의 비문자 몇 개는 허용.
const m = p.match(/^\s*[>*_`\-\s]{0,4}(A0|A1|B|C)\s*[:：]/i);
if (!m) {
  // --- 라벨 없음 → 폴백: 도메인 판정·디버깅 '고신호' 만 보수적으로 A1 리마인드(과발화 방지) ---
  //   흔한 단어(분석·검증 단독)는 제외. 결론/방법론/반례/근본원인/아티팩트 판정 같은 순간만.
  const SUPPRESS = /(다듬|polish|번역|translate|문장만|요약|summar|초안|글\s*써|보고서\s*작성|고마|thank|^\s*(응|네|ok|오케이|그래|좋아|알겠))/i;
  const JUDGE = /(아티팩트|artifact|반례|counter-?example|근본\s*원인|root\s*cause|디버깅|방법론|methodolog|정합성|오판|이상\s*(판정|여부|원인)|왜\s*(이런|안\s|틀|그런|안돼|안되))/i;
  if (!SUPPRESS.test(p) && JUDGE.test(p)) {
    const soft =
      `\n[mode-label · advisory] 이 요청은 도메인 판정·디버깅 = A1(2-pass 대상)일 수 있음 — ` +
      `**단독 결론 금지 방향**: 🔵 c측 + 🟢 x측을 **에이전트로 병행 분기**(이 프로젝트 x측이 Codex면 \`codex:adversarial-review\`)해 교차. ` +
      `명시하려면 맨 앞에 \`A1:\`. 강제 아님·최종권위=stop-guard/hookify.\n`;
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: soft },
    }));
  }
  process.exit(0);
}
const label = m[1].toUpperCase();

const MODES = {
  A0:
    `\n[mode A0 · advisory] 가벼운 조회/설명 — 1-pass 허용. 과한 게이트·2-pass 강제 금지. ` +
    `단순 상태조회·개념설명에 한함(새 설계·리스크 판단·디버깅이면 A1로 처리).\n`,
  A1:
    `\n[mode A1 · advisory] 분석·판단·설계·디버깅·문서검토 = **2-pass 의무 + 에이전트 병행 분기가 기본**(단독 답변은 예외). ` +
    `🔵 c측(constructive) + 🟢 x측(반례·약점 탐색)을 **서브에이전트로 병행 스폰** — 이 프로젝트 x측이 Codex면 ` +
    `\`codex:adversarial-review\`/\`codex:review\`, Claude c-/x- 페어면 Task 병행 분기. 다도메인이면 관련 페어 여러 개(예: 4페어). ` +
    `**결론/판정을 내리기 전에 반례부터 탐색**(특히 도메인 물리·모델 방법론·데이터 아티팩트 판정). ` +
    `페어 없으면 read-only 검증 에이전트(Explore) 1개라도 교차. 최소 2회 수렴(1회 종결은 3조건 충족 시만).\n`,
  B:
    `\n[mode B · advisory] 구현 3단계 체인 — **각 단계에 에이전트 교차를 기본 적용**(사소한 기계편집만 예외): ` +
    `① 진행 전 **명세 게이트(deep-interview) 또는 '바로 진행' 1줄 확인** — 나온 수용기준은 **x측 에이전트로 적대 챌린지 권장** ` +
    `② 구현은 **DEV 규율**: TDD(실패테스트→최소구현→green)·systematic-debugging(증상→재현→근본원인). 구현 후 **코드 리뷰를 x측 에이전트/Codex(\`codex:review\`)로 교차 권장** ` +
    `③ 완료 주장은 fresh evidence 1개=주장 1개(**Ralph**) + **read-only verifier 에이전트(Explore)로 독립 재확인 권장**. 승인 전 커밋·배포 금지.\n`,
  C:
    `\n[mode C · advisory] 자율 실험 루프 — \`.claude/cycle.<proj>.yaml\` 인프라 필요(없으면 미적용 → A1/B로 처리). ` +
    `배치 경계 사람 승인 게이트 + 기계 가드레일(예산·kill·divergence·유의성). **경계 판단(아이디어 생성·config 설계·plateau 재제안·최종 synthesis)은 c-/x- 에이전트 2-pass 기본**(기계 내부 루프만 면제). 코인·실거래 hard-refuse.\n`,
};

const directive = MODES[label] +
  `적용 여부는 요청 성격 보고 네가 판단(강제 아님). 최종권위=stop-guard/hookify.\n`;

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: directive },
}));
process.exit(0);
