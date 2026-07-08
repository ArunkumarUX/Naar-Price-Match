from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.database import Product

router = APIRouter()


class CatalogImport(BaseModel):
    products: list[dict]


def _as_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _extract_price(item: dict) -> float | None:
    # Supported formats:
    # - {"price": 123}
    # - {"base_price": 123}
    # - Naar payload: {"variants": [{"price": 123}, ...]}
    direct = _as_float(item.get("price", item.get("base_price")))
    if direct and direct > 0:
        return direct

    variants = item.get("variants") or []
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            p = _as_float(variant.get("price"))
            if p and p > 0:
                return p
    return None


@router.post("/import-catalog")
async def import_catalog(body: CatalogImport, db: AsyncSession = Depends(get_db)):
    """Import Naar shop catalog (e.g. from NAAR_CATALOG_API or manual export)."""
    from services.db import upsert_product

    imported = 0
    for item in body.products:
        # Accept both normalized payload and raw Naar payload.
        name = str(item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        price = _extract_price(item)
        if not price or price <= 0:
            continue

        status = str(item.get("status", "active")).lower()
        if status and status != "active":
            continue

        sku = str(item.get("sku") or item.get("_id") or name[:40]).strip()
        url = str(item.get("url") or "https://naar.io/shop").strip()
        await upsert_product(
            db,
            {
                "sku": sku,
                "name": name,
                "variant": item.get("variant")
                or (item.get("variants", [{}])[0].get("variantName") if item.get("variants") else None)
                or "default",
                "price": price,
                "url": url,
                "category": (
                    item.get("category")
                    if isinstance(item.get("category"), str)
                    else (item.get("category") or {}).get("title")
                ),
            },
        )
        imported += 1
    await db.commit()
    return {"imported": imported, "total": len(body.products)}


@router.get("/")
async def list_products(
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.is_active.is_(True)).limit(limit).offset(offset))
    products = result.scalars().all()
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "variant": p.variant,
            "base_price": p.base_price,
            "category": p.category,
            "url": p.url,
        }
        for p in products
    ]


@router.get("/{product_id}")
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        return {"error": "not found"}
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "variant": product.variant,
        "base_price": product.base_price,
        "category": product.category,
        "url": product.url,
        "listings": [
            {
                "platform": l.platform.value,
                "platform_id": l.platform_id,
                "match_confidence": l.match_confidence,
                "match_method": l.match_method,
                "url": l.platform_url,
            }
            for l in product.listings
        ],
    }
