"""
Chunker: splits arbitrated page text into article-level chunks.

Profiles:
  jouban  — 条番号型（公共建築工事標準仕様書など）。X.Y.Z 条番号を階層の起点とする。
  generic — 汎用型。見出し行またはページ境界を起点とするシンプル分割。

PDF structure (jouban):
  第N編 > 第M章 > 第K節 > X.Y.Z 条名
    (1) 項
      (ｱ) 号
        (a) 細目

Hierarchy field example: 第2編/第1章/第3節/1.3.1
Thresholds (adjustable): merge < 300 chars into parent section chunk;
                          split > 2000 chars at item boundaries.
"""
import re
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MERGE_THRESHOLD = 300
SPLIT_THRESHOLD = 2000

_HEN_RE = re.compile(r"^第\s*(\d+)\s*編\s*(.*)")
_SHO_RE = re.compile(r"^第\s*(\d+)\s*章\s*(.*)")
_SETSU_RE = re.compile(r"^第\s*(\d+)\s*節\s*(.*)")
_ARTICLE_RE = re.compile(r"^(\d+\.\d+\.\d+)\s+(.*)")
# Item-level split boundary inside a large chunk
_ITEM_RE = re.compile(r"^\s*\(\d+\)")

# Cross-reference extraction patterns (deterministic, LLM-free)
_REF_ARTICLE_RE = re.compile(r"(\d+\.\d+\.\d+)「[^」]+」")
_REF_TABLE_RE = re.compile(r"(表\d+\.\d+(?:\.\d+)?)")
_REF_CHAPTER_RE = re.compile(r"(第\d+編第\d+章)")


def _extract_refs(body: str) -> list[str]:
    refs = []
    refs.extend(m.group(1) for m in _REF_ARTICLE_RE.finditer(body))
    refs.extend(m.group(1) for m in _REF_TABLE_RE.finditer(body))
    refs.extend(m.group(1) for m in _REF_CHAPTER_RE.finditer(body))
    seen: set[str] = set()
    result = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


def _build_hierarchy(hen: str, sho: str, setsu: str, article_num: str) -> str:
    parts = [p for p in [hen, sho, setsu, article_num] if p]
    return "/".join(parts)


def _make_chunk(
    chunk_id: str,
    hierarchy: str,
    heading: str,
    body: str,
    pages: list[int],
    source_engine: str,
    domain: str = "",
) -> dict:
    stripped = body.strip()
    return {
        "chunk_id": chunk_id,
        "doc_type": "spec",
        "domain": domain,
        "hierarchy": hierarchy,
        "heading": heading,
        "body": stripped,
        "pages": f"{min(pages)}-{max(pages)}" if len(pages) > 1 else str(pages[0]),
        "char_count": len(stripped),
        "source_engine": source_engine,
        "refs": _extract_refs(stripped),
    }


def _split_large(body: str, base_heading: str, hierarchy: str, pages: list[int], source_engine: str, base_id: str, domain: str = "") -> list[dict]:
    """Split a body > SPLIT_THRESHOLD at item (1), (2)... boundaries."""
    item_starts = [m.start() for m in _ITEM_RE.finditer(body)]
    if not item_starts:
        return [_make_chunk(base_id, hierarchy, base_heading, body, pages, source_engine, domain)]

    parts = []
    boundaries = item_starts + [len(body)]
    if item_starts[0] > 0:
        parts.append(body[: item_starts[0]])
    for i in range(len(item_starts)):
        parts.append(body[boundaries[i]: boundaries[i + 1]])

    chunks = []
    for j, part in enumerate(parts):
        if not part.strip():
            continue
        sub_id = f"{base_id}-{j + 1}"
        sub_hierarchy = f"{hierarchy}/{j + 1}" if j > 0 or item_starts[0] > 0 else hierarchy
        chunks.append(_make_chunk(sub_id, sub_hierarchy, base_heading, part, pages, source_engine, domain))
    return chunks


