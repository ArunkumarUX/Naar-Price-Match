from config import settings
from engine.price_comparator import PriceRule, Severity


def get_active_rule() -> PriceRule:
    return PriceRule(
        lower_threshold_pct=settings.MAX_PRICE_DEVIATION_PCT,
        severity_map={
            Severity.LOW: 2.0,
            Severity.MEDIUM: settings.MAX_PRICE_DEVIATION_PCT,
            Severity.HIGH: 10.0,
            Severity.CRITICAL: settings.CRITICAL_DEVIATION_PCT,
        },
    )
