"""
BM25 index: build, save, load, and query using fugashi tokenization.

tokenize_ja is shared between ingest (build) and query (search).
"""
import logging
import pickle
from pathlib import Path

import fugashi
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_tagger = None

def _get_tagger():
    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()
    return _tagger


_KEEP_POS = frozenset(("名詞", "動詞", "形容詞"))


def tokenize_ja(text: str) -> list[str]:
    tagger = _get_tagger()
    tokens = []
    for word in tagger(text):
        pos1 = getattr(word.feature, "pos1", None) or (word.feature[0] if word.feature else "")
        if pos1 in _KEEP_POS:
            lemma = getattr(word.feature, "lemma", None)
            if not lemma or lemma == "*":
                lemma = str(word)
            tokens.append(lemma)
    return tokens


def build_index(chunks: list[dict]) -> BM25Okapi:
    corpus = [tokenize_ja(c.get("contextualized_text", c.get("body", ""))) for c in chunks]
    logger.info("BM25: tokenized %d chunks", len(corpus))
    return BM25Okapi(corpus)


def save_index(
    bm25: BM25Okapi,
    chunk_ids: list[str],
    path: str | Path,
    chunk_domains: list[str] | None = None,
    chunk_doc_types: list[str] | None = None,
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = {"bm25": bm25, "chunk_ids": chunk_ids}
    if chunk_domains is not None:
        data["chunk_domains"] = chunk_domains
    if chunk_doc_types is not None:
        data["chunk_doc_types"] = chunk_doc_types
    with open(path, "wb") as f:
        pickle.dump(data, f)
    logger.info("BM25: saved index (%d docs) → %s", len(chunk_ids), path)


def load_index(path: str | Path) -> tuple[BM25Okapi, list[str], list[str], list[str]]:
    with open(path, "rb") as f:
        data = pickle.load(f)
    chunk_ids = data["chunk_ids"]
    chunk_domains = data.get("chunk_domains", [""] * len(chunk_ids))
    chunk_doc_types = data.get("chunk_doc_types", [""] * len(chunk_ids))
    return data["bm25"], chunk_ids, chunk_domains, chunk_doc_types


def search(
    bm25: BM25Okapi,
    chunk_ids: list[str],
    query: str,
    top_k: int = 10,
    chunk_domains: list[str] | None = None,
    chunk_doc_types: list[str] | None = None,
    allowed_domains: set[str] | None = None,
    allow_law: bool = True,
) -> list[dict]:
    tokens = tokenize_ja(query)
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results = []
    for i, s in ranked:
        if s <= 0:
            break
        if allowed_domains is not None:
            domain = chunk_domains[i] if chunk_domains else ""
            doc_type = chunk_doc_types[i] if chunk_doc_types else ""
            if doc_type == "law":
                if not allow_law:
                    continue
            elif domain not in allowed_domains:
                continue
        results.append({"chunk_id": chunk_ids[i], "bm25_score": float(s)})
        if len(results) >= top_k:
            break
    return results
