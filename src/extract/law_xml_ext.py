"""e-Gov法令XML → チャンクリスト抽出器"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

HIERARCHY_TAGS = {
    "Part": "PartTitle",
    "Chapter": "ChapterTitle",
    "Section": "SectionTitle",
    "Subsection": "SubsectionTitle",
    "Division": "DivisionTitle",
}


def _get_all_text(elem) -> str:
    return "".join(elem.itertext()).strip()


def _build_hierarchy(article_elem) -> str:
    parts = []
    parent = article_elem
    ancestors = []
    # Walk up via stored parent map
    while parent is not None:
        ancestors.append(parent)
        parent = parent.get("_parent")

    for anc in reversed(ancestors):
        tag = anc.tag
        if tag in HIERARCHY_TAGS:
            title_elem = anc.find(HIERARCHY_TAGS[tag])
            if title_elem is not None:
                parts.append(_get_all_text(title_elem).strip())
    return "/".join(parts)


def _set_parents(elem, parent=None):
    elem.set("_parent", parent)
    for child in elem:
        _set_parents(child, elem)


def _extract_article_text(article) -> str:
    lines = []
    for para in article.iter("Paragraph"):
        para_num = para.find("ParagraphNum")
        if para_num is not None and _get_all_text(para_num):
            lines.append(_get_all_text(para_num))
        sent_elem = para.find("ParagraphSentence")
        if sent_elem is not None:
            lines.append(_get_all_text(sent_elem))

        for item in para.findall("Item"):
            item_title = item.find("ItemTitle")
            item_sent = item.find("ItemSentence")
            item_text = ""
            if item_title is not None:
                item_text += _get_all_text(item_title) + "　"
            if item_sent is not None:
                item_text += _get_all_text(item_sent)
            if item_text.strip():
                lines.append(item_text.strip())

            for sub in item.findall("Subitem1"):
                st = sub.find("Subitem1Title")
                ss = sub.find("Subitem1Sentence")
                sub_text = ""
                if st is not None:
                    sub_text += _get_all_text(st) + "　"
                if ss is not None:
                    sub_text += _get_all_text(ss)
                if sub_text.strip():
                    lines.append("  " + sub_text.strip())

    return "\n".join(lines)


def extract_chunks(xml_path: str | Path, doc_slug: str, domain: str = "") -> list[dict]:
    """Extract chunks from an e-Gov law XML file, one chunk per Article."""
    xml_path = Path(xml_path)
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    law_body = root.find(".//LawBody")
    if law_body is None:
        logger.warning("No LawBody found in %s", xml_path.name)
        return []

    _set_parents(law_body)

    main = law_body.find("MainProvision")
    if main is None:
        logger.warning("No MainProvision found in %s", xml_path.name)
        return []

    chunks = []
    idx = 0

    for article in main.iter("Article"):
        idx += 1
        title_elem = article.find("ArticleTitle")
        caption_elem = article.find("ArticleCaption")

        heading = ""
        if title_elem is not None:
            heading = _get_all_text(title_elem)
        if caption_elem is not None:
            cap = _get_all_text(caption_elem)
            if cap:
                heading = f"{heading} {cap}" if heading else cap

        body = _extract_article_text(article)
        hierarchy = _build_hierarchy(article)
        if heading:
            hierarchy = f"{hierarchy}/{heading}" if hierarchy else heading

        chunk = {
            "chunk_id": f"{doc_slug}-{idx}",
            "doc_type": "law",
            "domain": domain,
            "hierarchy": hierarchy,
            "heading": heading,
            "body": body,
            "pages": "",
            "char_count": len(body),
            "source_engine": "law_xml",
            "refs": [],
        }
        chunks.append(chunk)

    logger.info("%s: %d articles extracted", xml_path.name, len(chunks))
    return chunks
