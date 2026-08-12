from __future__ import annotations

import asyncio

from temporalio.common import WorkflowIDReusePolicy

from market_intelligence.workflows.temporal_engine import (
    TemporalWorkflowEngine,
    deterministic_workflow_id,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def start_workflow(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return object()


def test_deterministic_workflow_id_is_stable_and_scoped() -> None:
    first = deterministic_workflow_id("workflow-a", "event-123")
    second = deterministic_workflow_id("workflow-a", "event-123")
    other = deterministic_workflow_id("workflow-b", "event-123")
    assert first == second
    assert first != other
    assert first.startswith("mi-")


def test_temporal_engine_uses_reject_duplicate_policy() -> None:
    async def scenario() -> None:
        client = FakeClient()
        engine = TemporalWorkflowEngine(client, task_queue="mi-test")  # type: ignore[arg-type]
        workflow_id = await engine.start(
            "market-intelligence-ingestion",
            {"raw_event": {"source": "mercadolivre"}},
            idempotency_key="event-123",
        )
        assert workflow_id == deterministic_workflow_id(
            "market-intelligence-ingestion",
            "event-123",
        )
        _, kwargs = client.calls[0]
        assert kwargs["id"] == workflow_id
        assert kwargs["task_queue"] == "mi-test"
        assert kwargs["id_reuse_policy"] is WorkflowIDReusePolicy.REJECT_DUPLICATE

    asyncio.run(scenario())
