"""Celery task wiring (no broker required for `.run()`)."""


def test_ping_task_inline() -> None:
    from hospitai.workers.tasks import ping

    assert ping.run() == {"ok": True}


def test_tasks_registered() -> None:
    from hospitai.workers.celery_app import celery_app

    names = {t.name for t in celery_app.tasks.values() if t.name}
    assert "hospitai.workers.ping" in names
    assert "hospitai.workers.reindex_document_embeddings" in names
    assert "hospitai.workers.notify_domain_event" in names
