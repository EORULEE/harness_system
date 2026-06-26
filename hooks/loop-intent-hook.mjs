#!/usr/bin/env node
/**
 * loop-intent-hook.mjs — UserPromptSubmit 훅 (Loop Control Plane 넛지). r3 후보.
 *
 * 목적: 사용자가 자연어로 **실행형 작업**(고쳐/구현/조사/다듬/비교/실험/배포/승격/디자인…)을
 *       요청하면, 바로 손대지 말고 harness-loop-engineering 으로 (1)작업유형·recipe 판단
 *       (2)계획 요약(8항목) (3)AskUserQuestion 승인 게이트 후 **기존 workflow 재사용** 실행하도록
 *       1줄 advisory(additionalContext)를 주입한다. **스킬 강제 X, hard block 없음.**
 * 설계: system-question-advisory.mjs 와 동형(정규식 게이트, 항상 exit 0).
 *   - advisory only — 강제·차단 아님. 최종권위 = stop-guard·hookify(advisory 하위).
 *   - **EXECVERB(실행 의도)가 1차 게이트** — 없으면 침묵. 단순질문·상태조회·개념질문은 EXECVERB 미매치라 자동 억제.
 *   - **중복 방지(dedup defer)**: 시스템상태 질문(SYSNOUN+QSIGNAL)→system-question-advisory 에 위임(침묵),
 *     "조사"→research-intent 에 위임(침묵). 같은 프롬프트에 두 훅이 동시 안내하지 않게 한다.
 *   - 순수 "왜~?/무슨 역할?" 질문은 비교/조사 단어가 있어도 억제(PURE_Q safety).
 * 출력: UserPromptSubmit 의 additionalContext (exit 0). 매치 없으면 무출력(주입 0).
 * 안전: 어떤 예외에도 exit 0 (절대 차단/에러 전파 안 함). stdout EPIPE 도 try 로 감싸 exit 0.
 */
import { readFileSync } from "node:fs";

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { process.exit(0); }

let prompt = "";
try {
  const j = JSON.parse(raw || "{}");
  const ev = j.hook_event_name || j.hookEventName || j.event;
  if (ev && ev !== "UserPromptSubmit") process.exit(0);  // EVENT FILTER
  prompt = j.prompt || j.user_prompt || j.message || "";
} catch { process.exit(0); }

if (!prompt || typeof prompt !== "string") process.exit(0);
const p = prompt.trim();
if (!p) process.exit(0);

// --- 1차 게이트: 실행 의도(EXECVERB) 가 있어야 발화 ---
// (없으면 침묵 → 단순질문·상태조회·개념질문·brevity 요청은 자동 억제. brevity/status 가 실행요청을
//  선점해 삼키던 버그 제거: EXECVERB 를 먼저 본다.)
const EXECVERB = new RegExp(
  "(고쳐|고쳐줘|수정해|수정\\s*좀|버그\\s*(잡|고)|디버그|구현해|구현\\s*좀|개발해|만들어\\s*줘|만들어줘|" +
  "추가해|리팩터|배포해|배포\\s*좀|조사해|조사\\s*좀|비교해\\s*줘|비교\\s*분석|실험\\s*(해|돌려|비교)|" +
  "학습\\s*(돌려|시켜)|다듬어|보고서\\s*(써|작성)|논문\\s*(써|작성)|제안서\\s*(써|작성)|" +
  "양식\\s*(맞춰|적용)|디자인\\s*(개선|바꿔|다듬)|승격|wiki\\s*에?\\s*올려|정본으로\\s*올려|" +
  // 그림 생성(visual-generation): 그림/개념도/인포그래픽/일러스트/모식도/선화/다이어그램/그래프/모션/슬라이드 배치
  "그림\\s*(그려|만들)|그려\\s*줘|그려줘|그려\\s*줄|그래프\\s*(그려|만들|그려줄|그려줘)|" +
  "개념도|인포그래픽|일러스트|모식도|선화|다이어그램|도식화|" +
  "hero\\s*image|발표\\s*슬라이드|슬라이드\\s*(로\\s*)?(구성|배치|만들)|" +
  "\\b(fix|implement|deploy|refactor|debug|build|migrate|polish|infographic|diagram|draw)\\b)", "i");