def chunk_pages(pages: list[dict], doc_slug: str = "spec", domain: str = "") -> list[dict]:
    """
    Convert arbitrated page dicts into chunk records.
    Returns list of chunk dicts (also written to data/chunks.jsonl by ingest.py).
    """
    # State
    current_hen = ""
    current_sho = ""
    current_setsu = ""
    current_article_num = ""
    current_article_name = ""
    current_body_lines: list[str] = []
    current_pages: list[int] = []
    current_engine = ""

    raw_chunks: list[dict] = []  # articles before threshold rules
    counter = 0

    def flush():
        nonlocal counter
        if not current_article_num:
            return
        body = "\n".join(current_body_lines)
        hierarchy = _build_hierarchy(current_hen, current_sho, current_setsu, current_article_num)
        heading = f"{current_article_num} {current_article_name}"
        counter += 1
        chunk_id = f"{doc_slug}-{counter:04d}"
        raw_chunks.append(
            _make_chunk(chunk_id, hierarchy, heading, body, current_pages or [0], current_engine, domain)
        )

    for page_dict in pages:
        page_no = page_dict["page"]
        source_engine = page_dict.get("source_engine", "unknown")
        text = page_dict.get("text", "")

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if current_article_num:
                    current_body_lines.append("")
                continue

            m_hen = _HEN_RE.match(line)
            m_sho = _SHO_RE.match(line)
            m_setsu = _SETSU_RE.match(line)
            m_article = _ARTICLE_RE.match(line)

            if m_hen:
                flush()
                current_hen = f"第{m_hen.group(1)}編 {m_hen.group(2).strip()}"
                current_sho = ""
                current_setsu = ""
                current_article_num = ""
                current_article_name = ""
                current_body_lines = []
                current_pages = []
            elif m_sho:
                flush()
                current_sho = f"第{m_sho.group(1)}章 {m_sho.group(2).strip()}"
                current_setsu = ""
                current_article_num = ""
                current_article_name = ""
                current_body_lines = []
                current_pages = []
            elif m_setsu:
                flush()
                current_setsu = f"第{m_setsu.group(1)}節 {m_setsu.group(2).strip()}"
                current_article_num = ""
                current_article_name = ""
                current_body_lines = []
                current_pages = []
            elif m_article:
                flush()
                current_article_num = m_article.group(1)
                current_article_name = m_article.group(2).strip()
                current_body_lines = []
                current_pages = [page_no]
                current_engine = source_engine
            else:
                if current_article_num:
                    current_body_lines.append(raw_line)
                    if page_no not in current_pages:
                        current_pages.append(page_no)

    flush()

    # Apply threshold rules
    final_chunks: list[dict] = []
    pending_small: list[dict] = []
    pending_parent_key: str = ""

    def flush_pending():
        nonlocal pending_parent_key
        if not pending_small:
            return
        if len(pending_small) == 1:
            final_chunks.append(pending_small[0])
        else:
            # Merge into a single chunk
            merged_body = "\n".join(c["body"] for c in pending_small)
            base = pending_small[0]
            all_pages_str = [c["pages"] for c in pending_small]
            all_page_nums = []
            for ps in all_pages_str:
                parts = ps.split("-")
                all_page_nums.extend(int(p) for p in parts if p.isdigit())
            pages_range = (
                f"{min(all_page_nums)}-{max(all_page_nums)}"
                if len(all_page_nums) > 1
                else str(all_page_nums[0]) if all_page_nums else "0"
            )
            merged = dict(base)
            merged["body"] = merged_body
            merged["char_count"] = len(merged_body)
            merged["pages"] = pages_range
            merged["heading"] = base["heading"] + "（統合）"
            final_chunks.append(merged)
        pending_small.clear()
        pending_parent_key = ""

    for chunk in raw_chunks:
        parent_key = "/".join(chunk["hierarchy"].split("/")[:-1])  # up to 節

        if chunk["char_count"] < MERGE_THRESHOLD:
            if pending_parent_key and pending_parent_key != parent_key:
                flush_pending()
            pending_parent_key = parent_key
            pending_small.append(chunk)
        else:
            flush_pending()
            if chunk["char_count"] > SPLIT_THRESHOLD:
                split = _split_large(
                    chunk["body"],
                    chunk["heading"],
                    chunk["hierarchy"],
                    [int(p) for p in chunk["pages"].replace("-", " ").split() if p.isdigit()],
                    chunk["source_engine"],
                    chunk["chunk_id"],
                    chunk.get("domain", ""),
                )
                final_chunks.extend(split)
            else:
                final_chunks.append(chunk)

    flush_pending()

    logger.info(
        "chunker: %d raw → %d final chunks (merge<300, split>2000)",
        len(raw_chunks), len(final_chunks),
    )
    return final_chunks


