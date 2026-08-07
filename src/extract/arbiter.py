"""
Arbiter: compares text extraction results from multiple engines per page
and selects the best result based on:
  - garble_rate: ratio of garbled chars (U+FFFD + C0/C1 control chars)
  - fragment_rate: ratio of very short lines (likely line-break artifacts)

Threshold rationale: garbled text is a hard signal of engine failure;
fragmentation is softer (layout PDFs have many short lines) so weight 0.4.
"""
import re
import logging

logger = logging.getLogger(__name__)

_GARBLED_RE = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _garble_rate(text: str) -> float:
    if not text:
        return 1.0
    return len(_GARBLED_RE.findall(text)) / len(text)


def _fragment_rate(text: str) -> float:
    if not text:
        return 1.0
    lines = text.split("\n")
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return 1.0
    # Lines shorter than 4 chars are likely fragments (page numbers, isolated chars)
    short = sum(1 for l in non_empty if len(l.strip()) < 4)
    return short / len(non_empty)


def select_best(candidates: dict) -> tuple[str, dict]:
    """
    candidates: {engine_name: page_dict, ...}
    Returns (winning_engine_name, page_dict).
    Score = garble_rate * 0.6 + fragment_rate * 0.4 (lower is better).
    """
    scores = {}
    for engine, page in candidates.items():
        text = page.get("text", "")
        gr = _garble_rate(text)
        fr = _fragment_rate(text)
        score = gr * 0.6 + fr * 0.4
        scores[engine] = (score, gr, fr)
        logger.debug(
            "page=%s engine=%s garble=%.3f fragment=%.3f score=%.3f",
            page.get("page", "?"), engine, gr, fr, score,
        )

    best = min(scores, key=lambda e: scores[e][0])
    sc, gr, fr = scores[best]
    logger.info(
        "page=%s → %s (score=%.3f garble=%.3f fragment=%.3f)",
        candidates[best].get("page", "?"), best, sc, gr, fr,
    )
    return best, candidates[best]


def arbitrate_pages(pages_by_engine: dict) -> list[dict]:
    """
    pages_by_engine: {engine_name: [page_dict, ...], ...}
    All engines must have the same page count.
    Returns list of page dicts with 'source_engine' field added.
    """
    engine_names = list(pages_by_engine.keys())
    if not engine_names:
        return []

    page_count = len(pages_by_engine[engine_names[0]])
    results = []
    for idx in range(page_count):
        candidates = {eng: pages_by_engine[eng][idx] for eng in engine_names}
        winner, page = select_best(candidates)
        page = dict(page)
        page["source_engine"] = winner
        results.append(page)

    engine_counts = {}
    for p in results:
        eng = p["source_engine"]
        engine_counts[eng] = engine_counts.get(eng, 0) + 1
    logger.info("Arbitration summary: %s", engine_counts)
    return results
