import base64
import io
import logging

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


async def send_alert_email(alerts: list[dict]) -> None:
    if not alerts or not settings.SENDGRID_API_KEY:
        logger.info("Skipping email — no alerts or SENDGRID_API_KEY not set (%s alerts)", len(alerts))
        return

    try:
        import sendgrid
        from sendgrid.helpers.mail import (
            Attachment,
            Disposition,
            FileContent,
            FileName,
            FileType,
            Mail,
        )
    except ImportError:
        logger.warning("sendgrid not installed")
        return

    df = pd.DataFrame(
        [
            {
                "SKU": (a.get("listing") or {}).get("platform_id", ""),
                "Platform": a.get("platform", ""),
                "Naar Price (₹)": a.get("naar_price"),
                "Competitor Price (₹)": a.get("competitor_price"),
                "Deviation %": a.get("deviation_pct"),
                "Severity": getattr(a.get("severity"), "value", a.get("severity")),
                "Details": a.get("details"),
            }
            for a in alerts
        ]
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_b64 = base64.b64encode(buf.getvalue().encode()).decode()
    html_table = df.to_html(index=False, border=0)
    critical_count = sum(
        1
        for a in alerts
        if getattr(a.get("severity"), "value", a.get("severity")) == "critical"
    )

    message = Mail(
        from_email=settings.ALERT_EMAIL_FROM,
        to_emails=settings.ALERT_EMAIL_TO,
        subject=f"Naar Price Alert — {len(alerts)} issues ({critical_count} critical)",
        html_content=f"""
        <html><body>
        <h2 style="color:#dc2626">Price Monitoring Alert — {len(alerts)} Issues Found</h2>
        <p>{critical_count} critical, {len(alerts) - critical_count} other severity</p>
        {html_table}
        <p style="margin-top:24px;color:#6b7280">
        Open the <a href="{settings.DASHBOARD_URL}">pricing dashboard</a>.
        </p>
        </body></html>
        """,
    )
    message.attachment = Attachment(
        FileContent(csv_b64),
        FileName("price_alerts.csv"),
        FileType("text/csv"),
        Disposition("attachment"),
    )

    sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
    sg.send(message)
    logger.info("Alert email sent to %s", settings.ALERT_EMAIL_TO)
