import logging
import re

import httpx
from bs4 import BeautifulSoup
from config import settings

from scraper.demo_data import DEMO_CANDIDATES

logger = logging.getLogger(__name__)


class FlipkartScraper:
    SEARCH_URL = "https://www.flipkart.com/search?q={query}"

    def __init__(self):
        self.scraper_key = settings.SCRAPERAPI_KEY

    async def _fetch(self, url: str) -> str:
        if not self.scraper_key:
            raise RuntimeError("SCRAPERAPI_KEY not configured")
        api_url = (
            f"http://api.scraperapi.com?api_key={self.scraper_key}"
            f"&url={url}&render=true&country_code=in"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            return resp.text

    async def search_product(self, query: str, max_results: int = 5) -> list[dict]:
        if settings.DEMO_MODE:
            return self._demo_results(query, max_results)

        html = ""
        try:
            if self.scraper_key:
                url = self.SEARCH_URL.format(query=query.replace(" ", "+"))
                html = await self._fetch(url)
            else:
                from scraper.fetch_utils import fetch_html

                url = self.SEARCH_URL.format(query=query.replace(" ", "+"))
                html = await fetch_html(url)
        except Exception as exc:
            logger.error("Flipkart fetch '%s': %s", query, exc)

        results = self._parse_results(html, max_results) if html else []
        if results:
            return results

        if settings.claude_enabled and html:
            from ai.claude_extractor import extract_product_listings

            return await extract_product_listings(html, query, "flipkart", max_results=max_results)

        return []

    def _demo_results(self, query: str, max_results: int) -> list[dict]:
        q = query.lower()
        results = [c for c in DEMO_CANDIDATES["flipkart"] if any(tok in c["title"].lower() for tok in q.split()[:3])]
        return results[:max_results] if results else DEMO_CANDIDATES["flipkart"][:max_results]

    def _parse_results(self, html: str, max_results: int) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        cards = soup.select("div[data-id]")[: max_results * 3]

        for card in cards:
            try:
                title_el = card.select_one("a.s1Q9rs, .IRpwTa, ._4rR01T, a[title]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True) or title_el.get("title", "")
                price_el = card.select_one("._30jeq3, .Nx9bqj")
                price = float(re.sub(r"[^\d.]", "", price_el.get_text() if price_el else "0") or 0)
                url_el = card.select_one("a[href*='/p/']")
                url = "https://www.flipkart.com" + url_el["href"] if url_el else ""
                pid_match = re.search(r"/p/([^?]+)", url)
                pid = pid_match.group(1) if pid_match else ""
                if title and price > 0:
                    results.append(
                        {
                            "platform": "flipkart",
                            "platform_id": pid,
                            "title": title,
                            "price": price,
                            "url": url,
                        }
                    )
            except Exception:
                continue
            if len(results) >= max_results:
                break
        return results
