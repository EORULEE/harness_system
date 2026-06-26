#!/usr/bin/env node
/**
 * system-question-advisory.mjs — UserPromptSubmit 훅 (system-truth 넛지).
 *
 * 목적: 사용자가 자연어로 "내 시스템/설치/스킬/훅/settings/실제 동작" 을 물으면,
 *       기억으로 답하지 말고 실제 source 로 확인하도록 1줄 advisory(additionalContext)를
 *       주입해 harness-system-truth-probe 스킬을 떠올리게 한다. **스킬 강제 X**.
 * 설계: dev-intent-hook.mjs / research-intent-hook.mjs 와 동형. 최종권위 = stop-guard·hookify(advisory 하위).
 *       글쓰기·조사·구현/수정 요청·"간단히/빠르게" 는 억제(과발화 방지).
 * 출력: UserPromptSubmit 의 additionalContext (exit 0). 매치 없으면 무출력(주입 0).
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

// --- 억제(non-trigger): 글쓰기·조사·구현/수정 → 넛지 0 ---
//   구현/수정 동사는 dev-intent-hook 소관(상태 질문 아님). 조사는 research-intent-hook 소관.
//   '간단히/빠르게'는 억제 안 함(시스템 질문은 간단히 요청해도 source-backed 로 답해야 — codex review fix).
const SUPPRESS = /(다듬|polish|번역|translate|문장만|문체|요약|summar|초안|글\s*써|보고서\s*작성|논문\s*작성|조사(해|해줘|좀)|research|만들어|구현|개발|추가해|작성해\s*줘|배포해|고쳐|수정해|리팩터|refactor)/i;
if (SUPPRESS.test(p)) process.exit(0);

// --- 시스템 명사(SYSNOUN) + 상태/설명 신호(QSIGNAL) 둘 다 있어야 발화(보수적) ---
//   codex review fix: bare 영어 hook/plugin/skill/agent 제거(프로그래밍 'React hook' 등 오발화).
//   harness 특정어(harness·MCP·hookify·instinct)와 한국어 시스템어만 유지.
const SYSNOUN = /(내\s*(시스템|하네스|설정)|이\s*(시스템|하네스)|\bharness\b|하네스|훅|hookify|스킬|플러그인|에이전트|\bMCP\b|instinct|인스팅트|settings|설정|배선|wired)/i;
//   codex review fix: 개념질문 신호('뭐야/무엇/어떻게/?') 제거 → 상태(설치·배선·등록·활성·동작)·설명·목록만.
const QSIGNAL = /(설치|있어|있나|있는지|되어\s*있|돼\s*있|됐(어|나|는지)?|된\s*거|활성|배선|등록|연결|동작|작동|목록|\blist\b|몇\s*개|확인|맞(아|나)|설명|알려|보여|어떤\s*(스킬|훅|기능|기능들|MCP|설정|플러그인|에이전트|훅들))/;
if (!(SYSNOUN.test(p) && QSIGNAL.test(p))) process.exit(0);

const directive =
  `\n[system-truth nudge · advisory] 이 질문은 내 시스템 상태(설치·설정·동작) 질문일 수 있음 — 기억으로 답하지 말고 ` +
  `harness-system-truth-probe 절차로 답할 것: system_truth_index → Serena/Grep → 실제 source Read, file:line 근거 인용. ` +
  `확인 못 하면 Unverified. 설치≠활성≠동작 구분.\n` +
  `적용 여부는 질문 성격 보고 네가 판단(강제 아님). 최종권위=stop-guard/hookify.\n`;

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: directive },
}));
process.exit(0);
