from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from market_intelligence.ingestion.events import canonical_payload_hash
from market_intelligence.marketplaces.mercadolivre.http_client import MercadoLivreReadOnlyAdapter
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import ChannelEventRecord
from market_intelligence.workflows.names import WORKFLOW_INGESTION
from market_intelligence.workflows.temporal_engine import TemporalWorkflowEngine
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow
from market_intelligence.workflows.worker import build_temporal_worker

TOKEN = "synthetic-r14-temporal-token"


def _workflow_payload(*, suffix: str, resource: str) -> dict:
    now = datetime.now(UTC).replace(microsecond=0)
    raw_payload = {"topic": "items", "resource": resource}
    return {
        "marketplace": "mercadolivre",
        "raw_event": {
            "source": "mercadolivre",
            "event_type": "items",
            "external_id": f"r14-{suffix}",
            "resource": resource,
            "occurred_at": now.isoformat(),
            "received_at": now.isoformat(),
            "payload_hash": canonical_payload_hash(raw_payload),
            "payload": raw_payload,
        },
        "resource": resource,
        "entity_type": "item",
        "entity_id": resource.rsplit("/", 1)[-1],
    }


@pytest.mark.temporal
@pytest.mark.postgres
def test_r14_429_retries_then_persists_every_channel_attempt_without_secret() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        suffix = uuid4().hex
        resource = f"/items/MLB-R14-{suffix}"
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            if calls <= 2:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "1", "X-Request-Id": f"retry-{calls}"},
                    json={"error": "rate_limit"},
                )
            return httpx.Response(
                200,
                headers={"X-Request-Id": "success-3"},
                json={"id": resource.rsplit("/", 1)[-1], "status": "active"},
            )

        adapter = MercadoLivreReadOnlyAdapter(
            access_token=TOKEN,
            transport=httpx.MockTransport(handler),
        )
        try:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                queue = f"r14-retry-{suffix}"
                worker = build_temporal_worker(
                    env.client,
                    task_queue=queue,
                    sessions=sessions,
                    adapters={"mercadolivre": adapter},
                )
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=queue)
                    workflow_id = await engine.start(
                        WORKFLOW_INGESTION,
                        _workflow_payload(suffix=suffix, resource=resource),
                        idempotency_key=f"retry-{suffix}",
                    )
                    handle = env.client.get_workflow_handle(workflow_id, result_type=dict)
                    result = await handle.result()
                    assert result["resource_fetched"] is True
                    assert calls == 3
                    history = await handle.fetch_history()
                    raw_history = b"".join(event.SerializeToString() for event in history.events)
                    assert TOKEN.encode() not in raw_history
                    await Replayer(workflows=[MarketIntelligenceIngestionWorkflow]).replay_workflow(history)

            async with sessions() as session:
                rows = (
                    await session.execute(
                        select(ChannelEventRecord)
                        .where(ChannelEventRecord.operation == resource)
                        .order_by(ChannelEventRecord.attempt)
                    )
                ).scalars().all()
                assert [row.status_code for row in rows] == [429, 429, 200]
                assert [row.attempt for row in rows] == [1, 2, 3]
                assert rows[0].attributes["retry_after"] == "1"
                assert all("authorization" not in repr(row.attributes).lower() for row in rows)
                assert TOKEN not in repr(rows)
        finally:
            await adapter.aclose()
            await database.dispose()

    asyncio.run(scenario())


@pytest.mark.temporal
@pytest.mark.postgres
def test_r14_nonretryable_404_stops_after_first_attempt_and_records_channel_event() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        suffix = uuid4().hex
        resource = f"/items/MLB-R14-404-{suffix}"
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                404,
                headers={"X-Request-Id": "not-found-1"},
                json={"error": "not_found"},
            )

        adapter = MercadoLivreReadOnlyAdapter(
            access_token=TOKEN,
            transport=httpx.MockTransport(handler),
        )
        try:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                queue = f"r14-no-retry-{suffix}"
                worker = build_temporal_worker(
                    env.client,
                    task_queue=queue,
                    sessions=sessions,
                    adapters={"mercadolivre": adapter},
                )
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=queue)
                    workflow_id = await engine.start(
                        WORKFLOW_INGESTION,
                        _workflow_payload(suffix=suffix, resource=resource),
                        idempotency_key=f"no-retry-{suffix}",
                    )
                    handle = env.client.get_workflow_handle(workflow_id, result_type=dict)
                    with pytest.raises(WorkflowFailureError):
                        await handle.result()
                    assert calls == 1
                    history = await handle.fetch_history()
                    raw_history = b"".join(event.SerializeToString() for event in history.events)
                    assert TOKEN.encode() not in raw_history

            async with sessions() as session:
                rows = (
                    await session.execute(
                        select(ChannelEventRecord).where(
                            ChannelEventRecord.operation == resource
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1
                assert rows[0].status_code == 404
                assert rows[0].attempt == 1
        finally:
            await adapter.aclose()
            await database.dispose()

    asyncio.run(scenario())
