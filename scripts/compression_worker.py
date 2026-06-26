#!/usr/bin/env python3
"""
compression_worker.py — Layer 1 trace → Layer 2 structured memory 압축

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할 (Step 2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
trace 종료 시 호출되어:
  1. trace 전문을 Claude CLI에 전송 (claude -p)
  2. LLM이 YAML로 구조화 결과 반환
  3. 검증 후 Instincts·decisions.md·domain-facts.md에 자동 append
  4. 원본 trace는 그대로 보존

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실패 처리 (3중 안전장치)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. CLI 호출 실패 → 큐 파일에 적재 (.claude/runtime/compression_queue/)
2. 응답 YAML 파싱 실패 → 원본 응답을 _raw_responses/에 보존, 큐에 재시도 등록
3. 검증 실패 → 해당 항목만 skip, 나머지는 저장

어떤 경우에도 원본 trace는 손실되지 않음.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
명령
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  compress <trace-id>        특정 trace 압축 (실제 LLM 호출)
  retry-queue                실패 대기 중인 trace 재시도
  dry-run <trace-id>         프롬프트만 생성, 실제 호출 안 함
  show-prompt <trace-id>     생성될 프롬프트 미리보기
  stats                      압축 이력·토큰 사용량

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from harness_common import (
        file_lock, read_modify_write, save_yaml_atomic, atomic_write,
        load_yaml, HAS_YAML, now_iso, call_claude_cli, call_codex_cli,
    )
except ImportError as e:
    sys.stderr.write(f"❌ 의존성: {e}\n")
    sys.exit(1)

if not HAS_YAML:
    sys.stderr.write("❌ PyYAML 필요\n")
    sys.exit(1)

import yaml


# ────────────────────────────── 경로 ──────────────────────────────

MEMORY_DIR = Path(".claude/memory")
TRACES_DIR = MEMORY_DIR / "traces"
TRACES_INDEX = MEMORY_DIR / "_traces_index.yaml"
INSTINCTS_DIR = Path(".claude/instincts")
DECISIONS_FILE = MEMORY_DIR / "decisions.md"
FACTS_FILE = MEMORY_DIR / "domain-facts.md"

RUNTIME_DIR = Path(".claude/runtime")
COMPRESSION_QUEUE = RUNTIME_DIR / "compression_queue"
RAW_RESPONSES = RUNTIME_DIR / "_raw_llm_responses"
PENDING_EXTRACT_DIR = RUNTIME_DIR / "pending_extractions"
PENDING_REVIEW_ARCHIVE = RUNTIME_DIR / "_pending_review_archive"
COMPRESSION_LOG = RUNTIME_DIR / "compression_log.yaml"
TOKEN_USAGE_FILE = RUNTIME_DIR / "token_usage.yaml"

# 프롬프트 템플릿 위치 후보
PROMPT_CANDIDATES = [
    Path(__file__).parent.parent / "prompts" / "compress_trace.md",
    Path(__file__).parent / "compress_trace.md",
    Path("prompts/compress_trace.md"),
    Path("compress_trace.md"),
]

VALID_CATEGORIES = ["domain_knowledge", "methodology",
                    "anti_patterns", "conventions"]


# ────────────────────────────── 유틸 ──────────────────────────────


def ensure_runtime():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    COMPRESSION_QUEUE.mkdir(exist_ok=True)
    RAW_RESPONSES.mkdir(exist_ok=True)
    PENDING_EXTRACT_DIR.mkdir(exist_ok=True)
    PENDING_REVIEW_ARCHIVE.mkdir(exist_ok=True)


def load_prompt_template() -> str:
    for p in PROMPT_CANDIDATES:
        if p.exists():
            return p.read_text(encoding="utf-8")
    # 후보에 없으면 인라인 폴백 (최소 버전)
    return _FALLBACK_PROMPT


def build_prompt(trace_id: str) -> str | None:
    """trace 내용 + 메타데이터로 프롬프트 조립."""
    trace_file = TRACES_DIR / f"{trace_id}.md"
    if not trace_file.exists():
        return None
    content = trace_file.read_text(encoding="utf-8")

    # 인덱스에서 메타 조회
    idx = load_yaml(TRACES_INDEX) or {}
    info = idx.get("traces", {}).get(trace_id, {})

    template = load_prompt_template()
    prompt = template.replace("{{TRACE_CONTENT}}", content)
    prompt = prompt.replace("{{TRACE_ID}}", trace_id)
    prompt = prompt.replace("{{TRACE_NAME}}", info.get("name") or "unknown")
    prompt = prompt.replace("{{CAMPAIGN}}", info.get("campaign") or "(none)")
    prompt = prompt.replace("{{STARTED}}", info.get("started") or "unknown")
    prompt = prompt.replace("{{ENDED}}", info.get("ended") or "진행중")
    return prompt


def trace_exists(trace_id: str) -> bool:
    return (TRACES_DIR / f"{trace_id}.md").exists()


# ────────────────────────────── 응답 파싱 ──────────────────────────────


def extract_yaml_from_response(text: str) -> str | None:
    """LLM 응답에서 YAML 부분 추출.

    LLM이 때로 코드블록으로 감싸거나 앞뒤 설명을 붙일 수 있음.
    다음 순서로 시도:
      1. 전체를 YAML로 파싱 시도
      2. ```yaml ... ``` 블록 추출
      3. ``` ... ``` 블록 추출
      4. 첫 `summary:` 키부터 끝까지
    """
    text = text.strip()
    # 1. 직접 파싱 시도
    try:
        yaml.safe_load(text)
        return text
    except yaml.YAMLError:
        pass

    # 2. ```yaml 블록
    m = re.search(r"```(?:yaml|yml)\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 3. 코드블록
    m = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 4. summary: 부터
    m = re.search(r"^(summary:.*)", text, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(1).strip()

    return None


def validate_extraction(data: dict) -> tuple[dict, list[str]]:
    """LLM 응답 YAML 검증. 유효한 필드만 걸러서 반환.

    Returns (validated_data, warnings)
    """
    warnings = []
    result = {"summary": "", "instincts": [], "decisions": [], "facts": []}

    if not isinstance(data, dict):
        warnings.append("응답이 dict가 아님")
        return result, warnings

    # summary
    s = data.get("summary")
    if isinstance(s, str) and s.strip():
        result["summary"] = s.strip()[:500]

    # instincts
    for item in data.get("instincts", []) or []:
        if not isinstance(item, dict):
            warnings.append(f"instinct가 dict 아님: {type(item)}")
            continue
        cat = item.get("category")
        if cat not in VALID_CATEGORIES:
            warnings.append(f"잘못된 category: {cat}")
            continue
        item_id = item.get("id", "").strip()
        if not item_id or not re.match(r"^[a-z0-9][\w\-가-힣]{1,60}$", item_id):
            warnings.append(f"잘못된 instinct id: '{item_id}'")
            continue
        trigger = item.get("trigger", "").strip()
        action = item.get("action", "").strip()
        if not trigger or not action:
            warnings.append(f"[{item_id}] trigger/action 누락")
            continue
        confidence = item.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(0.95, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        result["instincts"].append({
            "category": cat,
            "id": item_id,
            "trigger": trigger,
            "action": action,
            "evidence": item.get("evidence", "").strip(),
            "confidence": confidence,
            "tags": item.get("tags") or [],
        })

    # decisions
    for item in data.get("decisions", []) or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "").strip()
        if not text:
            continue
        result["decisions"].append({
            "text": text,
            "rationale": item.get("rationale", "").strip(),
        })

    # facts
    for item in data.get("facts", []) or []:
        if not isinstance(item, dict):
            continue
        topic = item.get("topic", "").strip()
        content = item.get("content", "").strip()
        if not topic or not content:
            continue
        result["facts"].append({"topic": topic, "content": content})

    return result, warnings


# ────────────────────────────── 저장 파이프라인 ──────────────────────────────


def pending_path(trace_id: str) -> Path:
    return PENDING_EXTRACT_DIR / f"{trace_id}.yaml"


def _queue_structured_review(trace_id: str, extraction: dict, warnings: list[str] | None = None) -> Path:
    ensure_runtime()
    p = pending_path(trace_id)
    if p.exists():
        raise RuntimeError(f"pending extraction already exists for {trace_id}; apply-pending or reject-pending first")
    idx = load_yaml(TRACES_INDEX) or {}
    info = idx.get("traces", {}).get(trace_id, {})
    trace_file = TRACES_DIR / f"{trace_id}.md"
    payload = {
        "trace_id": trace_id,
        "created_at": now_iso(),
        "status": "pending_review",
        "summary": extraction.get("summary", ""),
        "decisions": extraction.get("decisions", []),
        "facts": extraction.get("facts", []),
        "warnings": warnings or [],
        "source": "compression_worker",
        "campaign_id": info.get("campaign"),
        "turn_id": info.get("turn_id"),
        "source_trace": trace_id,
        "source_trace_mtime": trace_file.stat().st_mtime if trace_file.exists() else None,
    }
    with file_lock(p, timeout=5.0):
        save_yaml_atomic(p, payload)
    return p


def _archive_pending(trace_id: str, status: str, reason: str | None = None, actor: str | None = None) -> Path | None:
    src = pending_path(trace_id)
    if not src.exists():
        return None
    data = load_yaml(src) or {}
    data["status"] = status
    data["resolved_at"] = now_iso()
    if reason:
        data["reason"] = reason
    if actor:
        if status == "approved":
            data["approved_by"] = actor
        elif status == "rejected":
            data["rejected_by"] = actor
        else:
            data["resolved_by"] = actor
    dst = PENDING_REVIEW_ARCHIVE / f"{trace_id}-{status}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
    with file_lock(dst, timeout=5.0):
        save_yaml_atomic(dst, data)
    src.unlink(missing_ok=True)
    return dst


def _commit_decisions(trace_id: str, decisions: list[dict], embeddings_store_module) -> int:
    if not decisions:
        return 0
    DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    today = datetime.now().date().isoformat()
    lines.append(f"\n## {today} — trace/{trace_id} 자동 추출\n")
    for d in decisions:
        line = f"- **{d['text']}**"
        if d.get("rationale"):
            line += f"  \n  _근거: {d['rationale']}_"
        lines.append(line)
    with file_lock(DECISIONS_FILE):
        with open(DECISIONS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    for i, d in enumerate(decisions):
        try:
            embeddings_store_module.index_document("decisions", f"{trace_id}-d{i}", d["text"])
        except Exception:
            pass
    return len(decisions)


def _commit_facts(trace_id: str, facts: list[dict], embeddings_store_module) -> int:
    if not facts:
        return 0
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _append_facts(facts, trace_id, embeddings_store_module)
    return len(facts)


def apply_extraction(trace_id: str, extraction: dict, auto_apply_structured: bool = False,
                     warnings: list[str] | None = None) -> dict:
    """검증된 추출 결과를 structured memory에 저장.

    v2.4.5: instincts는 즉시 반영하지만, decisions/facts는 기본적으로
    pending review 큐에 보관한다. (필요 시 --auto-apply-structured 로 즉시 적용)
    """
    result = {
        "trace_id": trace_id,
        "instincts_added": [],
        "instincts_updated": [],
        "decisions_added": 0,
        "facts_added": 0,
        "decisions_pending": 0,
        "facts_pending": 0,
        "pending_review": False,
        "warnings": [],
    }

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import instincts_updater  # noqa: F401
    except ImportError:
        result["warnings"].append("instincts_updater import 실패")

    import embeddings_store

    for inst in extraction["instincts"]:
        inst_id = inst["id"]
        cat = inst["category"]
        inst_path = INSTINCTS_DIR / cat / f"{inst_id}.yaml"
        if inst_path.exists():
            try:
                existing = load_yaml(inst_path) or {}
                existing.setdefault("evidence", []).append({
                    "date": datetime.now().date().isoformat(),
                    "observation": inst["evidence"] or "trace 자동 추출",
                    "type": "confirmation",
                    "source": f"trace/{trace_id}",
                })
                existing["confidence"] = min(0.95, existing.get("confidence", 0.5) + 0.10)
                existing.setdefault("metadata", {})["updated"] = now_iso()
                save_yaml_atomic(inst_path, existing)
                result["instincts_updated"].append(inst_id)
                continue
            except Exception as e:
                result["warnings"].append(f"[{inst_id}] 갱신 실패: {e}")

        inst_path.parent.mkdir(parents=True, exist_ok=True)
        new_instinct = {
            "id": inst_id,
            "category": cat,
            "trigger": {
                "natural": inst["trigger"],
                "keywords": _extract_keywords(inst["trigger"]),
            },
            "action": inst["action"],
            "confidence": inst["confidence"],
            "evidence": [{
                "date": datetime.now().date().isoformat(),
                "observation": inst["evidence"] or "trace 자동 추출",
                "type": "confirmation",
                "source": f"trace/{trace_id}",
            }],
            "tags": inst["tags"],
            "metadata": {
                "created": now_iso(),
                "updated": now_iso(),
                "review_status": "draft",
                "detected_by": ["compression_worker"],
                "source_trace": trace_id,
            },
        }
        try:
            save_yaml_atomic(inst_path, new_instinct)
            try:
                txt = f"{inst['trigger']}\n{inst['action']}\n{inst['evidence']}"
                embeddings_store.index_document("instincts", inst_id, txt)
            except Exception:
                pass
            result["instincts_added"].append(inst_id)
        except Exception as e:
            result["warnings"].append(f"[{inst_id}] 저장 실패: {e}")

    if extraction.get("decisions") or extraction.get("facts"):
        if auto_apply_structured:
            result["decisions_added"] = _commit_decisions(trace_id, extraction.get("decisions", []), embeddings_store)
            result["facts_added"] = _commit_facts(trace_id, extraction.get("facts", []), embeddings_store)
        else:
            p = _queue_structured_review(trace_id, extraction, warnings=warnings)
            result["pending_review"] = True
            result["pending_file"] = str(p)
            result["decisions_pending"] = len(extraction.get("decisions", []))
            result["facts_pending"] = len(extraction.get("facts", []))

    if extraction.get("summary"):
        try:
            with read_modify_write(TRACES_INDEX) as idx:
                if trace_id in idx.get("traces", {}):
                    idx["traces"][trace_id]["compressed_summary"] = extraction["summary"]
                    idx["traces"][trace_id]["compressed_at"] = now_iso()
                    idx["traces"][trace_id]["structured_pending"] = bool(result["pending_review"])
        except Exception as e:
            result["warnings"].append(f"인덱스 summary 갱신 실패: {e}")

    return result


def cmd_list_pending(args):
    ensure_runtime()
    items = []
    for p in sorted(PENDING_EXTRACT_DIR.glob("*.yaml"), key=lambda x: x.stat().st_mtime, reverse=True):
        data = load_yaml(p) or {}
        items.append({
            "trace_id": data.get("trace_id", p.stem),
            "created_at": data.get("created_at"),
            "decisions": len(data.get("decisions", [])),
            "facts": len(data.get("facts", [])),
            "summary": (data.get("summary") or "")[:120],
            "path": str(p),
        })
    if args.format == "json":
        print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("보류 중인 structured review 없음")
        return
    print(f"보류 중인 structured review: {len(items)}건")
    for item in items[: args.limit]:
        print(f"- {item['trace_id']}  decisions={item['decisions']} facts={item['facts']}  {item['created_at']}")
        if item["summary"]:
            print(f"    {item['summary']}")


def cmd_apply_pending(args):
    ensure_runtime()
    p = pending_path(args.trace_id)
    if not p.exists():
        sys.stderr.write(f"❌ pending extraction 없음: {args.trace_id}\n")
        sys.exit(1)
    if not args.approved_by:
        sys.stderr.write("❌ --approved-by 가 필요합니다.\n")
        sys.exit(1)
    data = load_yaml(p) or {}
    import embeddings_store
    decisions_added = _commit_decisions(args.trace_id, data.get("decisions", []), embeddings_store)
    facts_added = _commit_facts(args.trace_id, data.get("facts", []), embeddings_store)
    arch = _archive_pending(args.trace_id, "approved", reason=args.reason, actor=args.approved_by)
    try:
        with read_modify_write(TRACES_INDEX) as idx:
            if args.trace_id in idx.get("traces", {}):
                idx["traces"][args.trace_id]["structured_pending"] = False
                idx["traces"][args.trace_id]["structured_reviewed_at"] = now_iso()
                idx["traces"][args.trace_id]["structured_reviewed_by"] = args.approved_by
    except Exception:
        pass
    out = {"trace_id": args.trace_id, "decisions_added": decisions_added, "facts_added": facts_added, "approved_by": args.approved_by, "archived_to": str(arch) if arch else None, "status": "approved"}
    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"✅ pending extraction 승인: {args.trace_id}")
    print(f"   decisions: {decisions_added}건")
    print(f"   facts:     {facts_added}건")
    print(f"   approved:  {args.approved_by}")


def cmd_reject_pending(args):
    ensure_runtime()
    p = pending_path(args.trace_id)
    if not p.exists():
        sys.stderr.write(f"❌ pending extraction 없음: {args.trace_id}\n")
        sys.exit(1)
    if not args.rejected_by:
        sys.stderr.write("❌ --rejected-by 가 필요합니다.\n")
        sys.exit(1)
    arch = _archive_pending(args.trace_id, "rejected", reason=args.reason, actor=args.rejected_by)
    try:
        with read_modify_write(TRACES_INDEX) as idx:
            if args.trace_id in idx.get("traces", {}):
                idx["traces"][args.trace_id]["structured_pending"] = False
                idx["traces"][args.trace_id]["structured_reviewed_at"] = now_iso()
                idx["traces"][args.trace_id]["structured_rejected_by"] = args.rejected_by
    except Exception:
        pass
    out = {"trace_id": args.trace_id, "status": "rejected", "reason": args.reason, "rejected_by": args.rejected_by, "archived_to": str(arch) if arch else None}
    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"🗑️ pending extraction 반려: {args.trace_id}")
    print(f"   rejected:  {args.rejected_by}")
    if args.reason:
        print(f"   이유: {args.reason}")


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    """간단한 키워드 추출 — 단어 길이·빈도 기반."""
    tokens = re.findall(r"[\w가-힣]{3,}", text, re.UNICODE)
    # 불용어 기본
    STOP = {"the", "and", "for", "with", "when", "that", "this", "has",
            "이것", "그것", "저것", "있다", "없다", "한다", "된다"}
    seen = []
    for t in tokens:
        tl = t.lower()
        if tl in STOP or tl in seen:
            continue
        seen.append(tl)
        if len(seen) >= limit:
            break
    return seen


def _append_facts(facts: list, trace_id: str, embeddings_store_module):
    """Facts를 domain-facts.md에 topic별로 그룹화해서 append."""
    # 기존 facts 읽기
    existing = FACTS_FILE.read_text(encoding="utf-8") if FACTS_FILE.exists() else ""

    # topic별로 그룹화
    from collections import defaultdict
    new_by_topic = defaultdict(list)
    for f in facts:
        new_by_topic[f["topic"]].append(f["content"])

    # 기존에 해당 topic 섹션 있으면 그 뒤에 추가, 없으면 끝에 추가
    lines = existing.splitlines() if existing else []
    result_lines = list(lines)

    for topic, contents in new_by_topic.items():
        # "## topic" 섹션 찾기
        section_idx = None
        for i, line in enumerate(result_lines):
            if line.strip().lower() == f"## {topic.lower()}":
                section_idx = i
                break

        if section_idx is not None:
            # 해당 섹션 끝에 삽입
            insert_at = len(result_lines)
            for j in range(section_idx + 1, len(result_lines)):
                if result_lines[j].startswith("## "):
                    insert_at = j
                    break
            for c in contents:
                result_lines.insert(insert_at, f"- {c}  _(trace/{trace_id})_")
                insert_at += 1
        else:
            # 새 섹션 추가
            if result_lines and not result_lines[-1].strip() == "":
                result_lines.append("")
            result_lines.append(f"## {topic}")
            for c in contents:
                result_lines.append(f"- {c}  _(trace/{trace_id})_")

    with file_lock(FACTS_FILE):
        atomic_write(FACTS_FILE, "\n".join(result_lines) + "\n")

    # 임베딩 색인
    for i, f in enumerate(facts):
        try:
            embeddings_store_module.index_document(
                "facts", f"{trace_id}-f{i}",
                f"{f['topic']}: {f['content']}")
        except Exception:
            pass


# ────────────────────────────── 큐 관리 ──────────────────────────────


def enqueue_for_retry(trace_id: str, reason: str,
                      llm_response: str = ""):
    ensure_runtime()
    q_file = COMPRESSION_QUEUE / f"{trace_id}.yaml"
    data = {
        "trace_id": trace_id,
        "enqueued_at": now_iso(),
        "reason": reason,
        "retry_count": 0,
    }
    if q_file.exists():
        existing = load_yaml(q_file) or {}
        data["retry_count"] = existing.get("retry_count", 0) + 1
    with file_lock(q_file):
        save_yaml_atomic(q_file, data)

    if llm_response:
        # 원본 응답 보존
        raw_file = RAW_RESPONSES / f"{trace_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        atomic_write(raw_file, llm_response)


def remove_from_queue(trace_id: str):
    q_file = COMPRESSION_QUEUE / f"{trace_id}.yaml"
    if q_file.exists():
        q_file.unlink()


# ────────────────────────────── 토큰 사용량 기록 ──────────────────────────────


def log_token_usage(trace_id: str, estimated_tokens: int, status: str):
    ensure_runtime()
    today = datetime.now().date().isoformat()
    with read_modify_write(TOKEN_USAGE_FILE) as data:
        data.setdefault("daily", {}).setdefault(today, {"compressions": 0,
                                                          "tokens": 0})
        data["daily"][today]["compressions"] += 1
        data["daily"][today]["tokens"] += estimated_tokens
        data.setdefault("history", []).append({
            "timestamp": now_iso(),
            "trace_id": trace_id,
            "tokens": estimated_tokens,
            "status": status,
        })
        # 히스토리 최근 1000개만 보존
        if len(data["history"]) > 1000:
            data["history"] = data["history"][-800:]


def log_compression(entry: dict):
    ensure_runtime()
    with read_modify_write(COMPRESSION_LOG) as data:
        data.setdefault("entries", []).append(entry)
        if len(data["entries"]) > 500:
            data["entries"] = data["entries"][-400:]


# ────────────────────────────── 메인 압축 ──────────────────────────────


def compress_trace(trace_id: str, llm_backend: str = "claude",
                   timeout: float = 60.0, dry_run: bool = False,
                   auto_apply_structured: bool = False) -> dict:
    """한 trace를 압축. 핵심 엔트리포인트.

    llm_backend: "claude" | "codex" | "mock"
    """
    if not trace_exists(trace_id):
        return {"status": "error", "reason": f"trace 없음: {trace_id}"}

    prompt = build_prompt(trace_id)
    if not prompt:
        return {"status": "error", "reason": "프롬프트 생성 실패"}

    if dry_run:
        return {"status": "dry_run", "prompt_length": len(prompt),
                "prompt_preview": prompt[:500]}

    # LLM 호출
    if llm_backend == "claude":
        response = call_claude_cli(prompt, timeout=timeout, use_cache=True)
    elif llm_backend == "codex":
        response = call_codex_cli(prompt, timeout=timeout, use_cache=True)
    elif llm_backend == "mock":
        # 테스트용: 환경변수에서 응답 읽기
        import os
        response = os.environ.get("MOCK_LLM_RESPONSE", "")
    else:
        return {"status": "error", "reason": f"unknown backend: {llm_backend}"}

    estimated_tokens = (len(prompt) + len(response)) // 4  # 대략 4자/토큰

    if not response:
        enqueue_for_retry(trace_id, "LLM 응답 비어있음")
        log_token_usage(trace_id, estimated_tokens, "failed_no_response")
        return {"status": "queued", "reason": "LLM 응답 실패, 재시도 큐에 등록"}

    # YAML 추출
    yaml_text = extract_yaml_from_response(response)
    if not yaml_text:
        enqueue_for_retry(trace_id, "YAML 추출 실패", llm_response=response)
        log_token_usage(trace_id, estimated_tokens, "parse_failed")
        return {"status": "queued", "reason": "YAML 파싱 실패, 원본은 _raw_llm_responses에 보존"}

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        enqueue_for_retry(trace_id, f"YAML 로드 실패: {e}",
                          llm_response=response)
        log_token_usage(trace_id, estimated_tokens, "yaml_error")
        return {"status": "queued", "reason": f"YAML 오류: {e}"}

    # 검증
    extraction, warnings = validate_extraction(data)

    # 🆕 추출이 완전히 비었으면 queued (LLM이 의미 있는 응답 실패)
    if (not extraction["instincts"] and not extraction["decisions"]
            and not extraction["facts"] and not extraction["summary"]):
        enqueue_for_retry(trace_id, "empty extraction (no valid content)",
                          llm_response=response)
        log_token_usage(trace_id, estimated_tokens, "empty_extraction")
        return {"status": "queued",
                "reason": "LLM 응답에 구조화 가능한 내용 없음 (YAML은 파싱됐으나 유효 필드 없음)"}

    # 저장
    save_result = apply_extraction(trace_id, extraction, auto_apply_structured=auto_apply_structured, warnings=warnings)
    save_result["warnings"] = (save_result.get("warnings", []) + warnings)

    remove_from_queue(trace_id)
    log_token_usage(trace_id, estimated_tokens, "success")
    log_compression({
        "timestamp": now_iso(),
        "trace_id": trace_id,
        "backend": llm_backend,
        "tokens_estimate": estimated_tokens,
        "instincts_added": len(save_result.get("instincts_added", [])),
        "instincts_updated": len(save_result.get("instincts_updated", [])),
        "decisions_added": save_result.get("decisions_added", 0),
        "facts_added": save_result.get("facts_added", 0),
        "summary": extraction.get("summary", ""),
    })

    return {"status": "success", **save_result,
            "summary": extraction["summary"],
            "tokens_estimate": estimated_tokens}


# ────────────────────────────── 명령 함수들 ──────────────────────────────


def cmd_compress(args):
    result = compress_trace(args.trace_id, llm_backend=args.backend,
                            timeout=args.timeout, dry_run=False,
                            auto_apply_structured=args.auto_apply_structured)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    status = result.get("status", "unknown")
    if status == "success":
        print(f"✅ 압축 성공: {args.trace_id}")
        print(f"   요약:         {result.get('summary', '')}")
        print(f"   instincts:    신규 {len(result.get('instincts_added', []))}건, "
              f"갱신 {len(result.get('instincts_updated', []))}건")
        if result.get('pending_review'):
            print(f"   structured:   보류 review {result.get('decisions_pending', 0)} decisions / {result.get('facts_pending', 0)} facts")
            print(f"   승인:         python scripts/compression_worker.py apply-pending {args.trace_id} --approved-by pair-lead")
        else:
            print(f"   decisions:    {result.get('decisions_added', 0)}건 추가")
            print(f"   facts:        {result.get('facts_added', 0)}건 추가")
        print(f"   토큰 (추정):  {result.get('tokens_estimate', 0)}")
        if result.get("warnings"):
            print(f"   ⚠️  경고 {len(result['warnings'])}건:")
            for w in result["warnings"][:5]:
                print(f"       - {w}")
    elif status == "queued":
        print(f"⚠️  큐에 등록됨: {args.trace_id}")
        print(f"   이유: {result.get('reason')}")
        print(f"   → 나중에 `retry-queue` 로 재시도")
    else:
        print(f"❌ 실패: {result.get('reason')}")


def cmd_dry_run(args):
    result = compress_trace(args.trace_id, dry_run=True)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"프롬프트 길이: {result.get('prompt_length', 0)}자")
        print("━━━ 미리보기 (처음 500자) ━━━")
        print(result.get("prompt_preview", ""))


def cmd_show_prompt(args):
    prompt = build_prompt(args.trace_id)
    if not prompt:
        sys.stderr.write(f"❌ prompt 생성 실패\n")
        sys.exit(1)
    print(prompt)


def cmd_retry_queue(args):
    ensure_runtime()
    if not COMPRESSION_QUEUE.exists():
        print("큐 없음")
        return
    queued = list(COMPRESSION_QUEUE.glob("*.yaml"))
    if not queued:
        print("큐 비어있음")
        return

    print(f"대기 중: {len(queued)}건\n")
    success = 0
    for q_file in queued:
        qdata = load_yaml(q_file) or {}
        tid = qdata.get("trace_id", q_file.stem)
        retry_count = qdata.get("retry_count", 0)
        if retry_count >= args.max_retries:
            print(f"  ⏭  {tid} (재시도 {retry_count}회 초과, 스킵)")
            continue
        print(f"  ⏳ {tid} 재시도 중...")
        result = compress_trace(tid, llm_backend=args.backend,
                                timeout=args.timeout, auto_apply_structured=args.auto_apply_structured)
        if result.get("status") == "success":
            print(f"      ✅ 성공")
            success += 1
        else:
            print(f"      ⚠️  {result.get('reason')}")

    print(f"\n완료: {success}/{len(queued)}")


def cmd_stats(args):
    ensure_runtime()
    log = load_yaml(COMPRESSION_LOG) or {}
    usage = load_yaml(TOKEN_USAGE_FILE) or {}
    entries = log.get("entries", [])

    if args.format == "json":
        print(json.dumps({
            "total_compressions": len(entries),
            "daily_usage": usage.get("daily", {}),
            "recent": entries[-10:],
        }, ensure_ascii=False, indent=2))
        return

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 Compression 통계")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"총 압축 수행: {len(entries)}건")

    daily = usage.get("daily", {})
    if daily:
        today = datetime.now().date().isoformat()
        today_data = daily.get(today, {})
        print(f"오늘: {today_data.get('compressions', 0)}건, "
              f"{today_data.get('tokens', 0)} 토큰 (추정)")
        print(f"\n최근 7일 토큰 사용:")
        sorted_days = sorted(daily.items(), reverse=True)[:7]
        for day, d in sorted_days:
            bar = "█" * min(d.get("tokens", 0) // 1000, 30)
            print(f"  {day}  {d.get('tokens', 0):>8d} tok  {bar}")

    # 큐
    queue_size = len(list(COMPRESSION_QUEUE.glob("*.yaml"))) if COMPRESSION_QUEUE.exists() else 0
    pending_size = len(list(PENDING_EXTRACT_DIR.glob("*.yaml"))) if PENDING_EXTRACT_DIR.exists() else 0
    print(f"\n재시도 큐: {queue_size}건 대기")
    print(f"structured review 대기: {pending_size}건")


# ────────────────────────────── argparse ──────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(description="Compression Worker — trace → structured")
    sub = p.add_subparsers(dest="cmd", required=True)

    cp = sub.add_parser("compress", help="trace 압축 (LLM 호출)")
    cp.add_argument("trace_id")
    cp.add_argument("--backend", choices=["claude", "codex", "mock"],
                    default="claude")
    cp.add_argument("--timeout", type=float, default=60.0)
    cp.add_argument("--format", choices=["text", "json"], default="text")
    cp.add_argument("--auto-apply-structured", action="store_true", help="decisions/facts도 즉시 반영 (기본: pending review)")

    dp = sub.add_parser("dry-run", help="프롬프트만 확인, 호출 안 함")
    dp.add_argument("trace_id")
    dp.add_argument("--format", choices=["text", "json"], default="text")

    spp = sub.add_parser("show-prompt", help="완성된 프롬프트 출력")
    spp.add_argument("trace_id")

    rp = sub.add_parser("retry-queue", help="실패 대기 중인 trace 재시도")
    rp.add_argument("--backend", choices=["claude", "codex"], default="claude")
    rp.add_argument("--timeout", type=float, default=60.0)
    rp.add_argument("--max-retries", type=int, default=3)
    rp.add_argument("--auto-apply-structured", action="store_true", help="decisions/facts도 즉시 반영")

    lp = sub.add_parser("list-pending", help="보류 중인 structured review 목록")
    lp.add_argument("--limit", type=int, default=20)
    lp.add_argument("--format", choices=["text", "json"], default="text")

    ap = sub.add_parser("apply-pending", help="보류 중인 structured review 승인 반영")
    ap.add_argument("trace_id")
    ap.add_argument("--approved-by", required=True)
    ap.add_argument("--reason", default="review approved")
    ap.add_argument("--format", choices=["text", "json"], default="text")

    rp2 = sub.add_parser("reject-pending", help="보류 중인 structured review 반려")
    rp2.add_argument("trace_id")
    rp2.add_argument("--rejected-by", required=True)
    rp2.add_argument("--reason", default="review rejected")
    rp2.add_argument("--format", choices=["text", "json"], default="text")

    sub.add_parser("stats", help="압축 이력·토큰 사용량").add_argument(
        "--format", choices=["text", "json"], default="text")

    return p


def main():
    args = build_parser().parse_args()
    dispatch = {
        "compress": cmd_compress,
        "dry-run": cmd_dry_run,
        "show-prompt": cmd_show_prompt,
        "retry-queue": cmd_retry_queue,
        "list-pending": cmd_list_pending,
        "apply-pending": cmd_apply_pending,
        "reject-pending": cmd_reject_pending,
        "stats": cmd_stats,
    }
    fn = dispatch.get(args.cmd)
    if not fn:
        sys.stderr.write(f"❌ 명령 없음: {args.cmd}\n")
        sys.exit(1)
    fn(args)


_FALLBACK_PROMPT = """당신은 연구 프로젝트의 로그를 구조화된 지식으로 추출합니다.
아래 trace를 읽고 YAML 형식으로만 반환하세요.

형식:
summary: "한 줄 요약"
instincts: []
decisions: []
facts: []

<trace>
{{TRACE_CONTENT}}
</trace>

YAML만 반환."""


if __name__ == "__main__":
    main()
