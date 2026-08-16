"""Web search backends: Google Custom Search / DuckDuckGo / SearXNG.

Unified interface:
    web_search(query, num_results, backend) -> [{"url", "title", "snippet"}, ...]

No automatic fallback between backends. Missing config raises immediately so
the backend used is always traceable.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_config_backend() -> str:
    settings_path = Path("settings.json")
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            backend = data.get("web_search_backend")
            if isinstance(backend, str):
                return backend
        except Exception:
            pass
    return "duckduckgo"


def web_search(query: str, num_results: int = 5, backend: str | None = None) -> list[dict]:
    """
    返値: [{"url": str, "title": str, "snippet": str}, ...]
    backend: "google" / "duckduckgo" / "searxng"（Noneならconfig既定値）
    """
    if backend is None:
        backend = _load_config_backend()

    logger.info("web_search: backend=%s query=%r num_results=%d", backend, query, num_results)

    if backend == "google":
        return _search_google(query, num_results)
    elif backend == "duckduckgo":
        return _search_duckduckgo(query, num_results)
    elif backend == "searxng":
        return _search_searxng(query, num_results)
    else:
        raise ValueError(
            f"未知のweb_searchバックエンド: {backend!r}。"
            "'google' / 'duckduckgo' / 'searxng' のいずれかを指定してください。"
        )


def _search_google(query: str, num_results: int) -> list[dict]:
    api_key = os.environ.get("GOOGLE_CSE_API_KEY")
    cx = os.environ.get("GOOGLE_CSE_CX")
    if not api_key or not cx:
        raise EnvironmentError(
            "Google Custom Search: GOOGLE_CSE_API_KEY と GOOGLE_CSE_CX を"
            "環境変数に設定してください。"
        )
    import requests
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": min(num_results, 10)}
    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code == 429:
        raise RuntimeError(
            "Google Custom Search: 日100クエリ無料枠を超過しました（429 Too Many Requests）。"
        )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("items", [])[:num_results]:
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


def _search_duckduckgo(query: str, num_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "DuckDuckGo検索には ddgs パッケージが必要です。"
                "`pip install ddgs` でインストールしてください。"
            )
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, region="jp-jp", max_results=num_results):
            results.append({
                "url": r.get("href", ""),
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
            })
    return results


def _search_searxng(query: str, num_results: int) -> list[dict]:
    base_url = os.environ.get("SEARXNG_URL")
    if not base_url:
        raise EnvironmentError(
            "SearXNG: SEARXNG_URL が環境変数に設定されていません"
            "（例: http://localhost:8888）。"
        )
    import requests
    url = f"{base_url.rstrip('/')}/search"
    params = {"q": query, "format": "json", "language": "ja", "count": num_results}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", [])[:num_results]:
        results.append({
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
        })
    return results
