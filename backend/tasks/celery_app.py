from celery import Celery
from celery.schedules import crontab

from config import settings

celery_app = Celery("naar_monitor", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "weekly-full-check": {
            "task": "tasks.crawl_tasks.run_full_price_check",
            "schedule": crontab(hour=6, minute=0, day_of_week=1),
        },
        "daily-critical-refresh": {
            "task": "tasks.crawl_tasks.refresh_critical_alerts",
            "schedule": crontab(hour="*/4", minute=15),
        },
    },
)

celery_app.autodiscover_tasks(["tasks"])
