#!/usr/bin/env python3
"""
embeddings_store.py — 하이브리드 검색 (semantic + BM25)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
개념
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layer 1 (Trace), Layer 2 (Decisions/Facts/Instincts), Layer 3 (Bundle)에서
자유롭게 호출하는 공용 임베딩·검색 엔진.

두 가지 신호를 RRF(Reciprocal Rank Fusion)로 결합:
  - Semantic: sentence-transformers (있으면) / sklearn TF-IDF (폴백)
  - Lexical: 간단한 BM25 (stdlib만 사용, 외부 의존 없음)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
의존성 정책
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Best (권장):    pip install sentence-transformers numpy
Fallback:       pip install scikit-learn numpy     (TF-IDF 자동 사용)
Minimum:        없음 (BM25만 작동, semantic은 비활성)

의존성 없으면 semantic 검색을 조용히 비활성화하고 BM25로만 작동.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파일 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
.claude/embeddings/
├── vectors.npz              # id → float32 array (collection별)
└── bm25_corpus.yaml         # id → 토큰 리스트 (BM25용)

동일 파일에 여러 collection 공존:
  instincts, decisions, facts, traces, trace_sections
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent))
from harness_common import file_lock, save_yaml_atomic, load_yaml, HAS_YAML

# ────────────────────────────── 경로 ──────────────────────────────

EMBEDDINGS_DIR = Path(".claude/embeddings")
VECTORS_FILE = EMBEDDINGS_DIR / "vectors.npz"
BM25_FILE = EMBEDDINGS_DIR / "bm25_corpus.yaml"


# ────────────────────────────── Semantic backends ──────────────────────────────

_SEMANTIC_BACKEND: str | None = None
_SEMANTIC_MODEL = None
_TFIDF_VECTORIZER = None
_TFIDF_CORPUS_VECTORS = None  # sklearn 백엔드용 캐시

# 모듈 로드 시 딱 한 번만 가벼운 감지 (find_spec도 sklearn은 3초+라 생략)
# sentence-transformers: ImportError 여부 체크 (0.01s)
# sklearn: sys.modules에 이미 있으면 OK, 아니면 lazy — 실제 semantic_search 호출 때 확인
_HAS_SENTENCE_TRANSFORMERS = False
try:
    import sentence_transformers  # noqa: F401
    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    pass

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def _init_semantic_backend():
    """가벼운 backend 결정. sklearn import는 실제 search 시점에 lazy."""
    global _SEMANTIC_BACKEND, _SEMANTIC_MODEL

    if _SEMANTIC_BACKEND is not None:
        return

    # 1) sentence-transformers (import 이미 성공했으면 모델 로드 시도)
    if _HAS_SENTENCE_TRANSFORMERS:
        try:
            from sentence_transformers import SentenceTransformer
            try:
                _SEMANTIC_MODEL = SentenceTransformer(
                    "paraphrase-multilingual-MiniLM-L12-v2")
                _SEMANTIC_BACKEND = "sentence-transformers"
                return
            except Exception:
                try:
                    _SEMANTIC_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
                    _SEMANTIC_BACKEND = "sentence-transformers"
                    return
                except Exception:
                    pass
        except Exception:
            pass

    # 2) sklearn은 "아마도 있을 것"이라 가정 — 실패 시 semantic_search에서 fallback
    # sklearn import 자체가 3초+라 여기서 확인 안 함
    _SEMANTIC_BACKEND = "sklearn-tfidf"


def semantic_backend_name() -> str:
    _init_semantic_backend()
    return _SEMANTIC_BACKEND or "none"


def semantic_available() -> bool:
    return semantic_backend_name() != "none"


# ────────────────────────────── Tokenization ──────────────────────────────


_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """간단한 토큰화 — 영단어·한글·숫자. BM25용."""
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


# ────────────────────────────── Embedding 생성 ──────────────────────────────


def generate_embedding(text: str):
    """텍스트 → float 벡터 (numpy array).

    백엔드에 따라 다른 차원:
      sentence-transformers (multilingual MiniLM): 384
      sentence-transformers (all-MiniLM-L6-v2):    384
      sklearn-tfidf:                                가변 (corpus 크기 의존)
      none:                                          None 반환
    """
    if not HAS_NUMPY:
        return None

    _init_semantic_backend()
    if _SEMANTIC_BACKEND == "none":
        return None

    if _SEMANTIC_BACKEND == "sentence-transformers":
        vec = _SEMANTIC_MODEL.encode(text, convert_to_numpy=True,
                                      normalize_embeddings=True)
        return vec.astype("float32")

    # sklearn TF-IDF: corpus 기반이라 단일 텍스트만으로는 벡터화 어려움
    # → 대안: 저장할 때는 원문을 저장하고, 검색할 때 fit_transform으로 처리
    # 여기서는 None을 반환하고 hybrid_search에서 sklearn 경로 사용
    return None


# ────────────────────────────── 벡터 저장소 ──────────────────────────────


def _load_vectors() -> dict:
    """{collection: {id: np.array}} 로드."""
    if not HAS_NUMPY or not VECTORS_FILE.exists():
        return {}
    try:
        data = np.load(VECTORS_FILE, allow_pickle=True)
        out = {}
        for key in data.files:
            # key 형식: "collection::id"
            if "::" not in key:
                continue
            col, item_id = key.split("::", 1)
            out.setdefault(col, {})[item_id] = data[key]
        return out
    except Exception as e:
        sys.stderr.write(f"⚠️  벡터 로드 실패: {e}\n")
        return {}


def _save_vectors(all_vectors: dict):
    """{collection: {id: np.array}} 저장."""
    if not HAS_NUMPY:
        return
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    # 단일 npz로 저장 — key 형식: "collection::id"
    flat = {}
    for col, items in all_vectors.items():
        for item_id, vec in items.items():
            flat[f"{col}::{item_id}"] = vec

    with file_lock(VECTORS_FILE, timeout=10.0):
        # tmp 파일에 먼저 쓰고 rename (atomic)
        tmp = VECTORS_FILE.with_suffix(".npz.tmp")
        np.savez_compressed(tmp, **flat)
        tmp.replace(VECTORS_FILE)


# ────────────────────────────── BM25 corpus ──────────────────────────────


def _load_bm25_corpus() -> dict:
    """{collection: {id: {text: str, tokens: [str]}}}."""
    if not BM25_FILE.exists():
        return {}
    data = load_yaml(BM25_FILE)
    return data.get("collections", {}) if data else {}


def _save_bm25_corpus(corpus: dict):
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with file_lock(BM25_FILE, timeout=10.0):
        save_yaml_atomic(BM25_FILE, {"collections": corpus})


# ────────────────────────────── Index (쓰기 API) ──────────────────────────────


def index_document(collection: str, doc_id: str, text: str):
    """문서를 색인: BM25 corpus + (가능하면) semantic vector.

    collection 예: "instincts", "decisions", "facts", "traces", "trace_sections"
    """
    # 1. BM25 corpus 갱신
    corpus = _load_bm25_corpus()
    corpus.setdefault(collection, {})[doc_id] = {
        "text": text[:5000],  # 너무 길면 자름
        "tokens": tokenize(text),
    }
    _save_bm25_corpus(corpus)

    # 2. Semantic 벡터 (가능한 경우)
    vec = generate_embedding(text)
    if vec is not None:
        all_vec = _load_vectors()
        all_vec.setdefault(collection, {})[doc_id] = vec
        _save_vectors(all_vec)


def remove_document(collection: str, doc_id: str):
    """색인에서 제거."""
    corpus = _load_bm25_corpus()
    if collection in corpus and doc_id in corpus[collection]:
        del corpus[collection][doc_id]
        _save_bm25_corpus(corpus)

    all_vec = _load_vectors()
    if collection in all_vec and doc_id in all_vec[collection]:
        del all_vec[collection][doc_id]
        _save_vectors(all_vec)


# ────────────────────────────── BM25 검색 ──────────────────────────────


def bm25_search(query: str, collection: str, top_k: int = 10) -> list[tuple[str, float]]:
    """단순 BM25 (stdlib만). k1=1.5, b=0.75 기본값.

    Returns [(doc_id, score), ...] 내림차순.
    """
    corpus = _load_bm25_corpus()
    docs = corpus.get(collection, {})
    if not docs:
        return []

    query_tokens = set(tokenize(query))
    if not query_tokens:
        return []

    # 파라미터
    k1, b = 1.5, 0.75

    # 문서 통계
    doc_lengths = {did: len(d.get("tokens", [])) for did, d in docs.items()}
    if not doc_lengths:
        return []
    avgdl = sum(doc_lengths.values()) / len(doc_lengths)
    N = len(docs)

    # IDF 계산
    term_doc_count = {}
    for term in query_tokens:
        count = sum(1 for d in docs.values() if term in d.get("tokens", []))
        if count > 0:
            term_doc_count[term] = count

    scores = []
    for did, d in docs.items():
        tokens = d.get("tokens", [])
        if not tokens:
            continue
        dl = doc_lengths[did]
        score = 0.0
        token_counts = {}
        for t in tokens:
            token_counts[t] = token_counts.get(t, 0) + 1

        for term in query_tokens:
            if term not in term_doc_count:
                continue
            tf = token_counts.get(term, 0)
            if tf == 0:
                continue
            idf = math.log(1 + (N - term_doc_count[term] + 0.5) /
                            (term_doc_count[term] + 0.5))
            denom = tf + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf * (k1 + 1)) / denom

        if score > 0:
            scores.append((did, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


# ────────────────────────────── Semantic 검색 ──────────────────────────────


def semantic_search(query: str, collection: str,
                    top_k: int = 10) -> list[tuple[str, float]]:
    """Semantic 검색. 백엔드에 따라 동작."""
    _init_semantic_backend()

    if _SEMANTIC_BACKEND == "sentence-transformers":
        return _semantic_search_st(query, collection, top_k)
    elif _SEMANTIC_BACKEND == "sklearn-tfidf":
        return _semantic_search_sklearn(query, collection, top_k)
    else:
        return []


def _semantic_search_st(query: str, collection: str,
                        top_k: int) -> list[tuple[str, float]]:
    """sentence-transformers: 저장된 벡터와 cosine similarity."""
    if not HAS_NUMPY:
        return []
    all_vec = _load_vectors()
    vectors = all_vec.get(collection, {})
    if not vectors:
        return []

    q_vec = generate_embedding(query)
    if q_vec is None:
        return []

    results = []
    for did, doc_vec in vectors.items():
        # normalize_embeddings=True로 저장했으니 dot == cosine
        sim = float(np.dot(q_vec, doc_vec))
        results.append((did, sim))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def _semantic_search_sklearn(query: str, collection: str,
                             top_k: int) -> list[tuple[str, float]]:
    """sklearn TF-IDF: corpus 전체를 fit_transform, cosine similarity."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return []

    corpus = _load_bm25_corpus()
    docs = corpus.get(collection, {})
    if not docs:
        return []

    ids = list(docs.keys())
    texts = [docs[i].get("text", "") for i in ids]

    # tokenizer: 한글 포함 지원
    vectorizer = TfidfVectorizer(tokenizer=tokenize, lowercase=False,
                                  token_pattern=None)
    try:
        doc_matrix = vectorizer.fit_transform(texts)
        query_matrix = vectorizer.transform([query])
        sims = cosine_similarity(query_matrix, doc_matrix).flatten()
    except Exception as e:
        sys.stderr.write(f"⚠️  TF-IDF 검색 실패: {e}\n")
        return []

    results = [(ids[i], float(sims[i])) for i in range(len(ids)) if sims[i] > 0]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


