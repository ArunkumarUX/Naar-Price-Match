import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from scraper.naar_scraper import NaarScraper
from services.db import persist_scan_results, upsert_product
from tasks.crawl_tasks import _full_check
from tasks.report_tasks import _generate_weekly_report

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync-catalog")
async def sync_catalog(db: AsyncSession = Depends(get_db)):
    """Fetch Naar shop catalog and save to database."""
    naar = NaarScraper()
    products: list[dict] = []
    try:
        async with asyncio.timeout(90):
            async for product in naar.get_all_products():
                products.append(product)
    except TimeoutError:
        return {
            "status": "failed",
            "imported": 0,
            "message": "Catalog fetch timed out after 90s. Set NAAR_CATALOG_API or SCRAPERAPI_KEY in backend/.env",
        }

    if not products:
        return {
            "status": "failed",
            "imported": 0,
            "message": (
                "Could not fetch products from naar.io/shop. "
                "Set NAAR_CATALOG_API in backend/.env, add SCRAPERAPI_KEY for rendered fetch, "
                "or POST /products/import-catalog with your catalog JSON."
            ),
        }

    for product in products:
        await upsert_product(db, product)
    await db.commit()
    return {"status": "ok", "imported": len(products), "source": products[0].get("source", "naar")}


@router.post("/run-scan")
async def trigger_scan():
    result = await _full_check()
    return {"status": "completed", **result}


@router.get("/weekly")
async def weekly_report(db: AsyncSession = Depends(get_db)):
    return await _generate_weekly_report()


@router.get("/export/csv")
async def export_report_csv():
    from api.routers.alerts import export_csv
    from services.db import SessionLocal

    async with SessionLocal() as session:
        return await export_csv(session)
