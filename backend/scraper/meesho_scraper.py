import asyncio
import logging
import re

from bs4 import BeautifulSoup
from config import settings

from scraper.demo_data import DEMO_CANDIDATES

logger = logging.getLogger(__name__)


class MeeshoScraper:
    SEARCH_URL = "https://www.meesho.com/search?q={query}"

    async def search_product(self, query: str, max_results: int = 5) -> list[dict]:
        if settings.DEMO_MODE:
            return self._demo_results(query, max_results)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [] if settings.is_production else self._demo_results(query, max_results)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                url = self.SEARCH_URL.format(query=query.replace(" ", "+"))
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                html = await page.content()
            except Exception as exc:
                logger.error("Meesho search '%s': %s", query, exc)
                html = ""
            finally:
                await browser.close()

        results = self._parse_results(html, max_results)
        if results:
            return results

        if settings.claude_enabled and html:
            from ai.claude_extractor import extract_product_listings

            return await extract_product_listings(html, query, "meesho", max_results=max_results)

        return []

    def _demo_results(self, query: str, max_results: int) -> list[dict]:
        q = query.lower()
        results = [c for c in DEMO_CANDIDATES["meesho"] if any(tok in c["title"].lower() for tok in q.split()[:3])]
        return results[:max_results] if results else DEMO_CANDIDATES["meesho"][:max_results]

    def _parse_results(self, html: str, max_results: int) -> list[dict]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []

        for card in soup.select("[data-testid], .ProductList__GridCol, a[href*='/p/']")[: max_results * 4]:
            try:
                title_el = card.select_one("p, h2, span")
                title = title_el.get_text(strip=True) if title_el else card.get("aria-label", "")
                text = card.get_text(" ", strip=True)
                prices = re.findall(r"₹\s*([\d,]+)", text)
                price = float(prices[0].replace(",", "")) if prices else 0
                href = card.get("href", "")
                url = href if href.startswith("http") else f"https://www.meesho.com{href}"
                if title and price > 0:
                    results.append(
                        {
                            "platform": "meesho",
                            "platform_id": url.split("/")[-1],
                            "title": title[:120],
                            "price": price,
                            "url": url,
                        }
                    )
            except Exception:
                continue
            if len(results) >= max_results:
                break
        return results
