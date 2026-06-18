import asyncio
import logging
import re

from bs4 import BeautifulSoup
from config import settings

from scraper.demo_data import DEMO_CANDIDATES

logger = logging.getLogger(__name__)


class AmazonScraper:
    SEARCH_URL = "https://www.amazon.in/s?k={query}&i=industrial"

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy or settings.BRIGHTDATA_PROXY or None

    async def search_product(self, query: str, max_results: int = 5) -> list[dict]:
        if settings.DEMO_MODE:
            return self._demo_results(query, max_results)

        html = ""
        if self.proxy:
            html = await self._fetch_with_proxy(query)
        if not html:
            html = await self._fetch_playwright_html(query)

        results = self._parse_results(html, max_results) if html else []
        if results:
            return results

        if settings.claude_enabled and html:
            from ai.claude_extractor import extract_product_listings

            return await extract_product_listings(html, query, "amazon", max_results=max_results)

        return [] if settings.is_production else self._demo_results(query, max_results)

    async def _fetch_with_proxy(self, query: str) -> str:
        try:
            from camoufox.async_api import AsyncCamoufox
        except ImportError:
            return await self._fetch_playwright_html(query)

        proxy_cfg = {"server": self.proxy} if self.proxy else None
        try:
            async with AsyncCamoufox(headless=True, proxy=proxy_cfg, geoip=True, humanize=True) as browser:
                page = await browser.new_page()
                await page.set_extra_http_headers({"Accept-Language": "en-IN,en;q=0.9"})
                url = self.SEARCH_URL.format(query=query.replace(" ", "+"))
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                if await page.query_selector("form[action='/errors/validateCaptcha']"):
                    logger.warning("Amazon CAPTCHA — configure BRIGHTDATA_PROXY")
                    return ""
                return await page.content()
        except Exception as exc:
            logger.error("Amazon proxy search '%s': %s", query, exc)
            return ""

    async def _fetch_playwright_html(self, query: str) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ""

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                url = self.SEARCH_URL.format(query=query.replace(" ", "+"))
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                html = await page.content()
                await browser.close()
                return html
        except Exception as exc:
            logger.error("Amazon playwright search '%s': %s", query, exc)
            return ""

    async def _playwright_search(self, query: str, max_results: int) -> list[dict]:
        html = await self._fetch_playwright_html(query)
        return self._parse_results(html, max_results) if html else []

    def _demo_results(self, query: str, max_results: int) -> list[dict]:
        q = query.lower()
        results = [c for c in DEMO_CANDIDATES["amazon"] if any(tok in c["title"].lower() for tok in q.split()[:3])]
        return results[:max_results] if results else DEMO_CANDIDATES["amazon"][:max_results]

    def _parse_results(self, html: str, max_results: int) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []

        for card in soup.select("[data-component-type='s-search-result']")[:max_results]:
            try:
                asin = card.get("data-asin", "")
                title_el = card.select_one("h2 a span")
                title = title_el.get_text(strip=True) if title_el else ""
                price_el = card.select_one(".a-price .a-offscreen")
                price = float(re.sub(r"[^\d.]", "", price_el.get_text() if price_el else "0") or 0)
                url_el = card.select_one("h2 a")
                href = url_el.get("href", "") if url_el else ""
                if href.startswith("/"):
                    url = "https://www.amazon.in" + href
                elif href.startswith("http"):
                    url = href.replace("://amazon.", "://www.amazon.")
                else:
                    url = ""
                rating_el = card.select_one(".a-icon-alt")
                rating = rating_el.get_text().split()[0] if rating_el else None
                if title and price > 0:
                    results.append(
                        {
                            "platform": "amazon",
                            "platform_id": asin,
                            "title": title,
                            "price": price,
                            "url": url,
                            "rating": rating,
                        }
                    )
            except Exception:
                continue
        return results