# ────────────────────────────── Hybrid search (RRF fusion) ──────────────────────────────


def hybrid_search(query: str, collection: str, top_k: int = 10,
                  semantic_weight: float = 0.5,
                  rrf_k: int = 60) -> list[tuple[str, float, dict]]:
    """Semantic + BM25 → Reciprocal Rank Fusion.

    semantic_weight: 0 = BM25만, 1 = semantic만, 0.5 = 동등
    rrf_k: RRF 상수 (기본 60)

    Returns [(doc_id, fused_score, debug_dict), ...]
    """
    # 각 signal에서 후보 획득
    k_each = top_k * 3  # fusion 전 더 많이 가져옴

    bm25_results = bm25_search(query, collection, top_k=k_each)
    semantic_results = semantic_search(query, collection, top_k=k_each)

    # RRF: score = sum(weight / (rrf_k + rank))
    fused = {}
    debug = {}

    for rank, (did, score) in enumerate(bm25_results, start=1):
        w = 1.0 - semantic_weight
        fused[did] = fused.get(did, 0) + w / (rrf_k + rank)
        debug.setdefault(did, {})["bm25_rank"] = rank
        debug[did]["bm25_score"] = score

    for rank, (did, score) in enumerate(semantic_results, start=1):
        w = semantic_weight
        fused[did] = fused.get(did, 0) + w / (rrf_k + rank)
        debug.setdefault(did, {})["semantic_rank"] = rank
        debug[did]["semantic_score"] = score

    # 정렬
    sorted_results = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return [(did, score, debug.get(did, {})) for did, score in sorted_results[:top_k]]


