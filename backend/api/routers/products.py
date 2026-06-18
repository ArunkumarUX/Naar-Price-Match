from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.database import Product

router = APIRouter()


class CatalogImport(BaseModel):
    products: list[dict]


@router.post("/import-catalog")
async def import_catalog(body: CatalogImport, db: AsyncSession = Depends(get_db)):
    """Import Naar shop catalog (e.g. from NAAR_CATALOG_API or manual export)."""
    from services.db import upsert_product

    imported = 0
    for item in body.products:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            price = float(str(item.get("price", item.get("base_price", 0))).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        sku = str(item.get("sku") or name[:40]).strip()
        url = str(item.get("url") or "https://naar.io/shop").strip()
        await upsert_product(
            db,
            {
                "sku": sku,
                "name": name,
                "variant": item.get("variant") or "default",
                "price": price,
                "url": url,
                "category": item.get("category"),
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
