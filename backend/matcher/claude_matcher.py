from __future__ import annotations

import logging

from ai.claude_client import claude_available, claude_json

logger = logging.getLogger(__name__)

MATCH_SYSTEM = """You are a product matching engine for Indian e-commerce price parity monitoring.
Given a Naar (reference) product and competitor listings, decide which listings are the SAME product (or same SKU/variant).

Return ONLY valid JSON:
{
  "matches": [
    {
      "index": 0,
      "confidence": 0.92,
      "reason": "same product, matching size and material"
    }
  ]
}

Rules:
- confidence 0.0–1.0 (1.0 = exact same SKU/variant).
- Only include listings that are genuinely the same product — not similar category items.
- Variant attributes (size, color, pack count) must align when specified.
- Ignore listings below 0.65 confidence."""


async def claude_match_products(
    naar_product: dict,
    candidates: list[dict],
    min_confidence: float = 0.75,
) -> list[dict]:
    if not candidates or not claude_available():
        return []

    compact = []
    for i, c in enumerate(candidates[:12]):
        compact.append(
            {
                "index": i,
                "title": c.get("title", "")[:140],
                "price": c.get("price"),
                "platform": c.get("platform"),
                "seller_name": c.get("seller_name"),
                "sku": c.get("platform_id") or c.get("sku"),
            }
        )

    user = f"""Naar reference product:
- SKU: {naar_product.get('sku')}
- Name: {naar_product.get('name')}
- Variant: {naar_product.get('variant')}
- Price INR: {naar_product.get('price')}

Competitor listings:
{compact}

Minimum confidence threshold: {min_confidence}"""

    try:
        data = await claude_json(MATCH_SYSTEM, user, max_tokens=1536)
        matches = data.get("matches", []) if isinstance(data, dict) else []
    except Exception as exc:
        logger.warning("Claude matching failed for %s: %s", naar_product.get("sku"), exc)
        return []

    scored: list[dict] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        idx = m.get("index")
        conf = float(m.get("confidence", 0))
        if idx is None or conf < min_confidence:
            continue
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(candidates):
            continue
        scored.append(
            {
                **candidates[idx],
                "match_score": round(conf, 4),
                "match_method": "claude",
                "match_reason": m.get("reason", ""),
            }
        )

    return sorted(scored, key=lambda x: x["match_score"], reverse=True)
