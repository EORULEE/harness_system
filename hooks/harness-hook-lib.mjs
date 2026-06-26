// harness-hook-lib.mjs — Hook 공통 유틸 (Windows/macOS/Linux 공용)
//
// 모든 hook이 공유하는 기능:
//   - stdin 전부 읽기 (JSON 또는 raw)
//   - Python 스크립트 호출 (하네스는 Python 기반이므로)
//   - 프로젝트 디렉토리 찾기 (CLAUDE_PROJECT_DIR)
//   - stderr 안전 로깅

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

/**
 * stdin 전체를 문자열로 읽는다. EOF까지.
 * Claude Code가 hook에 JSON을 stdin으로 넘긴다.
 */
export async function readStdin() {
    return new Promise((resolve, reject) => {
        let data = '';
        if (process.stdin.isTTY) {
            // 인터랙티브 실행 (테스트용) — stdin이 terminal
            resolve('');
            return;
        }
        process.stdin.setEncoding('utf-8');
        process.stdin.on('data', chunk => { data += chunk; });
        process.stdin.on('end', () => resolve(data));
        process.stdin.on('error', err => reject(err));
    });
}

/**
 * 프로젝트 루트 결정:
 *   1. CLAUDE_PROJECT_DIR 환경변수 (Claude Code가 설정)
 *   2. 현재 작업 디렉토리
 */
