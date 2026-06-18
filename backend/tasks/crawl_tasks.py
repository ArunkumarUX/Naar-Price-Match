import asyncio
import logging

from config import settings
from engine.exception_detector import should_notify_immediately
from engine.price_comparator import PriceComparator
from engine.rule_engine import get_active_rule
from matcher.embedding_matcher import ProductMatcher
from notifications.email_sender import send_alert_email
from notifications.slack_notifier import send_slack_alert
from scraper.amazon_scraper import AmazonScraper
from scraper.flipkart_scraper import FlipkartScraper
from scraper.meesho_scraper import MeeshoScraper
from scraper.naar_scraper import NaarScraper
from scraper.seller_scraper import SellerScraper
from services.db import persist_scan_results
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

matcher = ProductMatcher(settings.EMBEDDING_MODEL)
comparator = PriceComparator(get_active_rule())

MARKETPLACE_SCRAPERS = {
    "amazon": AmazonScraper(proxy=settings.BRIGHTDATA_PROXY or None),
    "flipkart": FlipkartScraper(),
    "meesho": MeeshoScraper(),
}
SELLER_SCRAPER = SellerScraper(max_sellers_per_scan=12)


@celery_app.task(name="tasks.crawl_tasks.run_full_price_check", bind=True, max_retries=2)
def run_full_price_check(self):
    try:
        asyncio.run(_full_check())
    except Exception as exc:
        logger.exception("Full price check failed")
        raise self.retry(exc=exc, countdown=300) from exc


@celery_app.task(name="tasks.crawl_tasks.refresh_critical_alerts")
def refresh_critical_alerts():
    logger.info("Refreshing critical alerts (stub — re-run full check in production)")
    return {"status": "ok"}


async def _full_check():
    naar = NaarScraper()
    all_alerts: list[dict] = []
    all_products: list[dict] = []
    matches_by_sku: dict[str, list[dict]] = {}
    catalog_error: str | None = None

    async for product in naar.get_all_products():
        all_products.append(product)

    if not all_products:
        catalog_error = (
            "Naar catalog empty — naar.io/shop could not be scraped. "
            "Try POST /reports/sync-catalog or set NAAR_CATALOG_API / SCRAPERAPI_KEY in backend/.env"
        )
        logger.error(catalog_error)
        return {"alerts": 0, "products": 0, "catalog_error": catalog_error}

    for product in all_products:
        sku = product["sku"]
        matches_by_sku[sku] = []

        for platform, scraper in MARKETPLACE_SCRAPERS.items():
            candidates = await scraper.search_product(product["name"], max_results=5)
            matches = await matcher.match_async(product, candidates, min_confidence=settings.MIN_MATCH_CONFIDENCE)

            if not matches:
                alert = comparator.flag_missing(product, platform)
                alert["product_sku"] = sku
                all_alerts.append(alert)
                continue

            best = matches[0]
            best["platform"] = platform
            matches_by_sku[sku].append(best)

            if best.get("match_score", 0) < settings.MIN_MATCH_CONFIDENCE + 0.05:
                alert = comparator.flag_low_confidence(product, platform, best)
                alert["product_sku"] = sku
                all_alerts.append(alert)

            alert = comparator.compare(
                naar_price=float(product["price"]),
                competitor_price=float(best["price"]),
                platform=platform,
                listing=best,
            )
            if alert:
                alert["product_sku"] = sku
                all_alerts.append(alert)

        seller_candidates = await SELLER_SCRAPER.search_product(product["name"], max_results=10)
        seller_matches = await matcher.match_async(
            product, seller_candidates, min_confidence=max(0.65, settings.MIN_MATCH_CONFIDENCE - 0.1)
        )

        if not seller_matches:
            alert = comparator.flag_missing(product, "seller")
            alert["product_sku"] = sku
            all_alerts.append(alert)
        else:
            for best in seller_matches[:5]:
                best["platform"] = "seller"
                matches_by_sku[sku].append(best)
                alert = comparator.compare(
                    naar_price=float(product["price"]),
                    competitor_price=float(best["price"]),
                    platform=f"seller:{best.get('seller_name', 'unknown')}",
                    listing=best,
                )
                if alert:
                    alert["product_sku"] = sku
                    all_alerts.append(alert)

        await asyncio.sleep(0.3)

    try:
        await persist_scan_results(all_products, all_alerts, matches_by_sku)
    except Exception as exc:
        logger.warning("DB persist failed (is Postgres running?): %s", exc)

    critical = [
        a for a in all_alerts
        if should_notify_immediately(a) and getattr(a.get("severity"), "value", a.get("severity")) == "critical"
    ]
    high = [
        a for a in all_alerts
        if should_notify_immediately(a) and getattr(a.get("severity"), "value", a.get("severity")) == "high"
    ]

    if critical:
        await send_slack_alert(critical)
    if critical or high:
        await send_alert_email(critical + high)

    logger.info("Price check complete — %s alerts generated", len(all_alerts))
    return {"alerts": len(all_alerts), "products": len(all_products), "catalog_error": catalog_error}
