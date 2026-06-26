#!/usr/bin/env python3
"""
harness_common.py — 공용 유틸리티: 파일 락·원자적 쓰기·YAML I/O

병렬 에이전트가 안전하게 같은 파일에 쓰기 위한 최소 인프라.

제공 기능:
  file_lock(path)            — 크로스플랫폼 락 (mkdir 기반, 0 의존성)
  atomic_write(path, text)   — write temp + fsync + rename
  save_yaml_atomic(path, d)  — 원자적 YAML 저장
  load_yaml(path)            — YAML 안전 로드 (없으면 {} 반환)
  read_modify_write(path)    — 락 + 로드 + 수정 + 원자적 저장 (context manager)
  append_line_atomic(p, ln)  — 로그 스타일 append (JSONL 등)

동시성 보장:
  - 같은 파일 경로에 대한 동시 쓰기는 직렬화됨
  - 쓰기 도중 프로세스 중단 시에도 부분 손상 없음 (rename은 원자적)
  - 60초 이상 점유된 락은 stale로 간주하고 강제 해제
  - stdlib만 사용 (PyYAML 제외)

한계:
  - NFS 등 일부 분산 파일시스템에서는 mkdir atomicity가 약해질 수 있음
    → 로컬 디스크 사용을 권장
  - Python 프로세스 내 멀티스레드는 GIL 덕에 이미 안전
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

try:
    import yaml
    HAS_YAML = True
except ImportError:
    import json
    HAS_YAML = False


# 하네스 표준 디렉토리 (session_logger 등이 import). 정의 누락 시 session_logger가
# fallback(no-op file_lock)로 떨어져 로그 잠금이 사라지므로 반드시 export.
CLAUDE_DIR = Path(".claude")


# ────────────────────────────── 파일 락 ──────────────────────────────

_DEFAULT_TIMEOUT = 10.0
_DEFAULT_STALE_AFTER = 60.0
_BACKOFF_INITIAL = 0.02
_BACKOFF_MAX = 0.25


@contextmanager
def file_lock(
    resource_path: Path,
    timeout: float = _DEFAULT_TIMEOUT,
    stale_after: float = _DEFAULT_STALE_AFTER,
    verbose: bool = False,
) -> Iterator[None]:
    """
    파일/경로에 대한 배타 락을 획득한다.

    원리:
      mkdir()는 POSIX·Windows 모두에서 원자적이며, 같은 이름이 이미 있으면
      FileExistsError를 던진다. 이 특성으로 spin-lock을 구현한다.

    파라미터:
      resource_path : 락이 보호하는 실제 파일 경로 (존재할 필요 없음)
      timeout       : 최대 대기 시간 (초). 초과 시 TimeoutError.
      stale_after   : 이 시간을 초과한 락 디렉토리는 죽은 프로세스로 간주.
      verbose       : stale 락 제거 시 경고 출력.

    사용:
      with file_lock(Path("data.yaml")):
          ...  # 이 안에서는 단일 프로세스만 접근 보장
    """
    lock_dir = resource_path.with_suffix(resource_path.suffix + ".lock")
    lock_dir.parent.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    backoff = _BACKOFF_INITIAL
    acquired = False

    while not acquired:
        try:
            lock_dir.mkdir(exist_ok=False)
            # PID 기록 (stale 판단에 참고; 엄격한 PID 추적은 아님)
            try:
                (lock_dir / f"pid-{os.getpid()}").touch()
            except OSError:
                pass
            acquired = True
            break
        except FileExistsError:
            # stale 락 감지
            try:
                age = time.time() - lock_dir.stat().st_mtime
                if age > stale_after:
                    if verbose:
                        sys.stderr.write(
                            f"⚠️  stale lock 제거: {lock_dir.name} ({age:.0f}s old)\n"
                        )
                    _force_remove_lock(lock_dir)
                    continue
            except FileNotFoundError:
                continue  # 방금 다른 프로세스가 해제함

            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    f"파일 락 타임아웃 ({timeout}s): {resource_path}"
                )
            time.sleep(backoff)
            backoff = min(_BACKOFF_MAX, backoff * 1.5)

    try:
        yield
    finally:
        if acquired:
            _force_remove_lock(lock_dir)


def _force_remove_lock(lock_dir: Path):
    """락 디렉토리와 내부 파일을 제거."""
    try:
        for child in lock_dir.iterdir():
            try:
                child.unlink()
            except (FileNotFoundError, OSError):
                pass
        lock_dir.rmdir()
    except (FileNotFoundError, OSError):
        pass


# ────────────────────────────── 원자적 쓰기 ──────────────────────────────


def atomic_write(path: Path, content: str, encoding: str = "utf-8"):
    """
    파일을 원자적으로 쓴다: temp → fsync → rename.

    - 쓰기 중 프로세스가 죽어도 기존 파일은 그대로 보존됨
    - 같은 디렉토리 내 rename은 POSIX·Windows 모두 atomic
    - 리더(read-only)는 락 없이도 일관된 파일을 볼 수 있음
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # PID + 타임스탬프로 tmp 이름 — 동일 락 구간 내에서만 사용되므로 안전하지만
    # 방어적으로 유니크하게
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        with tmp.open("w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (AttributeError, OSError):
                # 일부 플랫폼은 fsync 미지원 — 무시
                pass
        os.replace(tmp, path)  # atomic rename
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def atomic_write_bytes(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        with tmp.open("wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (AttributeError, OSError):
                pass
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


# ────────────────────────────── JSON I/O ──────────────────────────────


def load_json(path: Path, default: dict | None = None) -> dict:
    default = {} if default is None else deepcopy(default)
    if not path.exists():
        return default
    try:
        import json
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception as e:
        sys.stderr.write(f"⚠️  JSON 로드 실패 {path}: {e}\n")
        return default


def save_json_atomic(path: Path, data: dict):
    import json
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@contextmanager
def read_modify_write_json(path: Path, default: dict | None = None, timeout: float = _DEFAULT_TIMEOUT, create_if_missing: bool = True) -> Iterator[dict]:
    if not create_if_missing and not path.exists():
        raise FileNotFoundError(path)
    default = {} if default is None else deepcopy(default)
    with file_lock(path, timeout=timeout):
        data = load_json(path, default=default)
        error_occurred = False
        try:
            yield data
        except Exception:
            error_occurred = True
            raise
        finally:
            if not error_occurred:
                save_json_atomic(path, data)


# ────────────────────────────── YAML I/O ──────────────────────────────


def save_yaml_atomic(path: Path, data: Any):
    """YAML을 원자적으로 저장. PyYAML 없으면 JSON 폴백."""
    if HAS_YAML:
        content = yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )
    else:
        import json
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write(path, content)


def load_yaml(path: Path) -> dict:
    """YAML 안전 로드. 파일 없으면 빈 dict."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            if HAS_YAML:
                return yaml.safe_load(f) or {}
            else:
                import json
                return json.load(f)
    except Exception as e:
        sys.stderr.write(f"⚠️  YAML 로드 실패 {path}: {e}\n")
        return {}


# ────────────────────────────── read-modify-write ──────────────────────────────


@contextmanager
def read_modify_write(
    path: Path,
    timeout: float = _DEFAULT_TIMEOUT,
    create_if_missing: bool = True,
) -> Iterator[dict]:
    """
    락을 획득한 뒤 YAML을 로드, 수정, 원자적 저장.

    사용:
        with read_modify_write(Path("data.yaml")) as data:
            data["counter"] = data.get("counter", 0) + 1
        # 블록 종료 시 자동 저장 + 락 해제

    블록 안에서 예외 발생 시 저장은 스킵되고 락만 해제.
    """
    if not create_if_missing and not path.exists():
        raise FileNotFoundError(path)

    with file_lock(path, timeout=timeout):
        data = load_yaml(path)
        error_occurred = False
        try:
            yield data
        except Exception:
            error_occurred = True
            raise
        finally:
            if not error_occurred:
                save_yaml_atomic(path, data)


# ────────────────────────────── append-only 로그 ──────────────────────────────


def append_line_atomic(path: Path, line: str, encoding: str = "utf-8"):
    """
    파일 끝에 한 줄 append.

    POSIX O_APPEND 플래그는 PIPE_BUF(통상 4096B) 이하 쓰기에 대해 atomic을 보장.
    짧은 JSONL 레코드 append에 적합하며 락이 불필요.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not line.endswith("\n"):
        line = line + "\n"
    # Python의 "a" 모드는 내부적으로 O_APPEND 사용
    with path.open("a", encoding=encoding) as f:
        f.write(line)
        f.flush()


# ────────────────────────────── 유틸 ──────────────────────────────


def now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")



# ────────────────────────────── LLM CLI 헬퍼 (Step 1) ──────────────────────────────

LLM_CACHE_FILE = Path(".claude/runtime/llm_cache.yaml")


def call_claude_cli(prompt: str, timeout: float = 60.0,
                    use_cache: bool = True) -> str:
    """Claude Code CLI를 subprocess로 호출.

    `claude -p "프롬프트"`를 실행하고 stdout을 반환.
    Max 구독료에 포함되므로 별도 API 키 불필요.

    사용 전제:
      - `claude` CLI가 PATH에 있어야 함
      - 로그인된 상태여야 함

    cache: 동일 프롬프트는 응답을 재사용 (LLM 비결정성 완화 + 비용 절감)
    """
    import hashlib, subprocess
    key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    if use_cache:
        cached = _llm_cache_get(key)
        if cached:
            return cached

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode != 0:
            sys.stderr.write(f"⚠️  claude CLI 오류: {result.stderr[:200]}\n")
            return ""
        response = result.stdout.strip()
    except FileNotFoundError:
        sys.stderr.write("⚠️  claude CLI 없음. Claude Code 설치 필요.\n")
        return ""
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"⚠️  claude CLI 타임아웃 ({timeout}s)\n")
        return ""

    if use_cache and response:
        _llm_cache_set(key, prompt[:200], response)
    return response


def call_codex_cli(prompt: str, timeout: float = 60.0,
                   use_cache: bool = True) -> str:
    """Codex CLI subprocess 호출 (교차 검증용).

    `codex exec "프롬프트"` 형태.
    """
    import hashlib, subprocess
    key = "codex-" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    if use_cache:
        cached = _llm_cache_get(key)
        if cached:
            return cached

    try:
        result = subprocess.run(
            ["codex", "exec", prompt],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode != 0:
            sys.stderr.write(f"⚠️  codex CLI 오류: {result.stderr[:200]}\n")
            return ""
        response = result.stdout.strip()
    except FileNotFoundError:
        sys.stderr.write("⚠️  codex CLI 없음.\n")
        return ""
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"⚠️  codex CLI 타임아웃 ({timeout}s)\n")
        return ""

    if use_cache and response:
        _llm_cache_set(key, prompt[:200], response)
    return response


def _llm_cache_get(key: str) -> str | None:
    """LLM 응답 캐시 조회."""
    if not LLM_CACHE_FILE.exists():
        return None
    try:
        cache = load_yaml(LLM_CACHE_FILE)
        entry = (cache.get("entries") or {}).get(key)
        return entry.get("response") if entry else None
    except Exception:
        return None


def _llm_cache_set(key: str, prompt_preview: str, response: str):
    """LLM 응답 캐시 저장 (락 보호)."""
    with file_lock(LLM_CACHE_FILE, timeout=5.0):
        cache = load_yaml(LLM_CACHE_FILE) if LLM_CACHE_FILE.exists() else {}
        cache.setdefault("entries", {})[key] = {
            "prompt_preview": prompt_preview,
            "response": response,
            "cached_at": now_iso(),
        }
        # 캐시 크기 제한 (1000 엔트리)
        entries = cache["entries"]
        if len(entries) > 1000:
            # 오래된 것부터 제거
            sorted_entries = sorted(
                entries.items(),
                key=lambda x: x[1].get("cached_at", ""),
            )
            cache["entries"] = dict(sorted_entries[-800:])
        save_yaml_atomic(LLM_CACHE_FILE, cache)


if __name__ == "__main__":
    # 간단한 self-test
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test.yaml"
        with file_lock(p):
            print("✅ 락 획득/해제 정상")
        save_yaml_atomic(p, {"key": "value", "nested": {"a": 1}})
        assert load_yaml(p) == {"key": "value", "nested": {"a": 1}}
        print("✅ 원자적 쓰기/읽기 정상")
        with read_modify_write(p) as d:
            d["counter"] = d.get("counter", 0) + 1
        assert load_yaml(p)["counter"] == 1
        print("✅ read-modify-write 정상")
        append_line_atomic(p.parent / "log.jsonl", '{"event": "test"}')
        assert (p.parent / "log.jsonl").exists()
        print("✅ append-only 로그 정상")
        print("\n모든 self-test 통과.")
