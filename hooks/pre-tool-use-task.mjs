#!/usr/bin/env node
// pre-tool-use-task.mjs — PreToolUse hook (matcher: Task)
//
// 서브에이전트 분기 시 발화. Claude Code가 JSON stdin으로
//   { "tool_name": "Task", "tool_input": {"subagent_type": "...", ...} }
// 를 넘긴다. 이 이벤트가 audit log에 쌓여야만 메타 블록의
// "참여 페어" 주장이 뒷받침된다.

import { readStdin, scriptPath, runPython, silentExit } from './harness-hook-lib.mjs';

async function main() {
    let input;
    try {
        input = await readStdin();
    } catch {
        silentExit();
        return;
    }

    await runPython(scriptPath('session_logger.py'), ['task-call'], {
        stdin: input,
        timeout: 3000,
        silent: true,
        captureOutput: true,
    });

    silentExit();
}

main().catch(() => silentExit());
