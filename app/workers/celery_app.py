from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "meeting_intelligence",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    result_expires=31_536_000,
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
