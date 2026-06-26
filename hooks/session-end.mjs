#!/usr/bin/env node
/**
 * session-end.mjs — SessionEnd hook (경량 queue writer).
 * Memory Continuity v2: event metadata 를 continuity_queue 에 atomic 기록하고 즉시 종료.
 *  - transcript 분석 X, LLM X, 네트워크 X.
 *  - 저장 = metadata 만(session_id·transcript_path·cwd·timestamp·reason·schema_version).
 *  - 저장 금지 = cookie·API key·env 전체·transcript 사본·tool result·raw secret.
 *  - 어떤 예외에도 세션 종료를 막지 않음(항상 exit 0).
 *  ※ 이번 단계에서는 settings 에 등록하지 않음(파일만 생성).
 */
import { readFileSync, writeFileSync, mkdirSync, renameSync, readdirSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { homedir, hostname } from "node:os";

function readStdin() { try { return readFileSync(0, "utf8"); } catch { return ""; } }
function maskLight(s) {
  if (typeof s !== "string") return s;
  return s
    .replace(/AIza[0-9A-Za-z_\-]{20,}/g, "[REDACTED]")
    .replace(/sk-[A-Za-z0-9]{20,}/g, "[REDACTED]")
    .replace(/ghp_[A-Za-z0-9]{20,}/g, "[REDACTED]")
    .replace(/eyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{10,}/g, "[REDACTED]")
    .replace(/(Bearer|token|api[_-]?key|password)\s*[:=]\s*\S+/gi, "$1 [REDACTED]");
}

let j = {};
try { j = JSON.parse(readStdin() || "{}"); } catch {}
const ev = j.hook_event_name || j.hookEventName || j.event || "";
if (ev && ev !== "SessionEnd") process.exit(0); // 방어: 다른 이벤트면 무동작

const cwd = j.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
// machine-local home 기반 runtime(= python worker 와 동일 규칙). 공유 cwd/.claude/runtime 로 fallback 금지.
const sanitizeId = (p) => String(p).replace(/[^a-zA-Z0-9]/g, "-");
function runtimeDir(c) {
  if (process.env.CONTINUITY_RUNTIME_DIR) return process.env.CONTINUITY_RUNTIME_DIR;
  const home = homedir();
  if (!home) return null;   // home 해석 실패 → advisory(큐 미기록), shared fallback 금지
  return join(home, ".claude", "projects", sanitizeId(c), "runtime");
}
const runtime = runtimeDir(cwd);
if (!runtime) process.exit(0);   // no shared fallback
const qdir = join(runtime, "continuity_queue");
const machineId = createHash("sha256").update(String(hostname() || "")).digest("hex").slice(0, 12);

const event = {
  schema_version: "continuity_event/v2",
  project_id: sanitizeId(cwd),
  platform: process.platform,
  machine_id: machineId,
  event_type: "session_end",
  session_id: j.session_id || j.sessionId || null,
  transcript_path: j.transcript_path || j.transcriptPath || null,
  cwd,
  timestamp: new Date().toISOString(),
  reason: maskLight(String(j.reason || "session_end")).slice(0, 200),
};

// safe session hash (UUID 자체 노출 대신 해시 12자) — 파일명엔 hash+timestamp만
const sh = createHash("sha256").update(String(event.session_id || "nosession")).digest("hex").slice(0, 12);
try {
  mkdirSync(qdir, { recursive: true });
  // dedupe: 같은 session+event 의 pending 파일 제거(큐 무한 누적 방지)
  try {
    for (const f of readdirSync(qdir)) {
      if (f.endsWith(`-session_end-${sh}.json`)) { try { unlinkSync(join(qdir, f)); } catch {} }
    }
  } catch {}
  const base = `${event.timestamp.replace(/[:.]/g, "")}-session_end-${sh}.json`;
  const tmp = join(qdir, "." + base + ".tmp");
  writeFileSync(tmp, JSON.stringify(event));
  renameSync(tmp, join(qdir, base)); // atomic, 파일 1개
} catch { /* fail-silent: 세션 종료 차단 금지 */ }
process.exit(0);
