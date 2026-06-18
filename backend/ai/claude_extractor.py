from __future__ import annotations

import logging

from ai.claude_client import claude_available, claude_json
from ai.html_utils import prepare_html_for_claude

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = """You extract Indian e-commerce product listings from HTML search results.
Return ONLY valid JSON — no markdown, no commentary.

Schema:
{
  "products": [
    {
      "title": "string",
      "price": 1234.56,
      "url": "https://...",
      "platform_id": "optional-id"
    }
  ]
}

Rules:
- Prices in INR (numbers only, no ₹ symbol in JSON).
- Skip ads, sponsored placeholders, and items without a price.
- Prefer exact matches to the search query.
- platform_id can be ASIN, SKU slug, or URL path segment."""


async def extract_product_listings(
    html: str,
    query: str,
    platform: str,
    *,
    seller_name: str | None = None,
    base_url: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    if not html or not claude_available():
        return []

    snippet = prepare_html_for_claude(html)
    context = f"Platform: {platform}"
    if seller_name:
        context += f"\nSeller store: {seller_name}"
    if base_url:
        context += f"\nBase URL: {base_url}"

    user = f"""{context}
Search query: {query}
Max results: {max_results}

HTML:
{snippet}"""

    try:
        data = await claude_json(EXTRACT_SYSTEM, user, max_tokens=2048)
        products = data.get("products", []) if isinstance(data, dict) else []
    except Exception as exc:
        logger.warning("Claude HTML extraction failed (%s): %s", platform, exc)
        return []

    results: list[dict] = []
    for item in products[:max_results]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        price = item.get("price")
        url = str(item.get("url", "")).strip()
        if not title or price is None:
            continue
        try:
            price_f = float(str(price).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price_f <= 0:
            continue

        if url and base_url and not url.startswith("http"):
            url = base_url.rstrip("/") + ("" if url.startswith("/") else "/") + url

        entry = {
            "platform": platform,
            "platform_id": str(item.get("platform_id") or url.split("/")[-1] or title[:40]),
            "title": title[:160],
            "price": price_f,
            "url": url or base_url or "",
        }
        if seller_name:
            entry["seller_name"] = seller_name
        results.append(entry)

    logger.info("Claude extracted %s listings for %s / %s", len(results), platform, query[:40])
    return results
