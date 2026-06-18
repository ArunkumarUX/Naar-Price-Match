from __future__ import annotations

from engine.price_comparator import PriceComparator
from engine.rule_engine import get_active_rule
from scraper.platform_urls import normalize_competitor_url
from models.database import AlertType, Severity


def classify_channel(naar_price: float, channel_price: float | None) -> dict:
    if channel_price is None or channel_price <= 0:
        return {"status": "missing", "deviation_pct": None, "label": "Unmatched"}

    deviation = ((naar_price - channel_price) / naar_price) * 100
    comparator = PriceComparator(get_active_rule())

    if deviation >= 5:
        status, label = "lower", f"−{abs(deviation):.0f}% Lower"
    elif deviation <= -50:
        status, label = "higher", f"+{abs(deviation):.0f}% Higher"
    elif deviation <= -15:
        status, label = "violation", "MAP Violation"
    else:
        status, label = "ok", "Parity OK"

    return {
        "status": status,
        "deviation_pct": round(deviation, 2),
        "label": label,
    }


def build_comparison_row(product: dict, matches_by_platform: dict) -> dict:
    naar_price = float(product.get("price", product.get("base_price", 0)))
    row = {
        "sku": product.get("sku"),
        "name": product.get("name"),
        "variant": product.get("variant"),
        "naar_price": naar_price,
        "naar_url": product.get("url"),
        "channels": {},
    }

    for platform in ("amazon", "flipkart", "meesho"):
        match = matches_by_platform.get(platform)
        if not match:
            row["channels"][platform] = {
                "platform": platform,
                "price": None,
                "url": None,
                "status": "missing",
                "deviation_pct": None,
                "label": "Unmatched",
                "match_confidence": None,
            }
            continue
        ch = classify_channel(naar_price, float(match.get("price", 0)))
        title = match.get("title") or product.get("name", "")
        url = normalize_competitor_url(platform, title, match.get("url"))
        row["channels"][platform] = {
            "platform": platform,
            "price": match.get("price"),
            "url": url,
            "is_search_link": match.get("is_search_link") or "/search" in (url or "") or "/s?" in (url or ""),
            "match_confidence": match.get("match_score"),
            "match_method": match.get("match_method"),
            **ch,
        }

    seller_matches = matches_by_platform.get("sellers", [])
    row["channels"]["sellers"] = []
    for sm in seller_matches:
        ch = classify_channel(naar_price, float(sm.get("price", 0)) if sm.get("price") else None)
        title = sm.get("title") or product.get("name", "")
        seller_url = normalize_competitor_url("seller", title, sm.get("url") or sm.get("seller_website"))
        row["channels"]["sellers"].append(
            {
                "seller_name": sm.get("seller_name"),
                "seller_id": sm.get("seller_id"),
                "seller_website": sm.get("seller_website"),
                "seller_category": sm.get("seller_category"),
                "price": sm.get("price"),
                "url": seller_url,
                "is_search_link": sm.get("is_search_link") or "/search" in (seller_url or ""),
                "title": sm.get("title"),
                "match_confidence": sm.get("match_score"),
                **ch,
            }
        )

    best_seller = None
    if row["channels"]["sellers"]:
        priced = [s for s in row["channels"]["sellers"] if s.get("price")]
        if priced:
            best_seller = min(priced, key=lambda s: s["price"])

    row["summary"] = {
        "lowest_competitor": _lowest_competitor(row),
        "seller_count_matched": len([s for s in row["channels"]["sellers"] if s.get("price")]),
        "best_seller": best_seller,
        "has_discrepancy": _has_discrepancy(row),
    }
    return row


def _lowest_competitor(row: dict) -> dict | None:
    candidates = []
    for platform in ("amazon", "flipkart", "meesho"):
        ch = row["channels"].get(platform, {})
        if ch.get("price"):
            candidates.append({**ch, "source": platform})
    for s in row["channels"].get("sellers", []):
        if s.get("price"):
            candidates.append({**s, "source": "seller"})
    if not candidates:
        return None
    return min(candidates, key=lambda c: c["price"])


def _has_discrepancy(row: dict) -> bool:
    for platform in ("amazon", "flipkart", "meesho"):
        st = row["channels"].get(platform, {}).get("status")
        if st and st not in ("ok", "missing"):
            return True
    return any(s.get("status") not in ("ok", "missing") for s in row["channels"].get("sellers", []))
