import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.orm import selectinload

from api.deps import get_db
from engine.comparison_builder import build_comparison_row
from matcher.embedding_matcher import ProductMatcher
from scraper.amazon_scraper import AmazonScraper
from scraper.flipkart_scraper import FlipkartScraper
from scraper.meesho_scraper import MeeshoScraper
from scraper.naar_scraper import NaarScraper
from scraper.seller_registry import load_sellers, seller_count
from scraper.seller_scraper import SellerScraper
from config import settings
from models.database import PriceSnapshot, Product, ProductListing

logger = logging.getLogger(__name__)
router = APIRouter()

matcher = ProductMatcher(settings.EMBEDDING_MODEL)


@router.get("/sellers")
async def list_sellers():
    return {"count": seller_count(), "sellers": load_sellers()}


@router.get("/matrix")
async def comparison_matrix(
    limit: int = Query(50, le=200),
    live: bool = Query(False, description="Run live scrape (slow). Default: cached DB from last scan."),
    db: AsyncSession = Depends(get_db),
):
    """Naar vs Amazon, Flipkart, Meesho, and all matched seller websites."""
    result = await db.execute(
        select(Product)
        .where(Product.is_active.is_(True))
        .options(
            selectinload(Product.listings).selectinload(ProductListing.snapshots),
        )
        .limit(limit)
    )
    products = result.scalars().all()

    if products:
        rows = [_product_from_db(p) for p in products]
    elif live:
        rows = await _live_comparison(limit)
    else:
        rows = []

    return {
        "seller_registry_count": seller_count(),
        "platforms": ["naar", "amazon", "flipkart", "meesho", "seller"],
        "products": rows,
        "source": "database" if products else ("live" if live else "empty"),
    }


@router.get("/product/{sku}")
async def compare_product(sku: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.sku == sku).options(selectinload(Product.listings))
    )
    product = result.scalar_one_or_none()
    if product:
        return _product_from_db(product)

    rows = await _live_comparison(1, sku_filter=sku)
    if not rows:
        return {"error": "Product not found"}
    return rows[0]


async def _live_comparison(limit: int, sku_filter: str | None = None) -> list[dict]:
    naar = NaarScraper()
    amazon = AmazonScraper(proxy=settings.BRIGHTDATA_PROXY or None)
    flipkart = FlipkartScraper()
    meesho = MeeshoScraper()
    seller = SellerScraper(max_sellers_per_scan=10)

    rows: list[dict] = []
    async for product in naar.get_all_products():
        if sku_filter and product.get("sku") != sku_filter:
            continue

        matches: dict = {}
        for platform, scraper in [("amazon", amazon), ("flipkart", flipkart), ("meesho", meesho)]:
            candidates = await scraper.search_product(product["name"], max_results=3)
            matched = await matcher.match_async(product, candidates, min_confidence=settings.MIN_MATCH_CONFIDENCE)
            matches[platform] = matched[0] if matched else None

        seller_candidates = await seller.search_product(product["name"], max_results=8)
        seller_matched = await matcher.match_async(
            product, seller_candidates, min_confidence=settings.MIN_MATCH_CONFIDENCE - 0.1
        )
        matches["sellers"] = seller_matched[:5]

        rows.append(build_comparison_row(product, matches))
        if len(rows) >= limit:
            break
        await asyncio.sleep(0.2)

    return rows


def _product_from_db(product: Product) -> dict:
    naar_price = product.base_price
    matches: dict = {"amazon": None, "flipkart": None, "meesho": None, "sellers": []}

    for listing in product.listings:
        entry = {
            "price": None,
            "url": listing.platform_url,
            "match_score": listing.match_confidence,
            "match_method": listing.match_method,
            "seller_name": listing.seller_name,
            "seller_id": listing.platform_id,
            "seller_website": listing.platform_url,
        }
        snapshots = sorted(listing.snapshots, key=lambda s: s.captured_at, reverse=True) if listing.snapshots else []
        if snapshots:
            entry["price"] = snapshots[0].price

        plat = listing.platform.value
        if plat == "seller":
            matches["sellers"].append(entry)
        elif plat in matches:
            matches[plat] = entry

    product_dict = {
        "sku": product.sku,
        "name": product.name,
        "variant": product.variant,
        "price": naar_price,
        "url": product.url,
    }
    return build_comparison_row(product_dict, matches)