def chunk_generic(
    pages: list[dict],
    doc_slug: str = "doc",
    domain: str = "",
    tags: list[str] | None = None,
    target_chars: int = 800,
) -> list[dict]:
    """
    汎用チャンカー。見出し行（短い行）またはtarget_chars文字に達したら区切る。
    条番号パターンを前提としない。
    """
    _HEADING_RE = re.compile(r"^[第\d\s【\[（(].{0,30}[章節項編:：]")
    _SHORT_LINE_THRESHOLD = 40  # これ以下の行を見出し候補とする

    tags_list = tags or []
    chunks: list[dict] = []
    counter = 0

    current_heading = ""
    current_lines: list[str] = []
    current_pages: list[int] = []

    def flush():
        nonlocal counter
        body = "\n".join(current_lines).strip()
        if not body:
            return
        counter += 1
        chunk_id = f"{doc_slug}-{counter:04d}"
        pages_str = (
            f"{min(current_pages)}-{max(current_pages)}"
            if len(current_pages) > 1
            else str(current_pages[0]) if current_pages else "0"
        )
        chunks.append({
            "chunk_id": chunk_id,
            "doc_type": "generic",
            "domain": domain,
            "tags": tags_list,
            "hierarchy": current_heading or f"chunk-{counter}",
            "heading": current_heading or f"(chunk {counter})",
            "body": body,
            "pages": pages_str,
            "char_count": len(body),
            "source_engine": "generic",
            "refs": [],
        })

    for page_dict in pages:
        page_no = page_dict["page"]
        text = page_dict.get("text", "")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                current_lines.append("")
                continue
            is_heading = (
                _HEADING_RE.match(line) or len(line) <= _SHORT_LINE_THRESHOLD
            ) and not current_lines

            if is_heading and current_lines:
                flush()
                current_heading = line
                current_lines = []
                current_pages = [page_no]
            else:
                if not current_pages:
                    current_pages = [page_no]
                if page_no not in current_pages:
                    current_pages.append(page_no)
                current_lines.append(raw_line)
                if sum(len(l) for l in current_lines) >= target_chars:
                    flush()
                    current_heading = ""
                    current_lines = []
                    current_pages = []
    flush()

    logger.info("generic chunker: %d chunks for %s", len(chunks), doc_slug)
    return chunks


# 条番号パターンの密度で jouban/generic を判定するしきい値
_JOUBAN_DENSITY_THRESHOLD = 0.015  # 全文字数に対する条番号マッチ数の割合


def detect_profile(pages: list[dict]) -> str:
    """
    先頭10ページのテキストから条番号密度を測定し、jouban/generic を返す。
    """
    sample = pages[:10]
    total_chars = 0
    article_hits = 0
    for p in sample:
        text = p.get("text", "")
        total_chars += len(text)
        article_hits += len(_ARTICLE_RE.findall(text))
    if total_chars == 0:
        return "generic"
    density = article_hits / total_chars
    profile = "jouban" if density >= _JOUBAN_DENSITY_THRESHOLD else "generic"
    logger.info("detect_profile: density=%.5f → %s", density, profile)
    return profile


def chunk_by_profile(
    pages: list[dict],
    doc_slug: str,
    domain: str,
    profile: str,
    tags: list[str] | None = None,
) -> list[dict]:
    """Profile-aware dispatcher."""
    if profile == "jouban":
        return chunk_pages(pages, doc_slug=doc_slug, domain=domain)
    return chunk_generic(pages, doc_slug=doc_slug, domain=domain, tags=tags)


def write_jsonl(chunks: list[dict], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    logger.info("chunker: wrote %d chunks to %s", len(chunks), path)


def append_jsonl(chunks: list[dict], path: str | Path) -> None:
    """Append chunks to an existing JSONL file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    logger.info("chunker: appended %d chunks to %s", len(chunks), path)
