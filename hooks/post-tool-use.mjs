#!/usr/bin/env node
// post-tool-use.mjs — Claude Code PostToolUse 훅 (Node.js 크로스플랫폼)
//
// 목적:
//   1. stdin JSON을 capture_queue에 적재 (Bash/Write/Edit/MultiEdit 대상)
//   2. circuit_breaker의 total_tokens 자동 누적
//
// 특징:
//   - async: true 로 호출되므로 Claude가 응답 대기 안 함
//   - timeout 5초
//   - 실패해도 exit 0 (Claude 블로킹 방지)

import { readStdin, scriptPath, runPython, silentExit } from './harness-hook-lib.mjs';
import { existsSync } from 'node:fs';

async function main() {
    const worker = scriptPath('capture_worker.py');
    const breaker = scriptPath('circuit_breaker.py');

    // 워커 스크립트가 없으면 조용히 exit
    if (!existsSync(worker)) {
        silentExit();
        return;
    }

    let input;
    try {
        input = await readStdin();
    } catch {
        silentExit();
        return;
    }

    // (1) capture_queue 적재
    await runPython(worker, ['enqueue'], {
        stdin: input,
        timeout: 4000,
        silent: true,
        captureOutput: true,  // 출력을 삼킴 (Claude에 영향 주지 않음)
    });

    // (2) 활동량 자동 집계 (v2.4.4 — 토큰 예산 자동 추적)
    if (existsSync(breaker)) {
        await runPython(breaker, ['track-activity'], {
            stdin: input,
            timeout: 4000,
            silent: true,
            captureOutput: true,
        });
    }

    // PostToolUse에서 블로킹할 이유 없음 — 무조건 exit 0
    silentExit();
}

main().catch(() => silentExit());
