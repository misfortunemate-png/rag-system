"""Web text extraction with tier classification, and e-Gov law API.

fetch_and_extract(url) -> {url, title, text, content_type,
                           tier, tier_label, tag, verified, category}

fetch_law_text(law_id) -> {law_id, url, title, text,
                           tier, tier_label, tag, source, verified, category}

Tier is determined by matching against data/web_tiers.yaml:
  1. negative_examples (URL prefix) → tier=3, negative tag
  2. go.jp domain suffix → tier=1
  3. tier_2 (URL prefix) → tier=2
  4. tier_3 (URL prefix) → tier=3
  5. default → tier=3, "【tier-3：未分類】"

Errors return text="" without raising (pipeline continues).
"""
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_TIERS_PATH = Path("data/web_tiers.yaml")
_tier_raw: dict | None = None
_lookup: dict | None = None

# 法令名 → e-Gov法令API v1 法令ID（web_tiers.yamlのtier_1 descriptionより）
LAW_ID_MAP: dict[str, str] = {
    "建築基準法": "325AC0000000201",
    "建築基準法施行令": "325CO0000000338",
    "消防法": "323AC1000000186",
    "電気事業法": "339AC0000000170",
    "労働安全衛生法": "347AC0000000057",
    "省エネ法": "347AC0000000049",
    "水道法": "332AC0000000177",
    "下水道法": "333AC0000000079",
}


def _load_tiers() -> dict:
    global _tier_raw
    if _tier_raw is None:
        if _TIERS_PATH.exists():
            import yaml
            with open(_TIERS_PATH, encoding="utf-8") as f:
                _tier_raw = yaml.safe_load(f) or {}
        else:
            _tier_raw = {}
    return _tier_raw


def _build_lookup() -> dict:
    """Build URL lookup tables from web_tiers.yaml. Cached at module level."""
    global _lookup
    if _lookup is not None:
        return _lookup

    tiers = _load_tiers()
    result: dict = {
        "negative": [],   # [(prefix, tag)]
        "tier2": [],      # [(prefix, tag, verified, category, access_restriction)]
        "tier3": [],      # [(prefix, tag)]
    }

    for entry in (tiers.get("negative_examples") or []):
        url = entry.get("url", "")
        tag = entry.get("tag", "【tier-3：未分類】")
        if url:
            result["negative"].append((url, tag))

    for entry in (tiers.get("tier_2") or []):
        url = entry.get("url", "")
        tag = entry.get("tag", "【tier-2：仕様書】")
        verified = bool(entry.get("verified", True))
        category = entry.get("category")
        access_restriction = entry.get("access_restriction")
        if url:
            result["tier2"].append((url, tag, verified, category, access_restriction))

    for entry in (tiers.get("tier_3") or []):
        url = entry.get("url", "")
        tag = entry.get("tag", "【tier-3：独自知見】")
        if url:
            result["tier3"].append((url, tag))

    _lookup = result
    return result


def _classify_tier_and_meta(url: str) -> dict:
    """
    Returns {tier, tag, tier_label, verified, category, access_restriction}.

    Priority:
      1. negative_examples (URL prefix match)
      2. go.jp domain suffix → tier=1
      3. tier_2 (URL prefix match)
      4. tier_3 (URL prefix match)
      5. default: tier=3, "【tier-3：未分類】"
    """
    lk = _build_lookup()

    # 1. negative_examples
    for prefix, tag in lk["negative"]:
        if url.startswith(prefix):
            return {
                "tier": 3, "tag": tag, "tier_label": tag,
                "verified": False, "category": None, "access_restriction": None,
            }

    # 2. tier_1 (go.jp domain suffix)
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""
    if hostname == "go.jp" or hostname.endswith(".go.jp"):
        return {
            "tier": 1, "tag": "【tier-1：法令原文】", "tier_label": "【tier-1：法令原文】",
            "verified": True, "category": None, "access_restriction": None,
        }

    # 3. tier_2 (URL prefix match)
    for prefix, tag, verified, category, access_restriction in lk["tier2"]:
        if url.startswith(prefix):
            return {
                "tier": 2, "tag": tag, "tier_label": tag,
                "verified": verified, "category": category,
                "access_restriction": access_restriction,
            }

    # 4. tier_3 (URL prefix match)
    for prefix, tag in lk["tier3"]:
        if url.startswith(prefix):
            return {
                "tier": 3, "tag": tag, "tier_label": tag,
                "verified": True, "category": None, "access_restriction": None,
            }

    # 5. default
    return {
        "tier": 3, "tag": "【tier-3：未分類】", "tier_label": "【tier-3：未分類】",
        "verified": False, "category": None, "access_restriction": None,
    }


