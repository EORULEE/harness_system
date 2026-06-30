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
  "첫 응답에서 **`SETUP.md` 기준으로 첫 설치 전체를 적극적으로 진행**하라(단순 언급·문서 떠넘기기 금지 — 네가 먼저 제안하고, 동의하면 직접 실행). SETUP.md 가 ACCOUNTS/WIKI 를 묶은 통합 가이드:\n" +
  " 1) **먼저 `bash selftest.sh` 를 직접 실행**해 결과(요구사항·코어 smoke 11·스킬 45·훅·도구·계정/MCP 상태)를 보여주고 요약하라. **[A] 에 ⚠(python<3.9 / PyYAML 없음 / node<18)** 가 있으면, **시스템 python·node 를 바꾸라고 하지 말고** 격리 env(conda `create -n harness python=3.12 pyyaml` / venv+`pip install pyyaml` / nvm `install 18`)로 맞추도록 안내하라(SETUP.md §0, `export PYTHON=` 로 훅 고정). 기존 환경 보존이 우선.\n" +
  " 2) 코어(응답규율·dev-discipline·code-claim·loop·deep-interview·ralph·system-truth-probe·adaptive)는 설정 0으로 바로 작동 — 이미 됨을 알린다.\n" +
  " 3) **선택 통합을 순서대로 적극 제안하고, 각 항목마다 '지금 본인 계정/키로 설정해 드릴까요?' 하고 먼저 물어라**(키는 사용자 본인 것 — 패키지에 키 없음):\n" +
  "    ⓐ **LLM Wiki**: '노트 폴더를 알려주시면 `export WIKI_ROOT=<폴더>` 로 잡고 결정적 도구를 바로 보여드릴까요?'(계정 0 / WIKI.md)\n" +
  "    ⓑ **Gemini 키**(글쓰기 백엔드, ACCOUNTS §2): 키 발급처 안내 → 받으면 `~/.claude/gemini.env` 작성까지 도와라.\n" +
  "    ⓒ **Codex+ChatGPT**(코드 적대검토, §3): 플러그인 설치 + 본인 ChatGPT 인증 절차를 단계별 안내.\n" +
  "    ⓓ **연구 MCP**(§4): '**지금 본인 계정으로 연구 MCP(semantic-scholar·paper-search·github·serena)를 추가해 드릴까요?**' 하고 먼저 제안 → **동의하면 `bash scripts/setup_mcp.sh` 를 직접 실행**하고 `claude mcp list` 로 `✔ Connected` 확인까지 보여줘라(키 필요한 서버는 본인 것 입력 안내).\n" +
  " ⚠️ 개인정보 보호로 KB(reference manager·notes app)·Drive·Fleet·일부 글쓰기 스킬·MCP 서버는 미포함 — 친구가 자기 것으로 구성(SETUP.md §3).\n" +
  "설정/결정이 끝나면 `touch .claude/.onboarded` 로 안내 종료(이것도 네가 제안). 강제 아님 · advisory.\n";

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: msg },
}));
process.exit(0);
