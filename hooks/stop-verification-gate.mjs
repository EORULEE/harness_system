#!/usr/bin/env node
/**
 * stop-verification-gate.mjs — Stop 훅(verification_gate v2 report-only 어드바이저리·canary).
 *
 * 역할: 최종 응답 + 직전 사용자 입력 + 이번 턴 tool 증거를 verification_gate.py 에 넘겨,
 *       claim-class 별 would_block(범위충족 미달·입력지시어 삭제·능력 얕은확인 등)을 **기록만** 한다.
 * 안전(핵심):
 *   - **항상 exit 0**(report-only canary). 절대 차단 안 함. 기존 stop.mjs(stop-guard exit2)·
 *     stop-absence-advisory 와 독립 병렬. exit code 안 덮어씀.
 *   - 어떤 예외에도 exit 0(턴 wedge 금지). 응답/입력 원문 저장 안 함(findings 요약만).
 *   - hard 승격은 별도 단계(FP=0 canary 확인 + 승인 후 이 파일에서 exit code 존중으로 전환).
 */
import { readFileSync, appendFileSync, mkdirSync } from "node:fs";
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

// transcript tail 에서 마지막 assistant 텍스트 + 마지막 user 텍스트 추출(내용 미저장)
let outText = "", userText = "";
try {
  const lines = readFileSync(tpath, "utf8").split("\n").filter(Boolean);
  for (let i = lines.length - 1; i >= 0 && (!outText || !userText); i--) {
    let rec; try { rec = JSON.parse(lines[i]); } catch { continue; }
    const msg = rec.message || rec;
    const role = msg.role || rec.role || rec.type;
    const c = msg.content;
    const text = typeof c === "string" ? c
      : Array.isArray(c) ? c.filter(b => b && b.type === "text").map(b => b.text).join("\n") : "";
    if (role === "assistant" && !outText) outText = text;
    else if (role === "user" && !userText && text) userText = text;
  }
} catch { done(); }
if (!outText || outText.length < 4) done();

// 이번 턴 tool 증거(경로+명령) — tool-use.jsonl tail 을 evidence 문자열로 정규화(근사, canary용)
const here = dirname(fileURLToPath(import.meta.url));
const runtime = join(here, "..", ".claude", "runtime");
let evidence = [];
try {
  const tu = readFileSync(join(runtime, "tool-use.jsonl"), "utf8").split("\n").filter(Boolean);
  for (const ln of tu.slice(-60)) {
    let e; try { e = JSON.parse(ln); } catch { continue; }
    const t = e.target || {};
    const parts = [t.verb || "", ...(Array.isArray(t.paths) ? t.paths : [])].filter(Boolean);
    if (parts.length) evidence.push(parts.join(" "));
  }
} catch { /* 없으면 빈 증거 */ }

// verification_gate.py 호출(report main; 항상 exit0). findings 만 로그.
try {
  const guard = join(here, "..", "scripts", "verification_gate.py");
  const py = process.env.PYTHON || "python3";
  const input = JSON.stringify({ output_text: outText, user_input: userText, tool_evidence: evidence });
  const r = spawnSync(py, [guard], { input, timeout: 8000, encoding: "utf8" });
  if (r.stdout) {
    let res; try { res = JSON.parse(r.stdout.trim()); } catch { res = null; }
    if (res && Array.isArray(res.findings) && res.findings.length) {
      try { mkdirSync(runtime, { recursive: true }); } catch {}
      const rec = { ts: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
                    would_block: res.exit_code === 2, findings: res.findings };
      // NOTE: new Date() OK in node hook(런타임). 응답 원문은 저장 안 함.
      appendFileSync(join(runtime, "verification-gate-report.jsonl"), JSON.stringify(rec) + "\n");
      if (res.exit_code === 2) {
        process.stderr.write(`[verification-gate·report] would_block: ${res.findings.filter(f=>f.blocking).map(f=>f.detector).join(",")} (canary·차단 아님)\n`);
      }
    }
  }
} catch { /* advisory — 무시 */ }
done();