def fetch_and_extract(url: str, timeout: int = 15) -> dict:
    """
    Returns:
        {"url", "title", "text", "content_type",
         "tier", "tier_label", "tag", "verified", "category"}

    PDF → text="". Timeout/error → text="" (pipeline continues).
    access_restriction entries: fetch attempted; errors logged at INFO level.
    """
    meta = _classify_tier_and_meta(url)
    tier = meta["tier"]
    tag = meta["tag"]
    tier_label = meta["tier_label"]
    access_restriction = meta.get("access_restriction")

    if access_restriction:
        logger.info("fetch_and_extract: access_restriction=%r for %s", access_restriction, url)

    try:
        import requests
        resp = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RagSystemBot/1.0)"},
            allow_redirects=True,
        )
        content_type = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()

        if content_type == "application/pdf" or url.lower().endswith(".pdf"):
            return {
                "url": url, "title": "", "text": "",
                "content_type": "application/pdf",
                "tier": tier, "tier_label": tier_label, "tag": tag,
                "verified": meta["verified"], "category": meta["category"],
            }

        html = resp.text
        title = ""
        text = ""

        try:
            import trafilatura
            extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
            if extracted:
                text = extracted[:3000]
            m = trafilatura.extract_metadata(html)
            if m and m.title:
                title = m.title
        except ImportError:
            pass

        if not text:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                if not title:
                    t_el = soup.find("title")
                    title = t_el.get_text(strip=True) if t_el else ""
                for el in soup(["script", "style", "nav", "footer", "header"]):
                    el.decompose()
                main = soup.find("main") or soup.find("article") or soup.find("body")
                if main:
                    text = main.get_text(separator="\n", strip=True)[:3000]
            except ImportError:
                pass

        return {
            "url": url,
            "title": title,
            "text": text,
            "content_type": content_type or "text/html",
            "tier": tier, "tier_label": tier_label, "tag": tag,
            "verified": meta["verified"], "category": meta["category"],
        }

    except Exception as e:
        if access_restriction:
            logger.info("fetch_and_extract: blocked/timeout for %s (%s): %s", url, access_restriction, e)
        else:
            logger.warning("fetch_and_extract failed for %s: %s", url, e)
        return {
            "url": url, "title": "", "text": "",
            "content_type": "error",
            "tier": tier, "tier_label": tier_label, "tag": tag,
            "verified": meta["verified"], "category": meta["category"],
        }


# ── e-Gov法令API ─────────────────────────────────────────────────────────────


def fetch_law_text(law_id: str) -> dict:
    """
    e-Gov法令API v1から法令XMLを取得しテキストに変換する。
    Returns: {"law_id", "url", "title", "text",
              "tier", "tier_label", "tag", "source", "verified", "category"}

    レート制限: 呼び出し側で1秒以上のインターバルを設けること。
    エラー時: text="" で返す（例外は送出しない）。
    """
    import requests
    import xml.etree.ElementTree as ET

    endpoint = f"https://laws.e-gov.go.jp/api/1/lawdata/{law_id}"
    try:
        resp = requests.get(
            endpoint, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RagSystemBot/1.0)"},
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.content)

        title_el = root.find(".//LawTitle")
        title = title_el.text.strip() if (title_el is not None and title_el.text) else ""

        parts: list[str] = []
        for el in root.iter():
            if el.text and el.text.strip():
                parts.append(el.text.strip())
            if el.tail and el.tail.strip():
                parts.append(el.tail.strip())
        text = "\n".join(parts)[:3000]

        logger.info("fetch_law_text: law_id=%s title=%r text_len=%d", law_id, title, len(text))

        return {
            "law_id": law_id,
            "url": endpoint,
            "title": title,
            "text": text,
            "tier": 1,
            "tier_label": "【tier-1：法令原文】",
            "tag": "【tier-1：法令原文】",
            "source": "e-gov-law-api",
            "verified": True,
            "category": None,
        }
    except Exception as e:
        logger.warning("fetch_law_text failed for %s: %s", law_id, e)
        return {
            "law_id": law_id,
            "url": endpoint,
            "title": "",
            "text": "",
            "tier": 1,
            "tier_label": "【tier-1：法令原文】",
            "tag": "【tier-1：法令原文】",
            "source": "e-gov-law-api",
            "verified": True,
            "category": None,
        }
