"""Web text extraction with tier classification.

fetch_and_extract(url) -> {url, title, text, content_type, tier, tier_label}

Tier is determined by domain suffix match against data/web_tiers.yaml.
Errors (timeout, connection failure) return text="" without raising.
"""
import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_TIERS_PATH = Path("data/web_tiers.yaml")
_tier_cache: dict | None = None


def _load_tiers() -> dict:
    global _tier_cache
    if _tier_cache is None:
        if _TIERS_PATH.exists():
            import yaml
            with open(_TIERS_PATH, encoding="utf-8") as f:
                _tier_cache = yaml.safe_load(f) or {}
        else:
            _tier_cache = {}
    return _tier_cache


def _classify_tier(url: str) -> tuple[int, str]:
    """Return (tier_int, tier_label). Tier 3 is default when no match."""
    tiers = _load_tiers()
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""

    tier1_domains: list = tiers.get("tier_1") or []
    tier2_domains: list = tiers.get("tier_2") or []

    for d in tier1_domains:
        if hostname == d or hostname.endswith("." + d):
            return 1, "官公庁・JIS・業界団体・メーカー公式"

    for d in tier2_domains:
        if hostname == d or hostname.endswith("." + d):
            return 2, "商社・技術解説サイト"

    return 3, "その他"


def fetch_and_extract(url: str, timeout: int = 15) -> dict:
    """
    返値: {"url": str, "title": str, "text": str,
           "content_type": str, "tier": int, "tier_label": str}

    PDFはtext=""で返す。タイムアウト・接続エラーもtext=""で返す（パイプラインを止めない）。
    """
    tier, tier_label = _classify_tier(url)

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
                "tier": tier, "tier_label": tier_label,
            }

        html = resp.text
        title = ""
        text = ""

        # Try trafilatura first
        try:
            import trafilatura
            extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
            if extracted:
                text = extracted[:3000]
            meta = trafilatura.extract_metadata(html)
            if meta and meta.title:
                title = meta.title
        except ImportError:
            pass

        # Fallback: BeautifulSoup
        if not text:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                if not title:
                    t_tag = soup.find("title")
                    title = t_tag.get_text(strip=True) if t_tag else ""
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
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
            "tier": tier,
            "tier_label": tier_label,
        }

    except Exception as e:
        logger.warning("fetch_and_extract failed for %s: %s", url, e)
        return {
            "url": url, "title": "", "text": "",
            "content_type": "error",
            "tier": tier, "tier_label": tier_label,
        }
