from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sellers.json"


@lru_cache(maxsize=1)
def load_sellers(active_only: bool = True) -> list[dict]:
    if not DATA_PATH.exists():
        logger.warning("Seller registry not found at %s", DATA_PATH)
        return []
    sellers = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if active_only:
        sellers = [s for s in sellers if s.get("active", True)]
    return sellers


def get_seller_urls(category: str | None = None) -> list[str]:
    sellers = load_sellers()
    if category:
        sellers = [s for s in sellers if s.get("category", "").lower() == category.lower()]
    return [s["website"] for s in sellers if s.get("website")]


def get_seller_by_url(url: str) -> dict | None:
    url = url.rstrip("/").lower()
    for seller in load_sellers():
        if seller.get("website", "").rstrip("/").lower() == url:
            return seller
    return None


def seller_count() -> int:
    return len(load_sellers())
