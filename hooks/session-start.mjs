#!/usr/bin/env node
// [hook-snapshot-stale check] 2026-07-02 — claude 프로세스가 장수하면 settings 훅 "목록" 스냅샷이
// 프로세스 시작 시점에 고정(/clear 미갱신) → 이후 배선된 훅은 그 프로세스에서 비활성.
// 훅 "파일" 수정은 즉시 반영이므로, 이미 배선된 본 파일에 검사를 넣어 재시작 없이 fleet 전체 활성.
// 위치 독립·자기완결·advisory(실패 무시, mac /proc 부재 포함).
(async () => { try {
  const fs = await import("node:fs");
  const p = `/proc/${process.ppid}`;
  if (fs.existsSync(p)) {
    const ps = fs.statSync(p).mtimeMs;
    const dir = (process.env.CLAUDE_PROJECT_DIR || ".") + "/.claude";
    const st = ["settings.json", "settings.local.json"].map(f => dir + "/" + f)
      .filter(f => fs.existsSync(f) && fs.statSync(f).mtimeMs > ps + 5000);
    if (st.length) process.stdout.write(
      `\n⚠️ [hook-snapshot-stale] settings 훅 배선(${st.map(f=>f.split("/").pop()).join(", ")})이 이 claude 프로세스 시작 이후 변경됨 — ` +
      `새로 배선된 훅은 이 프로세스에서 비활성일 수 있음. **claude 재시작 필요**(/clear 로는 스냅샷 미갱신).\n`);
  }
} catch {} })();
// [skill-shadow drift advisory] 2026-07-08 (AC15, 계약 contract-skill-dualization) —
// repo(SoT)↔global 스킬 drift 를 매 세션 report-only 경고(hard-block 아님, 헌법 report-first).
// 특히 global-ahead(편집이 repo 아닌 global 서 남) → repo 흡수 필요.
// ⚠️ **동기 top-level 블록**(async IIFE 아님) — ESM import 는 hoist 되므로 아래 정적 import 한
//    spawnSync/existsSync 를 여기서 쓸 수 있고, 모듈 평가 중 main() 호출(파일 끝) 전에 완료가 보장된다.
//    (codex BLOCK2 반영: async fire-and-forget 은 main() 의 process.exit 에 잘려 경고 유실 가능했음.)
try {
  const dir = process.env.CLAUDE_PROJECT_DIR || ".";
  const script = dir + "/scripts/skill_shadow_check.py";
  if (existsSync(script)) {
    const r = spawnSync("python3", [script, "report", "--quiet"],
      { timeout: 8000, encoding: "utf8" });
    const out = (r.stdout || "");
    const ga = out.split("\n").find(l => l.includes("global-ahead drift"));
    if (ga) process.stdout.write(
      `\n⚠️ [skill-shadow] ${ga.trim()}\n   → \`python3 scripts/skill_shadow_check.py check\` 로 확인, reconcile 후 \`skill_sync.py --apply\`.\n`);
  }
} catch { /* advisory: 실패 무시 */ }
// session-start.mjs — SessionStart hook + 수동 실행 겸용
//
// 역할:
//   1. Claude Code SessionStart 훅 (자동 주입)
//   2. 수동 실행 (설치 직후 검증 등)
//
// 동작:
//   - --emit: bundle 내용을 stdout으로 주입 (settings.json 기본 모드)
//   - --quiet: 최소 출력
//   - (기본): 전체 상태 요약
//
// 기능:
//   1. memory_sync.py session-hook: TTL 검사 + 필요 시 bundle 재생성
//   2. instincts 요약
//   3. 압축 재시도 큐 (백그라운드)
//   4. 캡처 큐 즉시 처리

import {
    scriptPath, runPython, getProjectDir,
    logError
} from './harness-hook-lib.mjs';
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import process from 'node:process';

const args = process.argv.slice(2);
const EMIT = args.includes('--emit');
const QUIET = args.includes('--quiet');

function log(msg) {
    if (!QUIET) process.stdout.write(msg + '\n');
}

function countFiles(dir, extension) {
    if (!existsSync(dir)) return 0;
    try {
        return readdirSync(dir).filter(f => f.endsWith(extension)).length;
    } catch {
        return 0;
    }
}

