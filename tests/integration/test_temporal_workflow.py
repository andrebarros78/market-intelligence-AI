from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.workflows.names import WORKFLOW_INGESTION
from market_intelligence.workflows.temporal_engine import TemporalWorkflowEngine
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow
from market_intelligence.workflows.worker import build_temporal_worker


class FlakyReadOnlyAdapter:
    name = "mercadolivre"

    def __init__(self) -> None:
        self.attempts = 0

    async def fetch_resource(self, resource: str) -> dict[str, Any]:
        self.attempts += 1
        if self.attempts < 3:
            raise RuntimeError("synthetic transient read failure")
        return {
            "id": resource.rsplit("/", 1)[-1],
            "status": "active",
            "price": 100.0,
        }

    def normalize_notification(self, payload: dict[str, Any]) -> Any:
        raise NotImplementedError


@pytest.mark.temporal
@pytest.mark.postgres
def test_temporal_postgres_pipeline_is_durable_idempotent_and_retries_reads() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        adapter = FlakyReadOnlyAdapter()
        suffix = uuid4().hex
        now = datetime.now(UTC)
        entity_id = f"MLB-{suffix}"
        event = build_raw_event(
            source="mercadolivre",
            event_type="items",
            external_id=f"notification-{suffix}",
            resource=f"/items/{entity_id}",
            received_at=now,
            payload={"resource": f"/items/{entity_id}"},
        )
        payload = {
            "marketplace": "mercadolivre",
            "raw_event": event.model_dump(mode="json"),
            "resource": f"/items/{entity_id}",
            "entity_type": "listing",
            "entity_id": entity_id,
            "radar_observation": {
                "entity_id": entity_id,
                "observed_at": now.isoformat(),
                "metrics": {"sales": 1.0},
                "history": {"sales": [10.0, 10.0, 10.0, 10.0, 10.0]},
                "context": {},
            },
        }

        try:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                task_queue = f"mi-base03-{suffix}"
                worker = build_temporal_worker(
                    env.client,
                    task_queue=task_queue,
                    sessions=sessions,
                    adapters={"mercadolivre": adapter},
                    radar=RadarService([KnownRuleDetector(), RobustZScoreDetector()]),
                )
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=task_queue)
                    first_id = await engine.start(
                        WORKFLOW_INGESTION,
                        payload,
                        idempotency_key=f"notification-{suffix}",
                    )
                    second_id = await engine.start(
                        WORKFLOW_INGESTION,
                        payload,
                        idempotency_key=f"notification-{suffix}",
                    )
                    assert first_id == second_id

                    handle = env.client.get_workflow_handle(
                        first_id,
                        result_type=dict[str, Any],
                    )
                    result = await handle.result()
                    assert result["raw_event_inserted"] is True
                    assert result["resource_fetched"] is True
                    assert result["snapshot_changed"] is True
                    assert result["radar_evaluated"] is True
                    assert result["radar_finding"]["entity_id"] == entity_id
                    assert adapter.attempts == 3

                    history = await handle.fetch_history()
                    assert history.events
                    await Replayer(
                        workflows=[MarketIntelligenceIngestionWorkflow]
                    ).replay_workflow(history)
        finally:
            await database.dispose()

    asyncio.run(scenario())
