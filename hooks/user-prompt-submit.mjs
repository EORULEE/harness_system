#!/usr/bin/env node
// user-prompt-submit.mjs — UserPromptSubmit hook
//
// 사용자 입력이 들어올 때 발화. 현재 턴 UUID를 생성하고 audit log에 기록.
// 에이전트는 응답 직전 `session_logger.py verify` 로 이 턴의 실제 실행 기록을 확인,
// 메타 블록 주장과 일치하는지 검증한다.
//
// 중요: current_turn.txt 를 foreground로 남겨야 하므로 await 필수.

import { readStdin, scriptPath, runPython, silentExit } from './harness-hook-lib.mjs';

async function main() {
    let input;
    try {
        input = await readStdin();
    } catch {
        input = '';
    }

    // turn-start는 현재 턴 UUID를 파일에 쓴다 (foreground 필수)
    await runPython(scriptPath('session_logger.py'), ['turn-start'], {
        stdin: input,
        timeout: 3000,
        silent: true,
        captureOutput: true,
    });

    silentExit();
}

main().catch(() => silentExit());
