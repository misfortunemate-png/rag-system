"""
Ingest pipeline: documents.yaml → extract → chunk → embed (ruri-v3-310m) → Chroma.

Usage:
    python -m src.ingest

Produces:
    data/chunks.jsonl   intermediate chunks for visual inspection
    data/refs.jsonl     cross-reference edges {from_chunk_id, to_hierarchy}
    data/chroma/        Chroma persistent store (collection: kitei_spec)
"""
import json
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CHROMA_DIR = Path("data/chroma")
CHUNKS_JSONL = Path("data/chunks.jsonl")
REFS_JSONL = Path("data/refs.jsonl")
COLLECTION_NAME = "kitei_spec"
MODEL_NAME = "cl-nagoya/ruri-v3-310m"
DOCUMENTS_YAML = Path("documents.yaml")

# Document-side prefix for ruri-v3-310m.
# Source: cl-nagoya/ruri-v3-310m HuggingFace model card (verified 2026-08-04).
DOC_PREFIX = "文章: "


def _load_documents() -> list[dict]:
    with open(DOCUMENTS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)["documents"]


def _load_model():
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model: %s", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)
    logger.info("Model loaded.")
    return model


def _embed_chunks(model, chunks: list[dict]) -> list[list[float]]:
    texts = [DOC_PREFIX + c["heading"] + "\n" + c["body"] for c in chunks]
    logger.info("Embedding %d chunks with doc prefix...", len(texts))
    # batch_size=64 → 8 に変更
    embeddings = model.encode(texts, batch_size=8, show_progress_bar=True, normalize_embeddings=True)

    return embeddings.tolist()


def _store_chroma(chunks: list[dict], embeddings: list[list[float]]) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["heading"] + "\n" + c["body"] for c in chunks]
    metadatas = [
        {
            "chunk_id": c["chunk_id"],
            "hierarchy": c["hierarchy"],
            "domain": c.get("domain", ""),
            "pages": c["pages"],
            "source_engine": c["source_engine"],
            "doc_type": c["doc_type"],
            "char_count": c["char_count"],
            "refs": json.dumps(c.get("refs", []), ensure_ascii=False),
        }
        for c in chunks
    ]

    batch = 500
    for i in range(0, len(chunks), batch):
        col.add(
            ids=ids[i: i + batch],
            embeddings=embeddings[i: i + batch],
            documents=documents[i: i + batch],
            metadatas=metadatas[i: i + batch],
        )
    logger.info("Stored %d chunks in Chroma collection '%s'", len(chunks), COLLECTION_NAME)


def _write_refs_jsonl(chunks: list[dict]) -> None:
    REFS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(REFS_JSONL, "w", encoding="utf-8") as f:
        for c in chunks:
            for ref in c.get("refs", []):
                f.write(json.dumps(
                    {"from_chunk_id": c["chunk_id"], "to_hierarchy": ref},
                    ensure_ascii=False,
                ) + "\n")
                count += 1
    logger.info("refs.jsonl: wrote %d edges → %s", count, REFS_JSONL)


def run() -> None:
    from src.extract import plumber, pymupdf_ext
    from src.extract.arbiter import arbitrate_pages
    from src.chunker import chunk_pages, write_jsonl

    docs = _load_documents()
    logger.info("=== documents.yaml: %d document(s) ===", len(docs))

    all_chunks: list[dict] = []

    for doc in docs:
        pdf_path = Path(doc["pdf_path"])
        if not pdf_path.exists():
            logger.error("PDF not found: %s", pdf_path)
            sys.exit(1)

        logger.info("--- %s (%s) ---", doc["doc_slug"], doc["domain"])

        logger.info("extract")
        plumber_pages = plumber.extract_pages(pdf_path)
        pymupdf_pages = pymupdf_ext.extract_pages(pdf_path)

        logger.info("arbitrate")
        pages = arbitrate_pages({"plumber": plumber_pages, "pymupdf": pymupdf_pages})

        logger.info("chunk")
        chunks = chunk_pages(pages, doc_slug=doc["doc_slug"], domain=doc["domain"])
        all_chunks.extend(chunks)

    write_jsonl(all_chunks, CHUNKS_JSONL)
    _write_refs_jsonl(all_chunks)

    logger.info("=== embed & store ===")
    model = _load_model()
    embeddings = _embed_chunks(model, all_chunks)
    _store_chroma(all_chunks, embeddings)

    logger.info("=== done: %d chunks ingested ===", len(all_chunks))


def main():
    run()


if __name__ == "__main__":
    main()
