from celery import Celery
from celery.schedules import crontab

from digest.config import settings

celery_app = Celery("digest", broker=settings.celery_broker_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "poll-rss-feeds": {
        "task": "digest.tasks.ingest.poll_all_rss_feeds",
        "schedule": crontab(minute="*/15"),
    },
}

celery_app.autodiscover_tasks(["digest.tasks"])