if (!EXECVERB.test(p)) process.exit(0);

// --- dedup defer 1: 시스템 상태 질문이면 system-question-advisory 에 위임(침묵) ---
const SYSNOUN = /(내\s*(시스템|하네스|설정)|이\s*(시스템|하네스)|\bharness\b|하네스|훅|hookify|스킬|플러그인|에이전트|\bMCP\b|instinct|인스팅트|settings|설정|배선|wired)/i;
const QSIGNAL = /(설치|있어|있나|있는지|되어\s*있|돼\s*있|됐(어|나|는지)?|된\s*거|활성|배선|등록|연결|동작|작동|목록|\blist\b|몇\s*개|확인|맞(아|나))/;
if (SYSNOUN.test(p) && QSIGNAL.test(p)) process.exit(0);

// --- dedup defer 2: 명시적 "조사해/조사 좀" 연구요청만 research-intent 에 위임(침묵). ---
// (단, 시각 요청 안의 명사 "조사 결과를 인포그래픽으로…" 는 over-suppress 하지 않음 → VISUAL 이면 발화)
const VISUAL = /(그림|개념도|인포그래픽|일러스트|모식도|선화|다이어그램|도식|그래프|차트|\bsvg\b|lottie|모션|슬라이드|hero\s*image|infographic|diagram)/i;
if (/조사\s*(해|좀|해줘)/.test(p) && !VISUAL.test(p)) process.exit(0);

// --- PURE_Q safety: 순수 "왜~?/무슨 역할?" 질문은 (비교/조사 단어가 있어도) 억제 ---
// 한글은 \b(word boundary)가 신뢰 불가 → "왜 " 자체를 질문 신호로. STRONG_MODIFY 가 실제 수정요청은 구제.
const PURE_Q = /(무슨\s*역할|뭐야|뭔지|뭔가요|어떤\s*역할|동작\s*(원리|방식)|설명만|왜\s)/;
// ⚠️ 명사(개념도·인포그래픽·일러스트)는 STRONG_MODIFY 에 넣지 않는다 — "개념도란 뭐야?" 같은
//    순수 질문이 명사 때문에 PURE_Q 억제를 우회해 오발화하던 버그 제거. 명시적 생성 동사만.
const STRONG_MODIFY = new RegExp(
  "(고쳐|수정|구현|개발|만들|추가|배포|다듬|승격|양식|디자인\\s*(개선|바꿔)|리팩터|" +
  "그려\\s*줘|그려줘|그려\\s*줄|" +
  "\\b(fix|implement|deploy|refactor|debug|build|migrate|polish)\\b)", "i");
if (PURE_Q.test(p) && !STRONG_MODIFY.test(p)) process.exit(0);

const directive =
  `\n[loop-control-plane · advisory] 이 요청은 실행형 작업일 수 있음 — 바로 손대지 말고 ` +
  `harness-loop-engineering 으로 (1) 작업유형·recipe 판단 (2) 계획 요약(8항목) ` +
  `(3) AskUserQuestion 승인 게이트 후 **기존 workflow(DEV/Research/Writing/Experiment/Mode C/Design/배포) 재사용** 실행할 것.\n` +
  `단순 질문·상태조회·개념질문은 즉답(계약 만들지 않음). DEV/조사/시스템 세부 넛지는 각 전용 훅에 위임(중복 안내 안 함).\n` +
  `적용 여부는 요청 성격 보고 네가 판단(강제 아님). 최종권위=stop-guard/hookify.\n`;

try {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: directive },
  }));
} catch { /* EPIPE 등 — 무시 */ }
process.exit(0);  // ALWAYS EXIT 0 (no hard block)
