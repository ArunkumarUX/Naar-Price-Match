from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models.database import (
    Platform,
    PriceAlert,
    PriceSnapshot,
    Product,
    ProductListing,
)

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.effective_database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    from models.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def upsert_product(session: AsyncSession, product: dict) -> Product:
    sku = product["sku"]
    product_id = sku
    existing = await session.get(Product, product_id)
    if existing:
        existing.name = product.get("name", existing.name)
        existing.variant = product.get("variant", existing.variant)
        existing.base_price = float(product.get("price", existing.base_price))
        existing.url = product.get("url", existing.url)
        existing.category = product.get("category", existing.category)
        existing.updated_at = datetime.utcnow()
        db_product = existing
    else:
        db_product = Product(
            id=product_id,
            sku=sku,
            name=product.get("name", ""),
            variant=product.get("variant"),
            category=product.get("category"),
            base_price=float(product.get("price", 0)),
            url=product.get("url", ""),
            meta=product.get("meta"),
        )
        session.add(db_product)
    await session.flush()
    return db_product


async def upsert_listing(session: AsyncSession, product_id: str, match: dict) -> ProductListing:
    platform = Platform(match.get("platform", "amazon"))
    seller_key = match.get("seller_id") or match.get("seller_name")

    stmt = select(ProductListing).where(
        ProductListing.product_id == product_id,
        ProductListing.platform == platform,
    )
    if platform == Platform.SELLER and seller_key:
        stmt = stmt.where(ProductListing.seller_name == seller_key)

    result = await session.execute(stmt)
    listing = result.scalar_one_or_none()
    if listing:
        listing.platform_id = match.get("platform_id")
        listing.platform_url = match.get("url", "")
        listing.match_confidence = float(match.get("match_score", 0))
        listing.match_method = match.get("match_method", "unknown")
        listing.seller_name = match.get("seller_name") or match.get("seller_id")
    else:
        listing = ProductListing(
            product_id=product_id,
            platform=platform,
            platform_id=match.get("platform_id"),
            seller_name=match.get("seller_name") or match.get("seller_id"),
            platform_url=match.get("url", ""),
            match_confidence=float(match.get("match_score", 0)),
            match_method=match.get("match_method", "unknown"),
        )
        session.add(listing)
    await session.flush()
    return listing


async def save_snapshot(session: AsyncSession, product_id: str, listing: ProductListing, price: float) -> None:
    session.add(
        PriceSnapshot(
            product_id=product_id,
            listing_id=listing.id,
            price=price,
            in_stock=True,
        )
    )


async def save_alert(session: AsyncSession, product_id: str, alert: dict, listing_id: int | None = None) -> PriceAlert:
    db_alert = PriceAlert(
        product_id=product_id,
        listing_id=listing_id,
        alert_type=alert["alert_type"],
        severity=alert["severity"],
        naar_price=alert.get("naar_price", 0),
        competitor_price=alert.get("competitor_price"),
        deviation_pct=alert.get("deviation_pct"),
        platform=alert.get("platform"),
        details=alert.get("details", ""),
    )
    session.add(db_alert)
    await session.flush()
    return db_alert


async def persist_scan_results(products: list[dict], alerts: list[dict], matches_by_sku: dict) -> None:
    await init_db()
    async with SessionLocal() as session:
        try:
            for product in products:
                db_product = await upsert_product(session, product)
                sku = product["sku"]
                for match in matches_by_sku.get(sku, []):
                    listing = await upsert_listing(session, db_product.id, match)
                    if match.get("price"):
                        await save_snapshot(session, db_product.id, listing, float(match["price"]))

            listing_map = {}
            for sku, match_list in matches_by_sku.items():
                if match_list:
                    listing_map[(sku, match_list[0].get("platform"))] = match_list[0]

            for alert in alerts:
                product_id = alert.get("product_sku") or next((p["sku"] for p in products), "unknown")
                listing_id = None
                await save_alert(session, product_id, alert, listing_id)
            await session.commit()
            logger.info("Persisted %s products and %s alerts", len(products), len(alerts))
        except Exception:
            await session.rollback()
            raise
