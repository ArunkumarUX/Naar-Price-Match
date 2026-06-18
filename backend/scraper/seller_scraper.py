import asyncio
import logging
import re

import httpx
from bs4 import BeautifulSoup
from config import settings

from scraper.demo_data import DEMO_CANDIDATES
from scraper.seller_registry import get_seller_by_url, load_sellers

logger = logging.getLogger(__name__)

SEARCH_PATHS = [
    "/search?q={query}",
    "/search?query={query}",
    "/products?search={query}",
    "/collections/all?q={query}",
    "/?s={query}",
]


class SellerScraper:
    """Search Naar authorized seller websites for product matches."""

    def __init__(self, max_sellers_per_scan: int = 15):
        self.max_sellers = max_sellers_per_scan

    async def search_product(
        self,
        query: str,
        max_results: int = 5,
        seller_urls: list[str] | None = None,
        category: str | None = None,
    ) -> list[dict]:
        sellers = load_sellers()
        if category:
            sellers = [s for s in sellers if s.get("category", "").lower() == category.lower()]

        if seller_urls:
            url_set = {u.rstrip("/").lower() for u in seller_urls}
            sellers = [s for s in sellers if s["website"].rstrip("/").lower() in url_set]

        sellers = sellers[: self.max_sellers]
        if not sellers:
            return [] if settings.is_production else self._demo_results(query, max_results)

        if settings.DEMO_MODE:
            return self._demo_results_for_sellers(query, sellers, max_results)

        results: list[dict] = []
        sem = asyncio.Semaphore(5)

        async def scan_one(seller: dict) -> list[dict]:
            async with sem:
                return await self._search_seller_site(seller, query, max_results)

        batches = await asyncio.gather(*[scan_one(s) for s in sellers], return_exceptions=True)
        for batch in batches:
            if isinstance(batch, list):
                results.extend(batch)

        results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return results[:max_results]

    async def _search_seller_site(self, seller: dict, query: str, max_results: int) -> list[dict]:
        base = seller["website"].rstrip("/")
        encoded = query.replace(" ", "+")

        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            for path_tpl in SEARCH_PATHS:
                try:
                    url = base + path_tpl.format(query=encoded)
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 NaarPriceMonitor/1.0"})
                    if resp.status_code >= 400:
                        continue
                    parsed = self._parse_page(resp.text, seller, base, max_results)
                    if parsed:
                        return parsed
                    if settings.claude_enabled:
                        from ai.claude_extractor import extract_product_listings

                        claude_hits = await extract_product_listings(
                            resp.text,
                            query,
                            "seller",
                            seller_name=seller["store_name"],
                            base_url=base,
                            max_results=max_results,
                        )
                        for hit in claude_hits:
                            hit["seller_id"] = seller["id"]
                            hit["seller_website"] = seller["website"]
                            hit["seller_category"] = seller.get("category")
                        if claude_hits:
                            return claude_hits
                except Exception as exc:
                    logger.debug("Seller search %s: %s", seller["store_name"], exc)

            try:
                resp = await client.get(base, headers={"User-Agent": "Mozilla/5.0 NaarPriceMonitor/1.0"})
                if resp.status_code < 400:
                    parsed = self._parse_page(resp.text, seller, base, max_results)
                    if parsed:
                        return parsed
                    if settings.claude_enabled:
                        from ai.claude_extractor import extract_product_listings

                        claude_hits = await extract_product_listings(
                            resp.text,
                            query,
                            "seller",
                            seller_name=seller["store_name"],
                            base_url=base,
                            max_results=max_results,
                        )
                        for hit in claude_hits:
                            hit["seller_id"] = seller["id"]
                            hit["seller_website"] = seller["website"]
                            hit["seller_category"] = seller.get("category")
                        return claude_hits
            except Exception as exc:
                logger.warning("Seller scrape failed %s: %s", seller["store_name"], exc)
        return []

    def _parse_page(self, html: str, seller: dict, base_url: str, max_results: int) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        q_tokens = set(re.sub(r"[^a-z0-9\s]", "", seller.get("store_name", "").lower()).split())

        selectors = [
            ".product-card", ".product-item", "[data-product]", ".grid-product",
            "article.product", ".product", "li.product", ".woocommerce-loop-product",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break
        if not cards:
            cards = soup.select("a[href*='product'], a[href*='/p/'], a[href*='/collections/']")

        for card in cards[: max_results * 4]:
            title_el = card.select_one("h2, h3, .product-title, .title, [class*='title'], a")
            title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)[:120]
            if len(title) < 4:
                continue

            price = self._extract_price(card)
            link_el = card if card.name == "a" else card.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = base_url + ("" if href.startswith("/") else "/") + href

            if price <= 0:
                continue

            results.append(
                {
                    "platform": "seller",
                    "platform_id": href.split("/")[-1] or seller["id"],
                    "title": title[:160],
                    "price": price,
                    "url": href or base_url,
                    "seller_name": seller["store_name"],
                    "seller_id": seller["id"],
                    "seller_website": seller["website"],
                    "seller_category": seller.get("category"),
                }
            )
            if len(results) >= max_results:
                break

        return results

    def _extract_price(self, el) -> float:
        text = el.get_text(" ", strip=True)
        for sel in [".price", ".amount", "[class*='price']", "span.money", "ins .amount"]:
            p = el.select_one(sel)
            if p:
                text = p.get_text(strip=True)
                break
        nums = re.findall(r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", text.replace(",", ""))
        if nums:
            try:
                return float(nums[0].replace(",", ""))
            except ValueError:
                pass
        return 0.0

    def _demo_results(self, query: str, max_results: int) -> list[dict]:
        return self._demo_results_for_sellers(query, load_sellers()[:5], max_results)

    def _demo_results_for_sellers(self, query: str, sellers: list[dict], max_results: int) -> list[dict]:
        q = query.lower()
        base_candidates = DEMO_CANDIDATES.get("seller", [])
        results: list[dict] = []

        for i, seller in enumerate(sellers[:max_results]):
            template = base_candidates[i % len(base_candidates)] if base_candidates else {}
            variance = 0.88 + (i % 5) * 0.05
            base_price = 1299.0
            for tok in q.split():
                if tok in seller.get("store_name", "").lower() or tok in seller.get("category", "").lower():
                    base_price = 999.0 + i * 120
                    break

            results.append(
                {
                    "platform": "seller",
                    "platform_id": f"{seller['id']}-demo",
                    "title": f"{query} — {seller['store_name']}",
                    "price": round(base_price * variance, 2),
                    "url": seller["website"],
                    "seller_name": seller["store_name"],
                    "seller_id": seller["id"],
                    "seller_website": seller["website"],
                    "seller_category": seller.get("category"),
                }
            )
        return results[:max_results]
