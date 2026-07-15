#!/usr/bin/env node
/**
 * salience-packet.mjs — UserPromptSubmit 훅(카테고리별 짧은 salience packet).
 *
 * 목적: 위치/존재/배포/Design/시스템상태/세션 질문에만, 전체 규율 재주입 없이
 *       **카테고리별 5~8줄 packet** 만 주입해 "단정 전 도구로 확인 + 과장 금지"를 환기.
 * 설계: system-question-advisory.mjs 와 동형(조건부 additionalContext, exit 0, hard block 없음).
 *       우선순위 1매치(다중 주입 방지). 글쓰기·조사·구현 요청은 억제(과주입 방지).
 * 안전: 매치 없으면 무출력. 어떤 예외도 exit 0. 전체 CLAUDE.md 재주입 절대 안 함.
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

// 억제: 글쓰기·조사·구현/수정 → 0 (다른 intent 훅 소관, 과주입 방지)
const SUPPRESS = /(다듬|polish|번역|문장만|문체|요약|초안|글\s*써|보고서\s*작성|논문\s*작성|조사해|research|만들어|구현|개발|리팩터|refactor)/i;
if (SUPPRESS.test(p)) process.exit(0);

// 카테고리(우선순위 순 — 첫 매치만 주입)
// 우선순위: system_state 가 file_missing 보다 앞(시스템 질문에도 "있어/설치돼" 가 흔해 오분류 방지).
const CAT = [
  ["claude_design", /claude\s*design|디자인\s*(프로젝트|동기화|상태)|\bpublished\b|게시(됐|됨|돼|여부)?|design.*(sync|upload|동기|배포)/i],
  ["deployment",    /배포|deploy|\brelease\b|릴리스|manifest|\bACTIVE\b|static[-_ ]?pass|승격|promote|live[-_ ]?pass|롤아웃|\bregistered\b|\bauthenticated\b/i],
  ["system_state",  /내\s*시스템|하네스|\bharness\b|스킬|훅|\bhook\b|settings|설정|배선|wired|hookify|instinct|\bMCP\b|(설치|등록|활성|배선|동작|작동)\s*(돼|됐|됨|되어|되었|여부|안)/i],
  ["file_missing",  /어디(에|\s*있|야)|위치|경로|\bpath\b|존재(해|하나|하는지)?|있(어|나|는지)|없(어|나|는지|다|음)|찾아|찾을\s*수|missing|어느\s*(폴더|파일)/i],
  ["session",       /세션|\bsession\b|이전\s*(대화|작업|세션)|지난\s*(세션|작업)/i],
];

let cat = null;
for (const [name, re] of CAT) { if (re.test(p)) { cat = name; break; } }
if (!cat) process.exit(0);

const PACKETS = {
  system_state:
    "\n[salience · system] 시스템 상태(설치·배선·동작) 질문일 수 있음 — 기억 말고 source 로:\n" +
    " · 순서: system_truth_index → Serena/Grep → 실제 파일 Read, file:line 인용\n" +
    " · 설치 ≠ 활성 ≠ 동작 구분 / 확인 못 하면 Unverified\n" +
    " · harness-system-truth-probe 절차 사용\n" +
    " · 전체 규율 재주입 아님 · 강제 아님 · advisory.\n",
  file_missing:
    "\n[salience · 위치/존재] 파일·경로·존재 질문일 수 있음 — 단정 전 도구로 확인:\n" +
    " · 경로/cwd/HOME = pwd / ls / realpath 로 실측(추측 금지)\n" +
    " · 존재/부재 = Read/Grep/Glob 후 '있음/없음' (못 하면 Unverified)\n" +
    " · '없다/찾지 못함'은 검색 범위 명시 + 증거와 함께\n" +
    " · 전체 규율 재주입 아님 · 강제 아님 · advisory.\n",
  deployment:
    "\n[salience · 배포] release·배포 상태 질문일 수 있음 — 과장 금지(증거 필요):\n" +
    " · 포함 여부 = manifest / 파일목록 실제 확인 후\n" +
    " · static-pass ≠ ACTIVE · session_log ≠ live-pass · registered ≠ authenticated\n" +
    " · ledger verdict 실측 인용 후 상태 단정\n" +
    " · 전체 규율 재주입 아님 · 강제 아님 · advisory.\n",
  claude_design:
    "\n[salience · Design] Claude Design 상태 질문일 수 있음 — 과장 금지:\n" +
    " · uploaded ≠ Published — 실제 Published 여부 확인 후 단정\n" +
    " · sync 됨 ≠ 게시됨\n" +
    " · MCP/대시보드로 실제 상태 조회 후 답 / 못 하면 Unverified\n" +
    " · 전체 규율 재주입 아님 · 강제 아님 · advisory.\n",
  session:
    "\n[salience · 세션] 이전 세션·작업 찾기 질문일 수 있음 — 실제 조회:\n" +
    " · ~/.claude/projects/<경로슬러그>/ 실제 디렉토리 조회(해시 아님=경로 기반)\n" +
    " · 기억으로 '있었다/없었다' 단정 말고 파일 확인 후\n" +
    " · 확인 못 하면 Unverified\n" +
    " · 전체 규율 재주입 아님 · 강제 아님 · advisory.\n",
};

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: PACKETS[cat] },
}));
process.exit(0);
