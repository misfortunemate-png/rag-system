"""
Agent tools: search_chunks (hybrid: dense + BM25 + RRF + rerank) and read_section.

TOOLS: provider-agnostic tool definitions for passing to LLM adapters.
"""
import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CHROMA_DIR = Path("data/chroma")
CHUNKS_JSONL = Path("data/chunks.jsonl")
BM25_INDEX_PATH = Path("data/bm25_index.pkl")
COLLECTION_NAME = "kitei_spec"
MODEL_NAME = "cl-nagoya/ruri-v3-310m"
RERANKER_MODEL_NAME = "cl-nagoya/ruri-v3-reranker-310m"

# Query-side prefix for ruri-v3-310m.
# Source: cl-nagoya/ruri-v3-310m HuggingFace model card (verified 2026-08-04).
QUERY_PREFIX = "クエリ: "
RERANK_QUERY_PREFIX = "検索クエリ: "

TOOLS = [
    {
        "name": "search_chunks",
        "description": (
            "条文テキストをハイブリッド検索（密ベクトル＋BM25＋リランキング）し、関連チャンクを返す。"
            "返値には chunk_id, hierarchy, heading, body, pages, domain, refs が含まれる。"
            "refsは本文中に出現する他条文・表への参照先。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索クエリ（日本語）"},
                "domain": {
                    "type": "string",
                    "description": "系統フィルタ（建築/電気/機械 等）。省略で全系統対象",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返す件数（デフォルト5）",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_section",
        "description": (
            "条番号または階層パスで条文全文を返す。"
            "hierarchy には '1.7.3' のような条番号、または '第2編/第1章/第3節/1.7.3' のような完全パスを指定する。"
            "部分一致（末尾一致）で検索するため条番号のみでも機能する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_slug": {
                    "type": "string",
                    "description": "文書スラッグ（例: denki-setsubi）",
                },
                "hierarchy": {
                    "type": "string",
                    "description": "条番号（例: 1.7.3）または完全階層パス",
                },
            },
            "required": ["doc_slug", "hierarchy"],
        },
    },
]


_embed_model = None
_chroma_client = None
_chroma_col = None
_bm25_data = None  # (bm25, chunk_ids, chunk_domains, chunk_doc_types)
_reranker = None
_init_lock = threading.Lock()


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        with _init_lock:
            if _embed_model is None:
                from sentence_transformers import SentenceTransformer

                _embed_model = SentenceTransformer(MODEL_NAME)
    return _embed_model


def _get_chroma_col():
    global _chroma_client, _chroma_col
    if _chroma_col is None:
        with _init_lock:
            if _chroma_col is None:
                import chromadb

                _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
                _chroma_col = _chroma_client.get_collection(COLLECTION_NAME)
    return _chroma_col


def _get_bm25_data():
    global _bm25_data
    if _bm25_data is None:
        with _init_lock:
            if _bm25_data is None and BM25_INDEX_PATH.exists():
                from src.bm25_index import load_index
                bm25, ids, domains, doc_types = load_index(BM25_INDEX_PATH)
                _bm25_data = (bm25, ids, domains, doc_types)
    return _bm25_data


def _get_reranker():
    global _reranker
    if _reranker is None:
        with _init_lock:
            if _reranker is None:
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker


def _load_rrf_settings() -> dict:
    settings_path = Path("settings.json")
    defaults = {
        "rrf_alpha": 0.5,
        "rrf_beta": 0.5,
        "rrf_k": 60,
        "rerank_candidates": 50,
        "rerank_enabled": True,
    }
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            for k in defaults:
                if k in data:
                    defaults[k] = data[k]
        except Exception:
            pass
    return defaults


