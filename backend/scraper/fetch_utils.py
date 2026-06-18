import logging
import os
from urllib.parse import quote

import httpx

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Origin": "https://naar.io",
    "Referer": "https://naar.io/shop",
}


def _client(**kwargs) -> httpx.AsyncClient:
    # Avoid broken system proxies blocking Anthropic / Naar requests.
    return httpx.AsyncClient(trust_env=False, follow_redirects=True, **kwargs)


async def fetch_html(url: str, *, timeout: float = 30) -> str:
    async with _client(timeout=timeout, headers=DEFAULT_HEADERS) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            logger.warning("HTTP %s for %s", resp.status_code, url)
            return ""
        return resp.text


async def fetch_rendered_html(url: str, *, timeout: float = 60) -> str:
    """Fetch with JS rendering via ScraperAPI or Zyte when configured."""
    if settings.SCRAPERAPI_KEY:
        proxy_url = (
            f"http://api.scraperapi.com?api_key={settings.SCRAPERAPI_KEY}"
            f"&url={quote(url, safe='')}&render=true&country_code=in"
        )
        try:
            async with _client(timeout=timeout) as client:
                resp = await client.get(proxy_url)
                if resp.status_code < 400 and len(resp.text) > 500:
                    return resp.text
        except Exception as exc:
            logger.warning("ScraperAPI fetch failed: %s", exc)

    if settings.ZYTE_API_KEY:
        try:
            async with _client(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.zyte.com/v1/extract",
                    auth=(settings.ZYTE_API_KEY, ""),
                    json={"url": url, "browserHtml": True},
                )
                if resp.status_code < 400:
                    data = resp.json()
                    html = data.get("browserHtml") or ""
                    if html:
                        return html
        except Exception as exc:
            logger.warning("Zyte fetch failed: %s", exc)

    return await fetch_html(url, timeout=timeout)
