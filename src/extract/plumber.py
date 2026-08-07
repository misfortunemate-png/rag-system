import pdfplumber
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _table_to_markdown(rows: list) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(str(c or "") for c in rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body_rows = [
        "| " + " | ".join(str(c or "").replace("\n", " ") for c in row) + " |"
        for row in rows[1:]
    ]
    return "\n".join([header, sep] + body_rows)


def extract_pages(pdf_path: str | Path) -> list[dict]:
    """Extract text from each PDF page using pdfplumber. Returns list of page dicts."""
    results = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(layout=True) or ""
            tables = page.extract_tables() or []
            table_parts = [_table_to_markdown(t) for t in tables if t]
            table_md = "\n".join(p for p in table_parts if p)
            results.append({"page": i, "text": text, "tables": table_md})
            if i % 50 == 0:
                logger.info(f"plumber: extracted page {i}/{len(pdf.pages)}")
    logger.info(f"plumber: extracted {len(results)} pages from {pdf_path}")
    return results
