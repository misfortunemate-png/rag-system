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

import dotenv
import yaml

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CHROMA_DIR = Path("data/chroma")
CHUNKS_JSONL = Path("data/chunks.jsonl")
REFS_JSONL = Path("data/refs.jsonl")
BM25_PATH = Path("data/bm25_index.pkl")
COLLECTION_NAME = "kitei_spec"
MODEL_NAME = "cl-nagoya/ruri-v3-310m"
DOCUMENTS_YAML = Path("documents.yaml")

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
    texts = [DOC_PREFIX + c.get("contextualized_text", c["heading"] + "\n" + c["body"]) for c in chunks]
    logger.info("Embedding %d chunks with doc prefix...", len(texts))
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
    documents = [c.get("contextualized_text", c["heading"] + "\n" + c["body"]) for c in chunks]
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
            "context": c.get("context", ""),
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
    from src.contextualizer import contextualize
    from src.bm25_index import build_index, save_index

    docs = _load_documents()
    logger.info("=== documents.yaml: %d document(s) ===", len(docs))

    all_chunks: list[dict] = []
    errors: list[dict] = []
    ctx_det = 0
    ctx_llm = 0
    ctx_fail = 0
    profile_counts: dict[str, int] = {}
    t_start = time.time()

    for doc in docs:
        file_path = Path(doc.get("file_path") or doc.get("pdf_path", ""))
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            errors.append({"file": str(file_path), "error": "not found"})
            continue

        slug = doc["doc_slug"]
        domain = doc.get("domain", "")
        title = doc.get("title", slug)
        tags = doc.get("tags", [])
        logger.info("--- %s (%s) [%s] ---", slug, domain, file_path.suffix)

        try:
            if file_path.suffix.lower() == ".xml":
                chunks = law_xml_extract(file_path, doc_slug=slug, domain=domain)
                doc_type = "law"
                profile_name = "law"
            else:
                pages = plumber.extract_pages(file_path)
                profile_name = detect_profile(pages)
                logger.info("profile: %s", profile_name)
                chunks = chunk_by_profile(
                    pages, doc_slug=slug, domain=domain, profile=profile_name, tags=tags,
                )
                doc_type = "spec" if profile_name == "jouban" else "generic"

            profile_counts[profile_name] = profile_counts.get(profile_name, 0) + len(chunks)

            chunks = contextualize(chunks, doc_title=title, doc_type=doc_type)
            for c in chunks:
                if doc_type in ("spec", "law"):
                    ctx_det += 1
                else:
                    ctx_llm += 1
                    if c.get("context") == title:
                        ctx_fail += 1

            all_chunks.extend(chunks)
            logger.info("%s: %d chunks", slug, len(chunks))
        except Exception as e:
            logger.error("ERROR processing %s: %s", slug, e)
            errors.append({"file": str(file_path), "error": str(e)})

    t_extract = time.time()
    logger.info("extraction+chunking+context: %.1fs", t_extract - t_start)
    logger.info("context stats: deterministic=%d, llm=%d (fallback=%d)", ctx_det, ctx_llm, ctx_fail)
    logger.info("profile breakdown: %s", profile_counts)

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

    logger.info("=== BM25 index ===")
    bm25 = build_index(all_chunks)
    chunk_ids = [c["chunk_id"] for c in all_chunks]
    chunk_domains = [c.get("domain", "") for c in all_chunks]
    chunk_doc_types = [c.get("doc_type", "") for c in all_chunks]
    save_index(bm25, chunk_ids, BM25_PATH, chunk_domains=chunk_domains, chunk_doc_types=chunk_doc_types)
    t_bm25 = time.time()
    logger.info("BM25: %.1fs", t_bm25 - t_store)

    logger.info("=== done: %d chunks ingested (%.1fs total) ===", len(all_chunks), t_bm25 - t_start)
    if errors:
        logger.warning("=== %d file(s) had errors ===", len(errors))
        for e in errors:
            logger.warning("  %s: %s", e["file"], e["error"])


def main():
    run()


if __name__ == "__main__":
    main()
