"""Celery task wiring (no broker required for `.run()`)."""


def test_ping_task_inline() -> None:
    from hospitai.workers.tasks import ping

    assert ping.run() == {"ok": True}


def test_probe_external_hospital_task_invalid_uuid() -> None:
    from hospitai.workers.tasks import probe_external_hospital_connectivity_task

    out = probe_external_hospital_connectivity_task.run("not-a-uuid")
    assert out.get("ok") is False
    assert out.get("error") == "invalid_tenant_id"


def test_tasks_registered() -> None:
    from hospitai.workers.celery_app import celery_app

    names = {t.name for t in celery_app.tasks.values() if t.name}
    assert "hospitai.workers.ping" in names
    assert "hospitai.workers.reindex_document_embeddings" in names
    assert "hospitai.workers.notify_domain_event" in names
    assert "hospitai.workers.probe_external_hospital_connectivity" in names
