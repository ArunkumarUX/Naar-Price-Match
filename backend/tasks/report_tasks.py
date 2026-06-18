import asyncio
import logging

from sqlalchemy import desc, func, select

from models.database import PriceAlert, PriceSnapshot, Product
from services.db import SessionLocal
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.report_tasks.generate_weekly_report")
def generate_weekly_report():
    return asyncio.run(_generate_weekly_report())


async def _generate_weekly_report() -> dict:
    async with SessionLocal() as session:
        alert_counts = await session.execute(
            select(PriceAlert.severity, func.count())
            .where(PriceAlert.is_resolved.is_(False))
            .group_by(PriceAlert.severity)
        )
        product_count = await session.execute(select(func.count()).select_from(Product))
        snapshot_count = await session.execute(select(func.count()).select_from(PriceSnapshot))

        recent = await session.execute(
            select(PriceAlert).where(PriceAlert.is_resolved.is_(False)).order_by(desc(PriceAlert.created_at)).limit(100)
        )

        report = {
            "open_alerts_by_severity": {str(row[0].value): row[1] for row in alert_counts.all()},
            "product_count": product_count.scalar() or 0,
            "snapshot_count": snapshot_count.scalar() or 0,
            "recent_alerts": len(recent.scalars().all()),
        }
        logger.info("Weekly report generated: %s", report)
        return report
