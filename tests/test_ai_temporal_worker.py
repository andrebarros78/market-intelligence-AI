from types import SimpleNamespace

from market_intelligence.workflows import ai_worker


def test_ai_temporal_worker_enforces_server_and_worker_rate_limits(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeWorker:
        def __init__(self, client, **kwargs):
            captured["client"] = client
            captured.update(kwargs)

    monkeypatch.setattr(ai_worker, "Worker", FakeWorker)
    client = SimpleNamespace()
    audit_repo = SimpleNamespace()

    worker = ai_worker.build_ai_temporal_worker(
        client,
        role="agents",
        audit_repo=audit_repo,
    )

    assert isinstance(worker, FakeWorker)
    assert captured["client"] is client
    assert captured["task_queue"] == "market-intelligence-ai-agents-v1"
    assert captured["max_concurrent_activities"] == 1
    assert captured["max_activities_per_second"] == 1.0
    assert captured["max_task_queue_activities_per_second"] == 1.0
    assert captured["disable_eager_activity_execution"] is True
    assert len(captured["workflows"]) == 2
    assert len(captured["activities"]) == 2


def test_system_and_agents_use_different_task_queues(monkeypatch) -> None:
    queues: list[str] = []

    class FakeWorker:
        def __init__(self, client, **kwargs):
            queues.append(kwargs["task_queue"])

    monkeypatch.setattr(ai_worker, "Worker", FakeWorker)
    client = SimpleNamespace()

    ai_worker.build_ai_temporal_worker(client, role="system")
    ai_worker.build_ai_temporal_worker(client, role="agents")

    assert queues == [
        "market-intelligence-ai-system-v1",
        "market-intelligence-ai-agents-v1",
    ]
