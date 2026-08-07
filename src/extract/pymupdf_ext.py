import fitz  # PyMuPDF
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pages(pdf_path: str | Path) -> list[dict]:
    """Extract text from each PDF page using PyMuPDF. Returns list of page dicts."""
    results = []
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        results.append({"page": i, "text": text, "tables": ""})
        if i % 50 == 0:
            logger.info(f"pymupdf: extracted page {i}/{total}")
    doc.close()
    logger.info(f"pymupdf: extracted {len(results)} pages from {pdf_path}")
    return results
