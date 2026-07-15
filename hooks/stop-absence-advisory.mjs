#!/usr/bin/env node
/**
 * stop-absence-advisory.mjs — Stop 훅(absence_claim_guard report-only 어드바이저리).
 *
 * 역할: 최종 응답 텍스트를 transcript tail 에서 추출 → absence_claim_guard.py --mode report 에 전달.
 *       부재/위치/상태과장/release 단정의 전제 evidence(tool-use.jsonl)를 대조해 would_block "기록만".
 * 안전(핵심):
 *   - **항상 exit 0**(advisory). 기존 stop.mjs 의 stop-guard(guardStatus)·Ralph 경계가 exit code 최종 권위.
 *     이 훅은 절대 차단하지 않으며 guardStatus 를 덮어쓰지 않는다(별도 Stop 항목, exit0).
 *   - 어떤 예외에도 exit 0(턴 wedge 금지). transcript 내용은 저장하지 않음(detector report 는 _redact 적용).
 *   - report-only 기본. soft/hard 전환은 별도 승인(여기서 모드 안 올림).
 */
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

function done() { process.exit(0); }

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { done(); }

let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch { done(); }

const tpath = payload.transcript_path || payload.transcriptPath;
if (!tpath) done();

// transcript tail 에서 마지막 assistant 텍스트 추출(내용 저장 안 함, 메모리 일시 사용만)
let text = "";
try {
  const buf = readFileSync(tpath, "utf8");
  const lines = buf.split("\n").filter(Boolean);
  for (let i = lines.length - 1; i >= 0 && !text; i--) {
    let rec;
    try { rec = JSON.parse(lines[i]); } catch { continue; }
    const msg = rec.message || rec;
    const role = msg.role || rec.role || rec.type;
    if (role !== "assistant") continue;
    const c = msg.content;
    if (typeof c === "string") text = c;
    else if (Array.isArray(c)) text = c.filter(b => b && b.type === "text").map(b => b.text).join("\n");
  }
} catch { done(); }

if (!text || text.length < 4) done();

// absence_claim_guard.py --mode report (항상 exit0; stderr 어드바이저리만)
// 2026-07-10 fix(계약 smoke_absence_hook_contract.sh): `--since-current` 인자 제거.
//   근거: guard argparse 는 이 인자를 지원한 적 없음(r14~r17 전 아카이브 argparse 0건)
//   → r15 탄생부터 argparse 오류+fail-open 으로 훅 경로 0회 작동(silent).
//   guard 는 --turn 미지정 시 내부에서 tool_use_audit query --since-current 를 이미 수행
//   (absence_claim_guard.py:116, tool_use_audit.py:169,200) = 현재 세션 evidence window 의미 등가.
//   따라서 인자 제거는 no-op 호환이 아니라 의미 보존 최소 수정.
try {
  const here = dirname(fileURLToPath(import.meta.url));
  const guard = join(here, "..", "scripts", "absence_claim_guard.py");
  const py = process.env.PYTHON || "python3";
  const r = spawnSync(py, [guard, "--mode", "report"], {
    input: text, timeout: 8000, encoding: "utf8", stdio: ["pipe", "ignore", "pipe"],
  });
  // r19 codex MINOR#3: silent fail-open 재발 방지 — guard 가 비정상 종료(argparse 등)면
  //   exit0(advisory) 는 유지하되 stderr 로 1줄 경고해 "조용한 무작동"을 가시화한다.
  if (r.error || (typeof r.status === "number" && r.status !== 0)) {
    const why = r.error ? String(r.error.message || r.error) : `exit ${r.status}`;
    process.stderr.write(`[stop-absence-advisory] guard 비정상 종료(${why}) — report 미기록 가능(advisory·차단 아님)\n`);
    if (r.stderr) process.stderr.write(String(r.stderr).split("\n").slice(0, 3).join("\n") + "\n");
  }
} catch { /* advisory — 무시 */ }

done();