export function getProjectDir() {
    return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

/**
 * Python 실행 파일 결정 (크로스플랫폼 자동 탐색).
 *
 * 우선순위:
 * 1. process.env.PYTHON (사용자 설정 절대경로)
 * 2. 플랫폼별 표준 위치 자동 탐색:
 *    - Windows: LOCALAPPDATA/ProgramFiles 의 Python 3.9~3.13
 *    - macOS: /opt/homebrew (Apple Silicon), /usr/local (Intel), MacPorts, pyenv, Anaconda
 *    - Linux: /usr/bin, /usr/local/bin, ~/.local/bin (pip --user), pyenv, Anaconda
 * 3. fallback: 'python' (Win) 또는 'python3' (Unix)
 *
 * Claude Code 가 GUI/Dock/systemd 등 빈약한 PATH 에서 실행될 때
 * `spawn python[3] ENOENT` 방지 (v2.4.7+ S6 이슈 대응).
 *
 * 결과는 모듈 로드 중 한 번만 계산 후 캐시.
 */
let _cachedPythonCmd = null;
export function getPythonCmd() {
    if (_cachedPythonCmd) return _cachedPythonCmd;
    if (process.env.PYTHON) {
        _cachedPythonCmd = process.env.PYTHON;
        return _cachedPythonCmd;
    }

    const candidates = [];
    if (process.platform === 'win32') {
        const localApp = process.env.LOCALAPPDATA || '';
        const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
        const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
        for (const ver of ['313', '312', '311', '310', '39']) {
            if (localApp) {
                candidates.push(`${localApp}\\Programs\\Python\\Python${ver}\\python.exe`);
            }
            candidates.push(`${programFiles}\\Python${ver}\\python.exe`);
            candidates.push(`${programFilesX86}\\Python${ver}\\python.exe`);
        }
    } else {
        const home = process.env.HOME || '';
        candidates.push(
            '/usr/bin/python3',
            '/usr/local/bin/python3',
            '/opt/homebrew/bin/python3',  // macOS Apple Silicon
            '/opt/local/bin/python3',     // MacPorts
        );
        for (const ver of ['3.13', '3.12', '3.11', '3.10', '3.9']) {
            candidates.push(`/opt/homebrew/opt/python@${ver}/bin/python3`);
            candidates.push(`/usr/local/opt/python@${ver}/bin/python3`);
        }
        if (home) {
            candidates.push(
                `${home}/.local/bin/python3`,      // pip --user
                `${home}/.pyenv/shims/python3`,    // pyenv
                `${home}/anaconda3/bin/python3`,   // Anaconda
                `${home}/miniconda3/bin/python3`,  // Miniconda
            );
        }
    }

    for (const p of candidates) {
        if (existsSync(p)) {
            _cachedPythonCmd = p;
            return _cachedPythonCmd;
        }
    }

    // 탐색 실패 시 PATH 검색에 의존 (기존 동작)
    _cachedPythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    return _cachedPythonCmd;
}

/**
 * Python 스크립트 호출. stdin 전달 가능.
 *
 * @param {string} scriptPath - 절대 경로 권장
 * @param {string[]} args - Python 스크립트 인자
 * @param {object} options
 *   - stdin: 전달할 stdin 내용 (문자열)
 *   - timeout: 밀리초 (기본 5000)
 *   - captureOutput: true면 stdout/stderr 반환, false면 그대로 전달
 *   - cwd: 작업 디렉토리
 *   - silent: 에러도 무시 (best-effort)
 * @returns {Promise<{code, stdout, stderr}>}
 */
export function runPython(scriptPath, args = [], options = {}) {
    return new Promise(resolve => {
        const {
            stdin = null,
            timeout = 5000,
            captureOutput = true,
            cwd = getProjectDir(),
            silent = false,
        } = options;

        if (!existsSync(scriptPath)) {
            if (!silent) {
                process.stderr.write(`[hook-lib] Python script not found: ${scriptPath}\n`);
            }
            resolve({ code: -1, stdout: '', stderr: 'script not found' });
            return;
        }

        const pythonCmd = getPythonCmd();
        const child = spawn(pythonCmd, [scriptPath, ...args], {
            cwd,
            stdio: captureOutput
                ? ['pipe', 'pipe', 'pipe']
                : ['pipe', 'inherit', 'inherit'],
            windowsHide: true,
            env: {
                ...process.env,
                // Fix 1 (B2): 한국어 Windows CP949 콘솔에서 Python 이모지 출력 실패 방지.
                // 이미 사용자가 PYTHONIOENCODING/PYTHONUTF8 설정했으면 그대로 존중.
                PYTHONIOENCODING: process.env.PYTHONIOENCODING || 'utf-8',
                PYTHONUTF8: process.env.PYTHONUTF8 || '1',
            },
        });

        let stdout = '';
        let stderr = '';
        if (captureOutput) {
            child.stdout.on('data', d => { stdout += d.toString('utf-8'); });
            child.stderr.on('data', d => { stderr += d.toString('utf-8'); });
        }

        // timeout 처리
        const timer = setTimeout(() => {
            try { child.kill('SIGTERM'); } catch {}
            if (!silent) {
                process.stderr.write(`[hook-lib] Python timeout after ${timeout}ms: ${scriptPath}\n`);
            }
        }, timeout);

        child.on('error', err => {
            clearTimeout(timer);
            if (!silent) {
                process.stderr.write(`[hook-lib] Python spawn error: ${err.message}\n`);
            }
            resolve({ code: -1, stdout, stderr: err.message });
        });

        child.on('close', code => {
            clearTimeout(timer);
            resolve({ code: code ?? -1, stdout, stderr });
        });

        // stdin 전달
        if (stdin !== null) {
            try {
                child.stdin.write(stdin);
                child.stdin.end();
            } catch {
                // stdin write 실패는 child가 이미 종료됐을 수 있음 — 무시
            }
        } else {
            child.stdin.end();
        }
    });
}

/**
 * 스크립트 경로 조합 — Windows/Unix 모두 작동.
 */
export function scriptPath(name) {
    return path.join(getProjectDir(), 'scripts', name);
}

/**
 * 에러 메시지를 stderr로 쓰되 예외 발생 안 시킴 (best-effort 로깅).
 */
export function logError(msg) {
    try { process.stderr.write(`${msg}\n`); } catch {}
}

/**
 * 조용히 exit 0 — hook 실패로 Claude Code 블로킹 방지.
 */
export function silentExit() {
    process.exit(0);
}
