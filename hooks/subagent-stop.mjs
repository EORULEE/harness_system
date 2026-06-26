#!/usr/bin/env node
// subagent-stop.mjs — SubagentStop hook
//
// 서브에이전트 종료 시:
//   1. task-end 기록
//   2. circuit_breaker track-subagent-command 로 transcript 파싱 → codex 호출 집계
//   3. 집계 결과를 session_logger subagent-audit 로 파이프

import { readStdin, scriptPath, runPython, silentExit } from './harness-hook-lib.mjs';

async function main() {
    let input;
    try {
        input = await readStdin();
    } catch {
        silentExit();
        return;
    }

    const sessionLogger = scriptPath('session_logger.py');
    const breaker = scriptPath('circuit_breaker.py');

    // (1) task-end 기록
    await runPython(sessionLogger, ['task-end'], {
        stdin: input,
        timeout: 3000,
        silent: true,
        captureOutput: true,
    });

    // (2) transcript 파싱 → JSON 결과 획득
    const trackResult = await runPython(
        breaker,
        ['track-subagent-command', '--format', 'json'],
        {
            stdin: input,
            timeout: 5000,
            silent: true,
            captureOutput: true,
        }
    );

    // (3) 집계 결과가 있으면 subagent-audit 로 파이프
    if (trackResult.code === 0 && trackResult.stdout.trim()) {
        await runPython(sessionLogger, ['subagent-audit'], {
            stdin: trackResult.stdout,
            timeout: 3000,
            silent: true,
            captureOutput: true,
        });
    }

    silentExit();
}

main().catch(() => silentExit());
