#!/usr/bin/env bash
# volatile_fixtures — deny-by-default 패키징이 부수적으로 strip 하는 "휘발성·secret-bait fixture"를
# smoke 실행 시 런타임 재생성한다 (r13, harness-2026-06-26).
#
# 배경: tarball exclude(05_OFFLINE_TARBALL_INSTALL.md: --exclude='*session_log*' --exclude='*/runtime/*')
#       및 .gitignore(**/*session_log*.jsonl·**/runtime/) 는 실제 런타임 세션로그·secret 누출을 막는
#       올바른 보호다. 그러나 이 패턴이 테스트 fixture
#       tests/fixtures/fleet-agent-pair/proj-observed/.claude/runtime/session_log.jsonl 까지 부수적으로
#       잘라, offline tarball·git clone 설치본에서 smoke_deploy_gate T9 / smoke_fleet_agent_pair T45·T55
#       가 false-fail 했다(r12 까지). 근본수정 = 휘발성 fixture 를 ship 하지 않고 smoke 가 런타임 생성.
#       (ledger_variant·stop_guard 가 이미 쓰는 mktemp self-setup 과 동일 철학.)
#
# secret 안전: bait 문자열은 런타임 문자열 결합으로만 구성 → tracked 소스에는
#       그 secret-bait 리터럴(가짜 키=값 및 한글 prompt)이 통째로 존재하지 않는다(secret-scan / deny 회피).
#       런타임 생성 파일은 .gitignore 로 추적되지 않으므로 배포본에 포함되지 않는다.

# regen_volatile_fixtures <fixtures_root>
#   <fixtures_root> = tests/fixtures/fleet-agent-pair 경로($FX). proj-observed 의 휘발성 session_log 를
#   원본과 byte-identical(sha256 d25b55781f5635ff8a8309c40943fcdf85b87c465b10d9961655ba2716e0c6e4)로 재생성.
regen_volatile_fixtures() {
  local fx="$1"
  [ -n "$fx" ] || { echo "regen_volatile_fixtures: <fixtures_root> 인자 필요" >&2; return 1; }
  # proj-observed = "session_log(task-call) 만 있고 formal verdict 없음 → observed-only" 검증 fixture.
  # payload.prompt 에 secret-bait 포함(T55: collector 가 prompt/secret 을 미수집하는지 검증) → 런타임 결합.
  local d="$fx/proj-observed/.claude/runtime"
  mkdir -p "$d" || return 1
  local key="EXAMPLE_API_""KEY"             # 런타임 결합 → 가짜 키 이름 (소스 분할)
  local val="bait""secret123"              # 런타임 결합 → 가짜 토큰값 (소스 분할)
  local prompt="bait ""본문 ${key}=${val}"  # 런타임 결합 → 한글 prompt + 가짜 키=값 (소스 분할)
  printf '{"event":"task-call","ts":"2026-06-24T22:00:00","payload":{"pair_inferred":"PAIR-SCIENCE","subagent_type":"x-science","prompt":"%s","description":"d"}}\n' "$prompt" \
    > "$d/session_log.jsonl"
}
