#!/usr/bin/env node
/**
 * pre-tool-vgate-tripwire.mjs — 좁은 destructive PreToolUse tripwire (v1.1 ADOPT 잔여 #7).
 *
 * 근거(설계 v1.1 §4-DEFER + ChatGPT 결함 #3): Stop 은 destructive effect 에 너무 늦다
 * (응답 완성 전에 이미 실행). PreToolUse deny/ask 는 bypassPermissions 에서도 적용(문서 TRUE).
 *
 * 정책: **좁은 known-destructive 패턴만** permissionDecision="ask" (hard block 아님 —
 *       사용자 확인 표면화). FP 회피가 우선: 의심스러우면 침묵(exit 0).
 *       single-use action receipt 는 DEFER(안정된 wrapper 생길 때) — 지금은 ask 만.
 * 완전 차단 아님을 명시: python -c unlink·base64 간접실행 등은 못 잡는다(정직 한계,
 *       설계 §6-10: 판독 불가 복합 명령의 "자동 승인"만 금지 — 여기선 매치 안 되면 기본
 *       권한흐름으로 넘어감). hookify 하드차단 규칙과 병행(중복 아님 — 대상 다름).
 */
import { readFileSync } from "node:fs";

function silent() { process.exit(0); }

let payload = {};
try { payload = JSON.parse(readFileSync(0, "utf8") || "{}"); } catch { silent(); }
if ((payload.tool_name || "") !== "Bash") silent();
const cmd = String((payload.tool_input || {}).command || "");
if (!cmd) silent();

// M14: rm 은 정규식 1개가 아니라 토큰 파싱(-r -f 분리형·--recursive/--force 장형 포괄).
function rmDestructive(segment) {
  const m = segment.match(/\brm\s+([^|;&]*)/);
  if (!m) return false;
  const toks = m[1].trim().split(/\s+/);
  let rec = false, force = false, absTarget = false;
  for (const t of toks) {
    if (t === "--recursive" || /^-[a-zA-Z]*[rR]/.test(t)) rec = true;
    if (t === "--force" || /^-[a-zA-Z]*f/.test(t)) force = true;
    if (/^\/(?!tmp\/|tmp$|dev\/shm)/.test(t)) absTarget = true;
  }
  return rec && force && absTarget;
}

// 좁은 destructive 표면(FP-회피 우선). 각 항목 = [판정함수 또는 정규식, 사유]
const RULES = [
  [(c) => rmDestructive(c), "절대경로 재귀 강제삭제(rm -rf/-r -f/--recursive --force /...)"],
  [(c) => { const m = c.match(/\bssh\s+\S+\s+(.*)$/s); return !!m && rmDestructive(m[1]); },
   "원격 재귀 강제삭제(ssh … rm)"],
  [/\bssh\s+\S+.*\b(systemctl\s+(restart|stop)|shutdown|reboot|mkfs)\b/,
   "원격 destructive(ssh … restart/shutdown/mkfs)"],
  [/\bgit\s+push\b.*(\s--force\b|\s-f\b)/, "force push"],
  [/\b(mkfs|shred)\b|\bdd\b.*\bof=\/dev\//, "디스크 파괴 계열(mkfs/shred/dd of=/dev)"],
  [/\bsystemctl\s+(stop|disable)\s+(?!.*--user)/, "시스템 서비스 정지/비활성"],
];

for (const [re, why] of RULES) {
  const hit = typeof re === "function" ? re(cmd) : re.test(cmd);
  if (hit) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason:
          `[vgate tripwire] ${why} 감지 — 사용자 확인 필요. ` +
          `(v1.1 report-only 단계: 차단 아님·확인 표면화만. 근거 없는 실행이면 취소 후 ` +
          `measure.py 실측 또는 decision_receipt.py 선언을 먼저.)`,
      },
    }));
    process.exit(0);
  }
}
silent();
