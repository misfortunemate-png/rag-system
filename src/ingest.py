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
    import time
    from src.extract import plumber
    from src.extract.law_xml_ext import extract_chunks as law_xml_extract
    from src.chunker import chunk_by_profile, detect_profile, write_jsonl

    docs = _load_documents()
    logger.info("=== documents.yaml: %d document(s) ===", len(docs))

    all_chunks: list[dict] = []
    errors: list[dict] = []
    t_start = time.time()

    for doc in docs:
        file_path = Path(doc.get("file_path") or doc.get("pdf_path", ""))
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            errors.append({"file": str(file_path), "error": "not found"})
            continue

        slug = doc["doc_slug"]
        domain = doc.get("domain", "")
        logger.info("--- %s (%s) [%s] ---", slug, domain, file_path.suffix)

        try:
            if file_path.suffix.lower() == ".xml":
                chunks = law_xml_extract(file_path, doc_slug=slug, domain=domain)
            else:
                pages = plumber.extract_pages(file_path)
                profile = detect_profile(pages)
                logger.info("profile: %s", profile)
                chunks = chunk_by_profile(
                    pages, doc_slug=slug, domain=domain, profile=profile,
                )
            all_chunks.extend(chunks)
            logger.info("%s: %d chunks", slug, len(chunks))
        except Exception as e:
            logger.error("ERROR processing %s: %s", slug, e)
            errors.append({"file": str(file_path), "error": str(e)})

    t_extract = time.time()
    logger.info("extraction+chunking: %.1fs", t_extract - t_start)

    write_jsonl(all_chunks, CHUNKS_JSONL)
    _write_refs_jsonl(all_chunks)

    logger.info("=== embed & store ===")
    model = _load_model()
    embeddings = _embed_chunks(model, all_chunks)
    t_embed = time.time()
    logger.info("embedding: %.1fs", t_embed - t_extract)

    _store_chroma(all_chunks, embeddings)
    t_store = time.time()
    logger.info("chroma store: %.1fs", t_store - t_embed)

    logger.info("=== done: %d chunks ingested (%.1fs total) ===", len(all_chunks), t_store - t_start)
    if errors:
        logger.warning("=== %d file(s) had errors ===", len(errors))
        for e in errors:
            logger.warning("  %s: %s", e["file"], e["error"])


def main():
    run()


if __name__ == "__main__":
    main()
