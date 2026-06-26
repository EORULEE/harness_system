#!/usr/bin/env node
/**
 * account-onboarding.mjs — SessionStart 훅. 첫 사용 시 계정 설정을 묻도록 advisory 주입.
 * .claude/.onboarded 마커가 있으면 침묵. 강제 아님(advisory only, exit 0).
 */
import { readFileSync, existsSync } from "node:fs";

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { process.exit(0); }
try {
  const j = JSON.parse(raw || "{}");
  const ev = j.hook_event_name || j.hookEventName || j.event;
  if (ev && ev !== "SessionStart") process.exit(0);
} catch { process.exit(0); }

const proj = process.env.CLAUDE_PROJECT_DIR || ".";
try { if (existsSync(proj + "/.claude/.onboarded")) process.exit(0); } catch {}

const msg =
  "\n[harness onboarding · advisory] 사용자가 이 하네스를 처음 쓰는 것일 수 있음(.claude/.onboarded 없음).\n" +
  "첫 응답에서 **`SETUP.md` 기준으로 첫 설치 전체를 안내·질문**하라(SETUP.md 가 ACCOUNTS/WIKI 를 묶은 통합 가이드):\n" +
  " 1) **먼저 `bash selftest.sh`** — 요구사항·코어 smoke(11)·스킬(45)·훅·도구·계정/MCP 상태 한 번에 확인.\n" +
  " 2) 코어(응답규율·dev-discipline·code-claim·loop·deep-interview·ralph·system-truth-probe·adaptive)는 설정 0으로 바로 작동.\n" +
  " 3) **선택 통합을 하나씩 안내·질문** — 무엇을 설정할지: ⓐ **LLM Wiki**(`export WIKI_ROOT=<노트폴더>`, 결정적 도구는 계정 0 / WIKI.md) ⓑ **Gemini 키**(글쓰기, ACCOUNTS §2) ⓒ **Codex+ChatGPT**(코드 적대검토, §3) ⓓ **연구 MCP**(semantic-scholar·serena 등, §4). 없으면 Claude 대체/생략.\n" +
  " ⚠️ 개인정보 보호로 KB(reference manager·notes app)·Drive·Fleet·일부 글쓰기 스킬·MCP 서버는 미포함 — 친구가 자기 것으로 구성(SETUP.md §3).\n" +
  "설정/결정이 끝나면 `touch .claude/.onboarded` 로 안내 종료. 강제 아님 · advisory.\n";

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: msg },
}));
process.exit(0);
