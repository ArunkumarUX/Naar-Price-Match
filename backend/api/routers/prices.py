from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.database import PriceSnapshot, Product

router = APIRouter()


@router.get("/snapshots")
async def list_snapshots(
    product_id: str | None = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    q = select(PriceSnapshot).order_by(desc(PriceSnapshot.captured_at)).limit(limit)
    if product_id:
        q = q.where(PriceSnapshot.product_id == product_id)
    result = await db.execute(q)
    snapshots = result.scalars().all()
    return [
        {
            "id": s.id,
            "product_id": s.product_id,
            "listing_id": s.listing_id,
            "price": s.price,
            "in_stock": s.in_stock,
            "captured_at": s.captured_at.isoformat(),
        }
        for s in snapshots
    ]


@router.get("/trend/{product_id}")
async def price_trend(product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(PriceSnapshot.captured_at)
        .limit(52)
    )
    snapshots = result.scalars().all()
    product = await db.get(Product, product_id)
    return {
        "product_id": product_id,
        "name": product.name if product else None,
        "points": [{"price": s.price, "captured_at": s.captured_at.isoformat()} for s in snapshots],
    }
