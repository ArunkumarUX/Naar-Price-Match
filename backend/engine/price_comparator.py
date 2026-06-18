from dataclasses import dataclass, field

from models.database import AlertType, Severity


@dataclass
class PriceRule:
    name: str = "default"
    lower_threshold_pct: float = 5.0
    upper_threshold_pct: float = 50.0
    severity_map: dict = field(
        default_factory=lambda: {
            Severity.LOW: 2.0,
            Severity.MEDIUM: 5.0,
            Severity.HIGH: 10.0,
            Severity.CRITICAL: 20.0,
        }
    )


DEFAULT_RULE = PriceRule()


class PriceComparator:
    def __init__(self, rule: PriceRule = DEFAULT_RULE):
        self.rule = rule

    def compare(
        self,
        naar_price: float,
        competitor_price: float,
        platform: str,
        listing: dict,
    ) -> dict | None:
        if naar_price <= 0 or competitor_price <= 0:
            return None

        deviation_pct = ((naar_price - competitor_price) / naar_price) * 100

        if deviation_pct >= self.rule.lower_threshold_pct:
            alert_type = AlertType.LOWER_PRICE
        elif deviation_pct <= -self.rule.upper_threshold_pct:
            alert_type = AlertType.HIGHER_PRICE
        else:
            return None

        return {
            "alert_type": alert_type,
            "severity": self._severity(abs(deviation_pct)),
            "naar_price": naar_price,
            "competitor_price": competitor_price,
            "deviation_pct": round(deviation_pct, 2),
            "platform": platform,
            "listing": listing,
            "details": (
                f"{platform.title()} ₹{competitor_price:.2f} vs "
                f"Naar ₹{naar_price:.2f} ({deviation_pct:+.1f}%)"
            ),
        }

    def flag_missing(self, product: dict, platform: str) -> dict:
        return {
            "alert_type": AlertType.PRODUCT_MISSING,
            "severity": Severity.MEDIUM,
            "naar_price": product.get("price", product.get("base_price", 0)),
            "competitor_price": None,
            "deviation_pct": None,
            "platform": platform,
            "listing": None,
            "details": f"SKU '{product.get('sku')}' not found on {platform}",
        }

    def flag_low_confidence(self, product: dict, platform: str, best_match: dict) -> dict:
        return {
            "alert_type": AlertType.LOW_CONFIDENCE,
            "severity": Severity.LOW,
            "naar_price": product.get("price", product.get("base_price", 0)),
            "competitor_price": best_match.get("price"),
            "deviation_pct": None,
            "platform": platform,
            "listing": best_match,
            "details": (
                f"Low confidence match on {platform} "
                f"({best_match.get('match_score', 0):.2f}) for SKU '{product.get('sku')}'"
            ),
        }

    def _severity(self, abs_pct: float) -> Severity:
        m = self.rule.severity_map
        if abs_pct >= m[Severity.CRITICAL]:
            return Severity.CRITICAL
        if abs_pct >= m[Severity.HIGH]:
            return Severity.HIGH
        if abs_pct >= m[Severity.MEDIUM]:
            return Severity.MEDIUM
        return Severity.LOW
