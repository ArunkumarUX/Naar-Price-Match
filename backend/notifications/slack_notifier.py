import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}


async def send_slack_alert(alerts: list[dict]) -> None:
    if not settings.SLACK_WEBHOOK_URL or not alerts:
        logger.info("Skipping Slack — webhook not configured")
        return

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🚨 {len(alerts)} Critical Price Alert(s)"},
        },
        {"type": "divider"},
    ]

    for alert in alerts[:8]:
        sev = getattr(alert.get("severity"), "value", alert.get("severity", "low"))
        emoji = SEVERITY_EMOJI.get(sev, "⚪")
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Platform*\n`{str(alert.get('platform', '')).title()}`"},
                    {"type": "mrkdwn", "text": f"*Severity*\n{emoji} `{str(sev).upper()}`"},
                    {"type": "mrkdwn", "text": f"*Naar Price*\n₹{alert.get('naar_price', 0):.2f}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Competitor*\n₹{alert.get('competitor_price', 0):.2f} ({alert.get('deviation_pct', 0):+.1f}%)",
                    },
                ],
            }
        )

    if len(alerts) > 8:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"_...and {len(alerts) - 8} more. Open the dashboard._"},
            }
        )

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open Dashboard"},
                    "url": f"{settings.DASHBOARD_URL}/alerts",
                    "style": "danger",
                }
            ],
        }
    )

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(settings.SLACK_WEBHOOK_URL, json={"blocks": blocks})
    logger.info("Slack alert sent (%s items)", len(alerts))
