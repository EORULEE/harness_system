#!/usr/bin/env node
// stop.mjs — Stop hook (guard + capture 처리 + turn-end 기록)
//
// 중요한 특성:
//   - stop-guard 가 exit != 0 이어도 turn-end 는 반드시 기록
//   - 최종 exit code 는 guard 의 status 전달 (Claude Code가 blocking 판단)

import { readStdin, scriptPath, runPython } from './harness-hook-lib.mjs';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

// v4.6 — Ralph 경계검사 (harness-ralph): _output/ralph 최신 로그가
// 6회+ iteration 인데 escalation·complete 표식이 없으면 차단(원칙 12, circuit_breaker≤5).
// 기존 stop-guard(guardStatus)와 독립 병렬 — ralph 로그 없으면 항상 0(회귀 0).
function checkRalphBoundary() {
    try {
        const dir = join(process.cwd(), '_output', 'ralph');
        const files = readdirSync(dir)
            .filter(f => f.endsWith('.md') && !f.startsWith('_'))
            .map(f => ({ f, m: statSync(join(dir, f)).mtimeMs }))
            .sort((a, b) => b.m - a.m);
        if (!files.length) return { block: false };
        const latest = files[0];
        if (Date.now() - latest.m > 6 * 3600 * 1000) return { block: false }; // stale 무시
        const txt = readFileSync(join(dir, latest.f), 'utf8');
        const iters = [...txt.matchAll(/^#{1,4}\s*(?:Iteration|Round|반복)\s+(\d+)/gim)]
            .map(x => parseInt(x[1], 10));
        const maxIter = iters.length ? Math.max(...iters) : 0;
        const escalated = /ESCALAT|에스컬레이션/i.test(txt);
        const complete = /COMPLETE|모든 기준 통과|all\s+criteria\s+pass|PASS_ALL/i.test(txt);
        if (maxIter > 5 && !escalated && !complete) {
            return {
                block: true,
                msg: `❌ Ralph 경계 위반: ${latest.f} 가 ${maxIter}회 iteration 인데 ` +
                     `에스컬레이션·완료 표식 없음. circuit_breaker max_iterations=5 초과 → ` +
                     `사용자 에스컬레이션 필요(무한루프 금지). 로그에 'ESCALATED' 또는 완료 표식 추가 후 종료.`,
            };
        }
        return { block: false };
    } catch {
        return { block: false }; // 디렉토리 없음 등 → 차단 안 함
    }
}

// v4.6 F6 — Ralph PRD 완료 차단: 최근 prd.json 이 미통과(passes:false)인데 같은 디렉토리
// 로그가 완료 선언(complete marker, 미에스컬)이면 차단 → 거짓 완료 방지. checkRalphBoundary
// (로그 iteration 검사)와 독립·추가. prd.json 없음/완전통과/미완료선언 → 항상 비차단(회귀 0).
export function checkRalphPrdCompletion() {
    try {
        const base = join(process.cwd(), '_output', 'ralph');
        const cands = [];
        for (const e of readdirSync(base)) {
            const full = join(base, e);
            let st;
            try { st = statSync(full); } catch { continue; }
            if (st.isDirectory()) {
                const pj = join(full, 'prd.json');
                try { const ps = statSync(pj); if (ps.isFile()) cands.push({ f: pj, m: ps.mtimeMs, dir: full }); } catch { /* no prd in dir */ }
            } else if (e === 'prd.json' && st.isFile()) {
                cands.push({ f: full, m: st.mtimeMs, dir: base }); // prd_template.json 은 제외됨(파일명 일치 아님)
            }
        }
        if (!cands.length) return { block: false };
        cands.sort((a, b) => b.m - a.m);
        const latest = cands[0];
        if (Date.now() - latest.m > 6 * 3600 * 1000) return { block: false }; // stale 무시
        let prd;
        try {
            prd = JSON.parse(readFileSync(latest.f, 'utf8'));
        } catch {
            // fail-open(사용자 턴 wedge 금지) 유지하되, 무성 통과 대신 가시화(Codex 지적).
            process.stderr.write(`[stop.mjs] ⚠️ Ralph prd.json 파싱 실패(완료검증 skip): ${latest.f}\n`);
            return { block: false };
        }
        // Ralph PRD 형태(stories[] + completion 객체) 아니면 스킵(타 schema·플레이스홀더)
        if (!Array.isArray(prd.stories) || typeof prd.completion !== 'object' || prd.completion === null) {
            return { block: false };
        }
        const acPass = (s) => Array.isArray(s.acceptance_criteria)
            ? s.acceptance_criteria.every(a => a && a.passes === true) : true;
        const prdComplete =
            prd.completion.all_stories_pass === true &&
            prd.stories.length > 0 &&
            prd.stories.every(s => s && s.passes === true && acPass(s));
        if (prdComplete) return { block: false }; // 완전통과 → 차단 안 함(회귀: v46 prd 17/17)
        // 같은 dir 의 최신 ralph-*.md 가 완료 선언(미에스컬)인지
        const logs = readdirSync(latest.dir)
            .filter(f => /^ralph-.*\.md$/.test(f))
            .map(f => ({ f, m: statSync(join(latest.dir, f)).mtimeMs }))
            .sort((a, b) => b.m - a.m);
        if (!logs.length) return { block: false }; // 완료 선언 로그 없음 → 진행중, 차단 안 함
        // 완료 선언도 신선해야 함(6h) — 과거 세션의 오래된 완료로그가 무관한 턴을 막지 않도록(Codex 지적).
        if (Date.now() - logs[0].m > 6 * 3600 * 1000) return { block: false };
        const txt = readFileSync(join(latest.dir, logs[0].f), 'utf8');
        const complete = /COMPLETE|모든 기준 통과|all\s+criteria\s+pass|PASS_ALL/i.test(txt);
        const escalated = /ESCALAT|에스컬레이션/i.test(txt);
        if (complete && !escalated) {
            const rel = latest.f.replace(process.cwd() + '/', '');
            const failing = prd.stories
                .filter(s => !(s.passes === true && acPass(s)))
                .map(s => s.id || '?').join(', ');
            return {
                block: true,
                msg: `❌ Ralph 완료 차단: ${rel} 에 미통과 기준(passes:false) 있음[story ${failing}]인데 ` +
                     `로그가 완료 선언. 거짓 완료 금지 — 미통과 기준을 fresh evidence 로 통과시키거나 ` +
                     `ESCALATED 표식 후 종료.`,
            };
        }
        return { block: false };
    } catch {
        return { block: false };
    }
}

async function main() {
    let input;
    try {
        input = await readStdin();
    } catch {
        input = '';
    }

    const sessionLogger = scriptPath('session_logger.py');
    const captureWorker = scriptPath('capture_worker.py');

    // (1) stop-guard — 언더리포트 차단
    const guardResult = await runPython(sessionLogger, ['stop-guard'], {
        stdin: input,
        timeout: 10000,
        silent: false,     // guard 에러 메시지는 사용자에게 보여야 함
        captureOutput: false,
    });
    // #4 fail-open: runPython 이 음수 code(-1=spawn 실패/python 부재/스크립트 없음)를 주면
    // guard 가 실제로 돌지 않은 것 → 차단(exit 255)이 아니라 fail-open(0). python 없는 머신
    // (<machine> 등)에서 매 턴 종료가 막히지 않도록. exit 2(실제 위반)는 그대로 전달.
    let guardStatus = guardResult.code;
    if (guardStatus < 0) {
        process.stderr.write(
            `[stop.mjs] ⚠️ stop-guard 미실행(code ${guardStatus}, python 부재/spawn 실패 가능) — ` +
            `fail-open: 턴 차단 안 함. 검증 스킵됨.\n`
        );
        guardStatus = 0;
    }

    // (2) capture_queue 처리 (best-effort)
    await runPython(captureWorker, ['process', '--limit', '50'], {
        timeout: 10000,
        silent: true,
        captureOutput: true,
    });

    // (3) turn-end 기록 (guard 실패여도 반드시 실행)
    await runPython(sessionLogger, ['turn-end', '--guard-exit', String(guardStatus)], {
        stdin: input,
        timeout: 5000,
        silent: true,
        captureOutput: true,
    });

    // (4) _output/ 동기화 (best-effort, 실패해도 블로킹 안 함)
    const syncOutput = scriptPath('sync_output.py');
    await runPython(syncOutput, ['sync'], {
        timeout: 10000,
        silent: true,
        captureOutput: true,
    });

    // (5) v4.6 Ralph 경계검사 (병렬, 독립). 기존 5대 BLOCKING(guardStatus)이 우선.
    //   - checkRalphBoundary: 로그 6회+ iteration 미에스컬 차단
    //   - checkRalphPrdCompletion(F6): prd.json 미통과인데 완료 선언 차단
    const ralph = checkRalphBoundary();
    if (ralph.block) {
        process.stderr.write(`\n${ralph.msg}\n`);
    }
    const ralphPrd = checkRalphPrdCompletion();
    if (ralphPrd.block) {
        process.stderr.write(`\n${ralphPrd.msg}\n`);
    }
    const ralphBlock = ralph.block || ralphPrd.block;
    // 최종 exit: guardStatus 우선(0이면 ralph 경계). stop-guard·hookify 최종 권위 유지.
    const finalExit = guardStatus !== 0 ? guardStatus : (ralphBlock ? 2 : 0);
    process.exit(finalExit);
}

// main() 은 **기본 실행**(훅 동작 불변·fail-safe). 테스트에서 함수만 import 할 때는
// STOP_MJS_NO_MAIN=1 로 명시 억제(dynamic import 직전 설정). 경로 endsWith 휴리스틱은
// 심볼릭링크/래퍼명에서 main 을 건너뛰어 가드를 무력화할 수 있어 사용하지 않는다(critical 수정).
if (!process.env.STOP_MJS_NO_MAIN) {
    main().catch(err => {
        process.stderr.write(`[stop.mjs] unexpected error: ${err.message}\n`);
        process.exit(0);  // 예기치 못한 에러여도 Claude 블로킹 방지
    });
}