# ────────────────────────────── 디버그 / 통계 ──────────────────────────────


def stats() -> dict:
    """인덱스 현황."""
    corpus = _load_bm25_corpus()
    all_vec = _load_vectors() if HAS_NUMPY else {}
    result = {
        "semantic_backend": semantic_backend_name(),
        "numpy_available": HAS_NUMPY,
        "collections": {},
    }
    for col in set(list(corpus.keys()) + list(all_vec.keys())):
        result["collections"][col] = {
            "bm25_docs": len(corpus.get(col, {})),
            "semantic_vecs": len(all_vec.get(col, {})),
        }
    return result


if __name__ == "__main__":
    # Self-test
    import json
    print("━━━ 인덱스 상태 ━━━")
    print(json.dumps(stats(), indent=2, ensure_ascii=False))

    print("\n━━━ 샘플 데이터 색인 ━━━")
    samples = [
        ("sar-phase", "SAR 위상 언래핑은 InSAR 처리의 핵심 단계"),
        ("InSAR 위상 언래핑", "InSAR 위상 언래핑 라이브러리는 phase unwrapping에 쓰이지만 coherence가 낮으면 실패"),
        ("ml-classification", "머신러닝 분류기는 레이블 불균형에 민감"),
        ("reproducibility", "재현성을 위해 seed를 고정해야 한다"),
    ]
    for did, text in samples:
        index_document("test", did, text)
        print(f"  ✅ indexed: {did}")

    print("\n━━━ BM25 검색: 'phase unwrapping' ━━━")
    for did, score in bm25_search("phase unwrapping", "test"):
        print(f"  {score:.3f}  {did}")

    print("\n━━━ BM25 검색 (한영 혼용): '위상 언래핑' ━━━")
    for did, score in bm25_search("위상 언래핑", "test"):
        print(f"  {score:.3f}  {did}")

    print(f"\n━━━ Semantic 백엔드: {semantic_backend_name()} ━━━")
    if semantic_available():
        print("━━━ Semantic 검색: 'phase unwrapping' ━━━")
        for did, score in semantic_search("phase unwrapping", "test"):
            print(f"  {score:.3f}  {did}")

        print("\n━━━ Hybrid 검색: 'phase unwrapping' ━━━")
        for did, score, dbg in hybrid_search("phase unwrapping", "test"):
            print(f"  {score:.4f}  {did}  {dbg}")
    else:
        print("  (semantic 백엔드 없음, BM25만 작동)")