async function main() {
    const projectDir = getProjectDir();
    process.chdir(projectDir);

    const memScript = scriptPath('memory_sync.py');
    const insScript = scriptPath('instincts_updater.py');
    const compScript = scriptPath('compression_worker.py');
    const capScript = scriptPath('capture_worker.py');

    // memory_sync 없으면 조용히 종료
    if (!existsSync(memScript)) {
        if (!QUIET) logError('⚠️  memory_sync.py 없음 — 하네스 설치 확인');
        process.exit(0);
    }

    // ── --emit 모드: bundle 내용을 stdout으로 바로 주입 ──
    if (EMIT) {
        // ── Memory Continuity v2: bounded continuity worker (best-effort) ──
        // queue 의 최신 유효 이벤트만 처리해 _active_context.md 갱신. timeout/실패여도 아래 memory_sync·KB 주입은 그대로.
        try {
            const contScript = scriptPath('session_continuity_worker.py');
            if (existsSync(contScript)) {
                await runPython(contScript, ['--once', '--latest'], {
                    timeout: 4000,        // 명시적 timeout
                    captureOutput: true,  // 워커 stdout(JSON)은 context 에 주입하지 않음
                    silent: true,
                });
            }
        } catch { /* advisory: 워커 실패/timeout → SessionStart 계속 */ }

        // inherit stdio 로 memory_sync.py session-hook --emit-stdout 실행
        // 그 stdout이 Claude Code 세션 context에 주입됨 (이제 ACTIVE_CONTEXT 핵심이 맨 앞)
        const r = await runPython(
            memScript,
            ['session-hook', '--emit-stdout'],
            {
                timeout: 25000,
                captureOutput: false,  // stdout을 Claude Code에 그대로 전달
                silent: true,
            }
        );
        process.exit(r.code === -1 ? 0 : r.code);
        return;
    }

    // ── 일반 모드: 전체 상태 요약 ──
    if (!QUIET) {
        log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
        log('🔌 세션 시작 훅');
        log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    }

    // (1) Memory session-hook (captureOutput true: 출력은 inherit 해야 사용자가 봄)
    await runPython(memScript, ['session-hook'], {
        timeout: 25000,
        captureOutput: false,
        silent: true,
    });

    // (2) Instincts 요약
    if (existsSync(insScript) && !QUIET) {
        const r = await runPython(insScript, ['stats'], {
            timeout: 5000,
            captureOutput: true,
            silent: true,
        });
        if (r.code === 0) {
            const m = r.stdout.match(/^활성:\s+(\d+)/m);
            if (m) log(`📚 Instincts: ${m[1]} 활성`);
        }
    }

    // (3) 압축 재시도 큐 (백그라운드 fire-and-forget)
    if (existsSync(compScript)) {
        const queueDir = path.join(projectDir, '.claude', 'runtime', 'compression_queue');
        const cnt = countFiles(queueDir, '.yaml');
        if (cnt > 0) {
            if (!QUIET) log(`🔄 압축 재시도 큐: ${cnt}건 대기 → 백그라운드 처리`);
            // spawn detached — 세션 블로킹 방지
            try {
                const child = spawn(
                    process.platform === 'win32' ? 'python' : 'python3',
                    [compScript, 'retry-queue', '--max-retries', '3'],
                    {
                        cwd: projectDir,
                        detached: true,
                        stdio: 'ignore',
                        windowsHide: true,
                    }
                );
                child.unref();
            } catch {
                // 백그라운드 실패는 무시
            }
        }
    }

    // (4) 캡처 큐 즉시 처리
    if (existsSync(capScript)) {
        const capDir = path.join(projectDir, '.claude', 'runtime', 'capture_queue');
        const cnt = countFiles(capDir, '.json');
        if (cnt > 0) {
            if (!QUIET) log(`📥 캡처 큐: ${cnt}건 → 즉시 처리`);
            await runPython(capScript, ['process', '--limit', '100'], {
                timeout: 10000,
                silent: true,
                captureOutput: true,
            });
        }
    }

    // (5) 번들 경로 안내
    if (!QUIET) {
        const contextFile = path.join(projectDir, '.claude', 'memory', '_context.md');
        if (existsSync(contextFile)) {
            log('');
            log(`📄 Context bundle: .claude/memory/_context.md`);
            log('   에이전트는 이 파일을 먼저 읽고 작업을 시작하세요.');
        }
        log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    }

    process.exit(0);
}

main().catch(err => {
    logError(`[session-start.mjs] error: ${err.message}`);
    process.exit(0);  // 에러여도 exit 0 — 세션은 시작돼야 함
});
