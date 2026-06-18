"""Extract Naar shop catalog via Claude when DOM/API parsing is insufficient."""

from __future__ import annotations

import json
import logging
import re

from ai.claude_client import claude_available, claude_json
from ai.html_utils import prepare_html_for_claude
from config import settings

logger = logging.getLogger(__name__)

CATALOG_SYSTEM = """You extract the full product catalog from the Naar shop page (naar.io/shop).
Return ONLY valid JSON:
{
  "products": [
    {
      "sku": "unique-id-or-slug",
      "name": "Product title",
      "variant": "size/color or default",
      "price": 1299.0,
      "url": "https://naar.io/...",
      "category": "optional category",
      "image": "optional image url"
    }
  ]
}

Rules:
- Prices in INR as numbers (no currency symbol).
- Use the exact product title shown on Naar shop.
- url should point to the product detail page on naar.io when visible.
- sku can be slug from URL or product id from the page.
- Include every product visible in All Products and seller listings."""


def _normalize_catalog_rows(products: list, shop_url: str, source: str) -> list[dict]:
    rows: list[dict] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            price = float(str(item.get("price", 0)).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        sku = str(item.get("sku") or name[:40]).strip()
        url = str(item.get("url") or shop_url).strip()
        if url and not url.startswith("http"):
            url = f"https://naar.io{url if url.startswith('/') else '/' + url}"
        rows.append(
            {
                "sku": sku,
                "name": name,
                "variant": item.get("variant") or "default",
                "price": price,
                "url": url,
                "category": item.get("category"),
                "image": item.get("image"),
                "source": source,
            }
        )
    return rows


async def extract_naar_shop_catalog(html: str, shop_url: str) -> list[dict]:
    if not html or not claude_available():
        return []

    snippet = prepare_html_for_claude(html, max_chars=64_000)
    user = f"Shop URL: {shop_url}\n\nHTML:\n{snippet}"

    try:
        data = await claude_json(CATALOG_SYSTEM, user, max_tokens=8192)
        products = data.get("products", []) if isinstance(data, dict) else []
    except Exception as exc:
        logger.warning("Claude Naar catalog extraction failed: %s", exc)
        return []

    rows = _normalize_catalog_rows(products, shop_url, "naar_shop")
    logger.info("Claude extracted %s Naar shop products", len(rows))
    return rows


async def fetch_naar_catalog_via_web_fetch(shop_url: str) -> list[dict]:
    """Use Claude web_fetch when direct HTTP/Playwright cannot reach naar.io/shop."""
    if not claude_available():
        return []

    from anthropic import AsyncAnthropic
    import httpx

    http_client = httpx.AsyncClient(trust_env=False, timeout=120.0)
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, http_client=http_client)
    user = (
        f"Fetch {shop_url} and extract every product on the Naar shop page with exact INR price "
        "and product detail URL. Return complete JSON only."
    )

    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=8192,
            temperature=0,
            system=CATALOG_SYSTEM,
            tools=[
                {
                    "type": "web_fetch_20250910",
                    "name": "web_fetch",
                    "allowed_domains": ["naar.io", "www.naar.io"],
                    "max_uses": 3,
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        logger.warning("Claude web_fetch catalog failed: %s", exc)
        return []

    text = "\n".join(block.text for block in response.content if hasattr(block, "text")).strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            logger.warning("Claude web_fetch returned non-JSON catalog")
            return []
        data = json.loads(match.group())

    products = data.get("products", []) if isinstance(data, dict) else []
    rows = _normalize_catalog_rows(products, shop_url, "naar_web_fetch")
    logger.info("Claude web_fetch extracted %s Naar shop products", len(rows))
    return rows
