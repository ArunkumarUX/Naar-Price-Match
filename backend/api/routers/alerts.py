import io
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.database import PriceAlert, Severity

router = APIRouter()


@router.get("/")
async def list_alerts(
    severity: Severity | None = None,
    resolved: bool = False,
    platform: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(PriceAlert).where(PriceAlert.is_resolved == resolved)
    if severity:
        q = q.where(PriceAlert.severity == severity)
    if platform:
        q = q.where(PriceAlert.platform == platform)
    q = q.order_by(desc(PriceAlert.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "product_id": a.product_id,
            "alert_type": a.alert_type.value,
            "severity": a.severity.value,
            "naar_price": a.naar_price,
            "competitor_price": a.competitor_price,
            "deviation_pct": a.deviation_pct,
            "platform": a.platform,
            "details": a.details,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


@router.get("/summary")
async def alert_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PriceAlert.severity, func.count())
        .where(PriceAlert.is_resolved.is_(False))
        .group_by(PriceAlert.severity)
    )
    return {row[0].value: row[1] for row in result.all()}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(PriceAlert, alert_id)
    if alert:
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        await db.flush()
    return {"status": "ok"}


@router.get("/export/csv")
async def export_csv(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PriceAlert).where(PriceAlert.is_resolved.is_(False)))
    alerts = result.scalars().all()
    df = pd.DataFrame(
        [
            {
                "product_id": a.product_id,
                "alert_type": a.alert_type.value,
                "severity": a.severity.value,
                "platform": a.platform,
                "naar_price": a.naar_price,
                "competitor_price": a.competitor_price,
                "deviation_pct": a.deviation_pct,
                "details": a.details,
                "created_at": a.created_at,
            }
            for a in alerts
        ]
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alerts.csv"},
    )
