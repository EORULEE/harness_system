#!/usr/bin/env node
/**
 * stop-vgate-orchestrator.mjs — v1.1 단일 Stop orchestrator 진입점 (report-only).
 *
 * 역할: stdin 훅 payload 를 그대로 scripts/vgate_orchestrator.py 에 전달.
 *       모든 detector/baseline/audit 로직은 python 한 프로세스에서 순차 평가
 *       (훅 병렬성 문서 사실 → 체인 순서 가정 폐기, 설계 v1.1 §3-5).
 * 모드: python 이 .claude/runtime/vgate/mode.txt 로 판정.
 *       - report: python 이 항상 0 반환 → 이 훅도 0.
 *       - hard  : would_block 시 python exit 2 + stderr 해소지시 → **exit 2 relay**
 *                 (사용자 승인 2026-07-15 "지금 바로 켜기". 연속 8회 cap 은 Claude Code 상위 강제).
 * 안전: python crash/timeout/부재 등 인프라 오류는 **fail-open(exit 0)** — 차단은
 *       python 이 명시적으로 2 를 반환한 경우만(오류≠위반).
 * 기존 stop.mjs(stop-guard)·stop-absence-advisory·stop-verification-gate 와 독립 병렬
 * (기존 훅 무수정 — r54 sealed 자산 보존).
 */
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

function done() { process.exit(0); }

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { done(); }

const root = process.env.CLAUDE_PROJECT_DIR || join(dirname(fileURLToPath(import.meta.url)), "..");
const py = join(root, "scripts", "vgate_orchestrator.py");

try {
  const r = spawnSync("python3", [py], { input: raw, timeout: 8000, encoding: "utf8" });
  if (r.status === 2) {
    if (r.stderr) process.stderr.write(r.stderr);
    process.exit(2);
  }
} catch { /* fail-open */ }
done();
