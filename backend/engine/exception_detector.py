from models.database import Severity


def detect_exceptions(alerts: list[dict]) -> dict[str, list[dict]]:
    grouped = {"critical": [], "high": [], "medium": [], "low": []}
    for alert in alerts:
        sev = alert.get("severity")
        key = sev.value if hasattr(sev, "value") else str(sev)
        if key in grouped:
            grouped[key].append(alert)
    return grouped


def should_notify_immediately(alert: dict) -> bool:
    sev = alert.get("severity")
    value = sev.value if hasattr(sev, "value") else str(sev)
    return value in {Severity.CRITICAL.value, Severity.HIGH.value}
