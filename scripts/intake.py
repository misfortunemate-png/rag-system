"""
Intake pipeline: data/inbox/ PDF -> Chroma append.

Usage:
    python scripts/intake.py

Steps:
  1. Migrate existing Chroma chunks (add doc_id if missing)
  2. Scan inbox/ for PDFs
  3. SHA-256 dedup against documents.yaml
  4. Extract -> chunk -> embed -> Chroma append
  5. Move PDF to data/raw/ (preserving folder structure)
  6. Register in documents.yaml
"""
import hashlib
import json
import logging
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INBOX_DIR = Path("data/inbox")
RAW_DIR = Path("data/raw")
CHUNKS_JSONL = Path("data/chunks.jsonl")
CHROMA_DIR = Path("data/chroma")
COLLECTION_NAME = "kitei_spec"
EMBED_MODEL = "cl-nagoya/ruri-v3-310m"
DOC_PREFIX = "文章: "

DOCUMENTS_YAML = Path("documents.yaml")

_KNOWN_DOC_SLUGS = ["denki-setsubi"]


# ── YAML helpers ──────────────────────────────────────────────────────────────

def _load_yaml() -> dict:
    import yaml
    if not DOCUMENTS_YAML.exists():
        return {"documents": []}
    with open(DOCUMENTS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("documents", [])
    return data


def _save_yaml(data: dict) -> None:
    import yaml
    with open(DOCUMENTS_YAML, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── Chroma helpers ────────────────────────────────────────────────────────────

def _get_or_create_col():
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _migrate_existing_doc_ids() -> None:
    """Add doc_id metadata to Chroma chunks ingested before M4.5."""
    col = _get_or_create_col()
    total = col.count()
    if total == 0:
        logger.info("migration: collection empty, nothing to migrate")
        return

    result = col.get(include=["metadatas"])
    ids = result["ids"]
    metadatas = result["metadatas"]

    need_ids = []
    need_metas = []
    for cid, meta in zip(ids, metadatas):
        if meta.get("doc_id"):
            continue
        doc_slug = None
        for slug in _KNOWN_DOC_SLUGS:
            if cid.startswith(slug + "-"):
                doc_slug = slug
                break
        if doc_slug:
            new_meta = dict(meta)
            new_meta["doc_id"] = doc_slug
            need_ids.append(cid)
            need_metas.append(new_meta)

    if not need_ids:
        logger.info("migration: all %d chunks already have doc_id", total)
        return

    batch_size = 500
    for i in range(0, len(need_ids), batch_size):
        col.update(
            ids=need_ids[i:i + batch_size],
            metadatas=need_metas[i:i + batch_size],
        )
    logger.info("migration: added doc_id to %d / %d chunks", len(need_ids), total)


# ── PDF processing ────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _slugify(name: str) -> str:
    stem = Path(name).stem
    slug = re.sub(r"[^\w\-]", "-", stem, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:40].lower()


def _extract_pages(pdf_path: Path) -> list[dict]:
    import pdfplumber
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": i, "text": text, "source_engine": "pdfplumber"})
    return pages


def _embed_and_append(chunks: list[dict], col) -> int:
    """Embed chunks and add to Chroma. Returns count of actually added chunks."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)

    batch_size = 100
    added = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        ids = [c["chunk_id"] for c in batch]

        existing = col.get(ids=ids, include=[])
        existing_set = set(existing["ids"])
        new_idx = [i for i, cid in enumerate(ids) if cid not in existing_set]
        if not new_idx:
            continue

        new_chunks = [batch[i] for i in new_idx]
        texts_for_embed = [
            DOC_PREFIX + c.get("heading", "") + "\n" + c.get("body", "")
            for c in new_chunks
        ]
        docs_for_store = [
            c.get("heading", "") + "\n" + c.get("body", "")
            for c in new_chunks
        ]
        metadatas = [
            {
                "chunk_id": c["chunk_id"],
                "doc_id": c.get("doc_id", ""),
                "doc_type": c.get("doc_type", "generic"),
                "domain": c.get("domain", ""),
                "hierarchy": c.get("hierarchy", ""),
                "heading": c.get("heading", ""),
                "pages": str(c.get("pages", "")),
                "char_count": int(c.get("char_count", 0)),
                "source_engine": c.get("source_engine", ""),
                "refs": json.dumps(c.get("refs", []), ensure_ascii=False),
            }
            for c in new_chunks
        ]

        vecs = model.encode(texts_for_embed, normalize_embeddings=True).tolist()
        col.add(
            ids=[batch[i]["chunk_id"] for i in new_idx],
            embeddings=vecs,
            documents=docs_for_store,
            metadatas=metadatas,
        )
        added += len(new_idx)

    return added


def process_pdf(pdf_path: Path, docs_data: dict, col) -> bool:
    """Process one PDF. Returns True if processed (new), False if skipped."""
    sha = _sha256(pdf_path)
    docs = docs_data.get("documents", [])

    # SHA-256 dedup
    for doc in docs:
        if doc.get("sha256") == sha:
            logger.info("SKIP (already registered by sha256): %s", pdf_path.name)
            return False

    # Name collision with different hash
    stem = pdf_path.stem
    for doc in docs:
        existing_stem = Path(doc.get("pdf_path", "")).stem
        if existing_stem == stem and doc.get("sha256") != sha:
            logger.warning(
                "CONFLICT: '%s' name already registered with a different hash. "
                "Stopping this file only — resolve manually before re-running intake.",
                pdf_path.name,
            )
            return False

    logger.info("Processing: %s", pdf_path.name)

    # Determine domain / tags from folder structure
    try:
        rel_parts = pdf_path.relative_to(INBOX_DIR).parts[:-1]
    except ValueError:
        rel_parts = ()
    domain = rel_parts[0] if rel_parts else "未分類"
    tags = list(rel_parts[1:]) if len(rel_parts) > 1 else []

    # Generate unique doc_id / slug
    slug_base = _slugify(pdf_path.stem)
    doc_id = slug_base
    existing_ids = {d.get("id", "") for d in docs}
    if doc_id in existing_ids:
        i = 2
        while f"{doc_id}-{i}" in existing_ids:
            i += 1
        doc_id = f"{doc_id}-{i}"

    # Extract
    pages = _extract_pages(pdf_path)

    # Profile detection
    from src.chunker import chunk_by_profile, detect_profile
    profile = detect_profile(pages)
    logger.info("profile detected: %s", profile)

    # Chunk
    chunks = chunk_by_profile(pages, doc_slug=doc_id, domain=domain, profile=profile, tags=tags)
    for c in chunks:
        c["doc_id"] = doc_id
    logger.info("chunked: %d chunks", len(chunks))

    # Append to chunks.jsonl
    from src.chunker import append_jsonl
    append_jsonl(chunks, CHUNKS_JSONL)

    # Embed and add to Chroma
    added = _embed_and_append(chunks, col)
    logger.info("added to Chroma: %d new chunks", added)

    # Determine raw/ target (preserve inbox folder structure)
    try:
        rel = pdf_path.relative_to(INBOX_DIR)
        target = RAW_DIR / rel
    except ValueError:
        target = RAW_DIR / pdf_path.name

    target.parent.mkdir(parents=True, exist_ok=True)

    # Register in documents.yaml
    new_doc = {
        "id": doc_id,
        "doc_slug": doc_id,
        "title": pdf_path.stem,
        "domain": domain,
        "tags": tags,
        "profile": profile,
        "sha256": sha,
        "pdf_path": str(target).replace("\\", "/"),
        "ingest_at": date.today().isoformat(),
        "status": "active",
    }
    docs_data["documents"].append(new_doc)
    _save_yaml(docs_data)
    logger.info("registered in documents.yaml: %s", doc_id)

    # Move PDF to raw/
    shutil.move(str(pdf_path), str(target))
    logger.info("moved to %s", target)

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("=== intake start ===")

    # Step 1: Migrate existing chunks
    try:
        _migrate_existing_doc_ids()
    except Exception as e:
        logger.warning("migration failed (non-fatal): %s", e)

    # Step 2: Find PDFs
    pdfs = sorted(INBOX_DIR.rglob("*.pdf"))
    if not pdfs:
        logger.info("inbox is empty — nothing to do")
        return

    logger.info("found %d PDF(s) in inbox", len(pdfs))

    docs_data = _load_yaml()
    col = _get_or_create_col()

    processed = skipped = failed = 0
    for pdf_path in pdfs:
        try:
            ok = process_pdf(pdf_path, docs_data, col)
            if ok:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("ERROR processing %s: %s", pdf_path.name, e)
            failed += 1

    logger.info(
        "=== intake done: %d processed, %d skipped, %d failed ===",
        processed, skipped, failed,
    )


if __name__ == "__main__":
    main()
