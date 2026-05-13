"""Celery application instance (broker from Settings)."""

from __future__ import annotations

from celery import Celery

from hospitai.infrastructure.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    backend = settings.celery_result_backend or settings.celery_broker_url
    app = Celery(
        "hospitai",
        broker=settings.celery_broker_url,
        backend=backend,
        include=["hospitai.workers.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_default_queue="hospitai",
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery_app()
