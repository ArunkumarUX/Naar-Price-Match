import asyncio
import json
import logging
import re
from typing import AsyncGenerator

from bs4 import BeautifulSoup
from config import settings

from scraper.demo_data import DEMO_PRODUCTS
from scraper.fetch_utils import DEFAULT_HEADERS, fetch_html, fetch_rendered_html

logger = logging.getLogger(__name__)

SHOP_URL = settings.NAAR_SHOP_URL


class NaarScraper:
    BASE_URL = settings.NAAR_BASE_URL
    SHOP_URL = settings.NAAR_SHOP_URL

    async def get_all_products(self) -> AsyncGenerator[dict, None]:
        if settings.DEMO_MODE:
            logger.info("DEMO_MODE: returning sample Naar catalog (shop URLs)")
            for product in DEMO_PRODUCTS:
                yield product
            return

        products = await self._load_shop_catalog()
        if not products:
            products = await self._legacy_catalog_fallback()

        if not products:
            logger.warning("No products from %s — demo fallback disabled in production", self.SHOP_URL)
            if settings.is_production:
                return
            products = DEMO_PRODUCTS

        seen: set[str] = set()
        for product in products:
            key = product.get("sku") or product.get("name")
            if key in seen:
                continue
            seen.add(key)
            yield product

    async def _load_shop_catalog(self) -> list[dict]:
        """Primary: Naar API → Claude web_fetch → Playwright → rendered HTTP → Claude HTML."""
        api_products = await self._try_catalog_api()
        if api_products:
            logger.info("Naar API: %s products", len(api_products))
            return api_products

        if settings.claude_enabled:
            from ai.naar_catalog import fetch_naar_catalog_via_web_fetch

            web_fetch_products = await fetch_naar_catalog_via_web_fetch(self.SHOP_URL)
            if web_fetch_products:
                logger.info("Naar shop Claude web_fetch: %s products", len(web_fetch_products))
                return web_fetch_products

        playwright_products = await self._scrape_shop_playwright()
        if playwright_products:
            logger.info("Naar shop Playwright: %s products", len(playwright_products))
            return playwright_products

        if not settings.SCRAPERAPI_KEY and not settings.ZYTE_API_KEY:
            return []

        html_products = await self._scrape_shop_rendered()
        if html_products:
            logger.info("Naar shop rendered HTTP: %s products", len(html_products))
            return html_products

        if settings.claude_enabled:
            claude_products = await self._scrape_shop_claude()
            if claude_products:
                logger.info("Naar shop Claude: %s products", len(claude_products))
                return claude_products

        return []

    async def _try_catalog_api(self) -> list[dict]:
        import httpx

        candidates = [
            settings.NAAR_CATALOG_API,
            f"{self.BASE_URL}/api/v1/ecommerce/products",
            f"{self.BASE_URL}/api/ecommerce/products",
            f"{self.BASE_URL}/api/shop/products",
            f"{self.BASE_URL}/api/products",
            f"{self.BASE_URL}/api/v1/products",
            "https://api.naar.io/products",
            "https://api.naar.io/v1/products",
            "https://api.naar.io/ecommerce/products",
            "https://api.naar.io/shop/products",
            f"{self.BASE_URL}/products.json",
        ]
        candidates = [u for u in dict.fromkeys(candidates) if u]

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, trust_env=False) as client:
            headers = {
                **DEFAULT_HEADERS,
                "Accept": "application/json",
                "Origin": "https://naar.io",
                "Referer": "https://naar.io/shop",
            }
            for url in candidates:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code >= 400:
                        continue
                    data = resp.json()
                    parsed = self._normalize_api_payload(data)
                    if parsed:
                        return parsed
                except Exception as exc:
                    logger.debug("Naar API %s: %s", url, exc)
        return []

    def _normalize_api_payload(self, data) -> list[dict]:
        items = data
        if isinstance(data, dict):
            for key in ("products", "data", "items", "results", "content"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break

        if not isinstance(items, list):
            return []

        rows: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("title") or item.get("productName")
            price = item.get("price") or item.get("sellingPrice") or item.get("mrp")
            if isinstance(price, dict):
                price = price.get("amount") or price.get("value")
            if not name:
                continue
            try:
                price_f = float(str(price).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if price_f <= 0:
                continue
            slug = item.get("slug") or item.get("handle") or item.get("id")
            rows.append(
                {
                    "sku": str(item.get("sku") or slug or name[:30]),
                    "name": str(name),
                    "variant": item.get("variant") or item.get("size") or "default",
                    "price": price_f,
                    "url": item.get("url")
                    or item.get("productUrl")
                    or (f"{self.BASE_URL}/product/{slug}" if slug else self.SHOP_URL),
                    "category": item.get("category") or item.get("product_type"),
                    "image": item.get("image") or item.get("thumbnail"),
                    "source": "naar_api",
                }
            )
        return rows

    async def _scrape_shop_playwright(self) -> list[dict]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        from scraper.playwright_utils import launch_chromium

        captured_json: list[dict] = []

        try:
            async with async_playwright() as p:
                browser = await launch_chromium(p)
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 900},
                )
                page = await ctx.new_page()

                async def on_response(response):
                    if response.request.resource_type not in ("xhr", "fetch"):
                        return
                    try:
                        if "json" not in (response.headers.get("content-type") or ""):
                            return
                        body = await response.text()
                        if len(body) > 800_000:
                            return
                        data = json.loads(body)
                        parsed = self._normalize_api_payload(data)
                        if parsed:
                            captured_json.extend(parsed)
                    except Exception:
                        pass

                page.on("response", on_response)

                try:
                    await page.goto(self.SHOP_URL, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(3)
                    for _ in range(10):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1)
                    dom_products = await page.evaluate(
                        """() => {
                        const out = [];
                        const seen = new Set();
                        const priceRe = /₹\\s*([\\d,]+(?:\\.\\d{1,2})?)/;
                        const nodes = document.querySelectorAll(
                          'a[href*="/product"], a[href*="/p/"], [class*="product" i], [data-testid*="product" i]'
                        );
                        nodes.forEach((el) => {
                          const text = (el.innerText || '').trim();
                          if (!text || text.length < 4) return;
                          const m = text.match(priceRe);
                          if (!m) return;
                          const price = parseFloat(m[1].replace(/,/g, ''));
                          if (!price || price <= 0) return;
                          const link = el.closest('a') || (el.tagName === 'A' ? el : el.querySelector('a'));
                          const href = link ? link.href : '';
                          const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                          const name = lines.find(l => !priceRe.test(l) && l.length > 3) || lines[0];
                          const key = (href || name) + price;
                          if (seen.has(key)) return;
                          seen.add(key);
                          out.push({ name, price, url: href || '', sku: href.split('/').filter(Boolean).pop() || name.slice(0,24) });
                        });
                        return out;
                    }"""
                    )
                    for row in dom_products or []:
                        if row.get("name") and row.get("price"):
                            captured_json.append(
                                {
                                    "sku": row.get("sku") or row["name"][:30],
                                    "name": row["name"],
                                    "variant": "default",
                                    "price": float(row["price"]),
                                    "url": row.get("url") or self.SHOP_URL,
                                    "source": "naar_shop_dom",
                                }
                            )
                except Exception as exc:
                    logger.error("Playwright shop scrape failed: %s", exc)
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning("Playwright unavailable for Naar shop: %s", exc)
            return []

        return self._dedupe_products(captured_json)

    async def _scrape_shop_rendered(self) -> list[dict]:
        from ai.naar_catalog import extract_naar_shop_catalog

        try:
            html = await fetch_rendered_html(self.SHOP_URL)
        except Exception as exc:
            logger.debug("Rendered shop fetch failed: %s", exc)
            return []
        if not html:
            return []

        products = self._parse_embedded_json(html)
        if products:
            return products

        if settings.claude_enabled and len(html) > 500:
            return await extract_naar_shop_catalog(html, self.SHOP_URL)
        return []

    async def _scrape_shop_httpx(self) -> list[dict]:
        try:
            html = await fetch_html(self.SHOP_URL)
        except Exception as exc:
            logger.debug("HTTP shop fetch failed: %s", exc)
            return []

        products = self._parse_embedded_json(html)
        if products:
            return products

        soup = BeautifulSoup(html, "lxml")
        rows: list[dict] = []
        for script in soup.find_all("script"):
            text = script.string or ""
            if "product" not in text.lower():
                continue
            for match in re.finditer(r"\{[^{}]*\"(?:title|name)\"[^{}]*\"(?:price|sellingPrice)\"[^{}]*\}", text):
                try:
                    blob = json.loads(match.group(0))
                    parsed = self._normalize_api_payload([blob])
                    rows.extend(parsed)
                except Exception:
                    continue
        return self._dedupe_products(rows)

    async def _scrape_shop_claude(self) -> list[dict]:
        from ai.naar_catalog import extract_naar_shop_catalog

        try:
            html = await fetch_rendered_html(self.SHOP_URL)
        except Exception as exc:
            logger.warning("Cannot fetch shop for Claude: %s", exc)
            return []
        return await extract_naar_shop_catalog(html, self.SHOP_URL)

    def _parse_embedded_json(self, html: str) -> list[dict]:
        for pattern in [
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                parsed = self._normalize_api_payload(data)
                if not parsed and isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, dict):
                            parsed = self._normalize_api_payload(v)
                            if parsed:
                                break
                if parsed:
                    return self._dedupe_products(parsed)
            except Exception:
                continue
        return []

    async def _legacy_catalog_fallback(self) -> list[dict]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        from scraper.playwright_utils import launch_chromium

        try:
            async with async_playwright() as p:
                browser = await launch_chromium(p)
                page = await browser.new_page()
                products = await self._try_shopify_api(page)
                if not products:
                    products = await self._try_sitemap(page)
                await browser.close()
            return products
        except Exception as exc:
            logger.warning("Legacy catalog Playwright fallback failed: %s", exc)
            return []

    async def _try_shopify_api(self, page) -> list[dict]:
        url = f"{self.BASE_URL}/products.json?limit=250"
        products: list[dict] = []
        page_num = 1
        while True:
            try:
                paged = f"{url}&page={page_num}"
                resp = await page.goto(paged, timeout=10000)
                if not resp or resp.status != 200:
                    break
                data = json.loads(await page.evaluate("document.body.innerText"))
                batch = data.get("products", [])
                if not batch:
                    break
                for item in batch:
                    for variant in item.get("variants", []):
                        products.append(
                            {
                                "sku": variant.get("sku") or str(variant.get("id")),
                                "name": item.get("title", ""),
                                "variant": variant.get("title", "default"),
                                "price": float(variant.get("price", 0)),
                                "url": f"{self.BASE_URL}/products/{item.get('handle')}",
                                "category": item.get("product_type", ""),
                                "source": "shopify",
                            }
                        )
                page_num += 1
            except Exception:
                break
        return products

    async def _try_sitemap(self, page) -> list[dict]:
        urls: list[str] = []
        for sitemap in ["/sitemap.xml", "/sitemap_products_1.xml"]:
            try:
                resp = await page.goto(self.BASE_URL + sitemap, timeout=10000)
                if resp and resp.status == 200:
                    soup = BeautifulSoup(await page.content(), "lxml-xml")
                    for loc in soup.find_all("loc"):
                        if "/product" in loc.text:
                            urls.append(loc.text)
            except Exception:
                continue
        return []

    @staticmethod
    def _dedupe_products(products: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for p in products:
            key = p.get("sku") or p.get("name", "")
            if key in seen:
                continue
            seen.add(key)
            if not p.get("url"):
                p["url"] = SHOP_URL
            out.append(p)
        return out
