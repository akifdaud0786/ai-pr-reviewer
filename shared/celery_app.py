"""
Single Celery application shared by:
  - webhook_service  (producer: pushes review jobs onto the Redis queue)
  - orchestrator_service (consumer: the Celery worker that runs the LangGraph review)

Keeping one Celery() instance definition avoids task-name mismatches between
producer and consumer.
"""
from celery import Celery

from shared.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_pr_reviewer",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["orchestrator_service.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="pr_review_queue",
)