def _rrf_fusion(
    dense_ranked: list[str],
    bm25_ranked: list[str],
    alpha: float,
    beta: float,
    k: int,
) -> list[str]:
    scores: dict[str, float] = {}
    for rank, cid in enumerate(dense_ranked, 1):
        scores[cid] = scores.get(cid, 0.0) + alpha / (k + rank)
    for rank, cid in enumerate(bm25_ranked, 1):
        scores[cid] = scores.get(cid, 0.0) + beta / (k + rank)
    return [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


def _parse_domains_filter(domains: list[str] | None) -> tuple[set[str] | None, bool]:
    """Parse domains list into (allowed_domain_set, allow_law).

    Returns (None, True) when no filtering needed (all domains).
    """
    if domains is None:
        return None, True

    allowed = set()
    allow_law = False
    for d in domains:
        if d == "法令":
            allow_law = True
        else:
            allowed.add(d)
    return allowed, allow_law


def _build_chroma_where(
    allowed_domains: set[str] | None,
    allow_law: bool,
    doc_ids: list | None,
) -> dict | None:
    """Build Chroma where filter combining domain/doc_type and doc_id constraints."""
    filters = []

    if allowed_domains is not None:
        domain_conditions = []
        if allowed_domains:
            domain_conditions.append({"domain": {"$in": list(allowed_domains)}})
        if allow_law:
            domain_conditions.append({"doc_type": "law"})

        if not domain_conditions:
            return {"__impossible__": True}  # no domains selected
        elif len(domain_conditions) == 1:
            filters.append(domain_conditions[0])
        else:
            filters.append({"$or": domain_conditions})

    if doc_ids is not None and len(doc_ids) > 0:
        filters.append({"doc_id": {"$in": doc_ids}})

    if len(filters) == 0:
        return None
    elif len(filters) == 1:
        return filters[0]
    else:
        return {"$and": filters}


def search_chunks(
    query: str,
    domain: str | None = None,
    domains: list[str] | None = None,
    top_k: int = 5,
    doc_ids: list | None = None,
) -> list[dict]:
    # Backward compat: single domain string → list
    if domain is not None and domains is None:
        domains = [domain]

    if doc_ids is not None and len(doc_ids) == 0:
        return []

    settings = _load_rrf_settings()
    rrf_alpha = settings["rrf_alpha"]
    rrf_beta = settings["rrf_beta"]
    rrf_k = settings["rrf_k"]
    rerank_candidates = settings["rerank_candidates"]
    rerank_enabled = settings["rerank_enabled"]

    allowed_domains, allow_law = _parse_domains_filter(domains)

    # ── 1. Dense vector search (Chroma) ─────────────────────────────────────
    model = _get_embed_model()
    vec = model.encode([QUERY_PREFIX + query], normalize_embeddings=True).tolist()[0]
    col = _get_chroma_col()

    chroma_where = _build_chroma_where(allowed_domains, allow_law, doc_ids)

    dense_n = rerank_candidates
    try:
        results = col.query(
            query_embeddings=[vec],
            n_results=dense_n,
            where=chroma_where,
            include=["documents", "metadatas"],
        )
        dense_ids = [m.get("chunk_id", "") for m in results["metadatas"][0]]
    except Exception:
        dense_ids = []
        results = {"documents": [[]], "metadatas": [[]]}

    # Build chunk data lookup from dense results
    chunk_data: dict[str, dict] = {}
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        cid = meta.get("chunk_id", "")
        if cid:
            lines = doc.split("\n", 1)
            chunk_data[cid] = {
                "chunk_id": cid,
                "hierarchy": meta.get("hierarchy", ""),
                "heading": lines[0] if lines else "",
                "body": lines[1] if len(lines) > 1 else "",
                "pages": meta.get("pages", ""),
                "domain": meta.get("domain", ""),
                "refs": json.loads(meta.get("refs", "[]")),
                "doc_type": meta.get("doc_type", ""),
                "contextualized_text": doc,
            }

    # ── 2. BM25 search ──────────────────────────────────────────────────────
    bm25_data = _get_bm25_data()
    bm25_ids: list[str] = []
    if bm25_data is not None:
        from src.bm25_index import search as bm25_search
        bm25_obj, bm25_chunk_ids, bm25_domains, bm25_doc_types = bm25_data
        bm25_hits = bm25_search(
            bm25_obj, bm25_chunk_ids, query, top_k=dense_n,
            chunk_domains=bm25_domains, chunk_doc_types=bm25_doc_types,
            allowed_domains=allowed_domains, allow_law=allow_law,
        )
        bm25_ids = [h["chunk_id"] for h in bm25_hits]

        # Load chunk data for BM25-only hits from chunks.jsonl
        missing_ids = set(bm25_ids) - set(chunk_data.keys())
        if missing_ids and CHUNKS_JSONL.exists():
            with open(CHUNKS_JSONL, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = json.loads(line)
                    cid = c.get("chunk_id", "")
                    if cid in missing_ids:
                        chunk_data[cid] = {
                            "chunk_id": cid,
                            "hierarchy": c.get("hierarchy", ""),
                            "heading": c.get("heading", ""),
                            "body": c.get("body", ""),
                            "pages": c.get("pages", ""),
                            "domain": c.get("domain", ""),
                            "refs": c.get("refs", []),
                            "doc_type": c.get("doc_type", ""),
                            "contextualized_text": c.get("contextualized_text", ""),
                        }
                        missing_ids.discard(cid)
                        if not missing_ids:
                            break

    # ── 3. RRF fusion ───────────────────────────────────────────────────────
    if bm25_ids:
        fused_ids = _rrf_fusion(dense_ids, bm25_ids, rrf_alpha, rrf_beta, rrf_k)
    else:
        fused_ids = dense_ids

    candidates = fused_ids[:rerank_candidates]

    # ── 4. Reranking ────────────────────────────────────────────────────────
    if rerank_enabled and len(candidates) > 0:
        try:
            reranker = _get_reranker()
            pairs = []
            valid_cids = []
            for cid in candidates:
                cd = chunk_data.get(cid)
                if cd:
                    text = cd.get("contextualized_text") or cd.get("body", "")
                    pairs.append((RERANK_QUERY_PREFIX + query, text))
                    valid_cids.append(cid)

            if pairs:
                scores = reranker.predict(pairs)
                ranked = sorted(zip(valid_cids, scores), key=lambda x: x[1], reverse=True)
                candidates = [cid for cid, _ in ranked[:top_k]]
            else:
                candidates = candidates[:top_k]
        except Exception as e:
            logger.warning("Reranker failed, falling back to RRF order: %s", e)
            candidates = candidates[:top_k]
    else:
        candidates = candidates[:top_k]

    # ── 5. Build output ─────────────────────────────────────────────────────
    hits = []
    for cid in candidates:
        cd = chunk_data.get(cid)
        if cd:
            hits.append({
                "chunk_id": cd["chunk_id"],
                "hierarchy": cd["hierarchy"],
                "heading": cd["heading"],
                "body": cd["body"],
                "pages": cd["pages"],
                "domain": cd["domain"],
                "refs": cd["refs"],
            })
    return hits


def read_section(doc_slug: str, hierarchy: str) -> str:
    chunks = []
    if CHUNKS_JSONL.exists():
        with open(CHUNKS_JSONL, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))

    slug_chunks = [c for c in chunks if c.get("chunk_id", "").startswith(doc_slug)]

    # Exact hierarchy match
    for chunk in slug_chunks:
        if chunk.get("hierarchy") == hierarchy:
            return chunk["heading"] + "\n" + chunk["body"]

    # Partial match: hierarchy ends with "/article_num" or equals article_num
    for chunk in slug_chunks:
        h = chunk.get("hierarchy", "")
        if h.endswith("/" + hierarchy) or h == hierarchy:
            return chunk["heading"] + "\n" + chunk["body"]

    return f"[条文が見つかりません: doc_slug={doc_slug}, hierarchy={hierarchy}]"
