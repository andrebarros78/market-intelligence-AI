from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from market_intelligence.ingestion.events import RawEvent, canonical_payload_hash
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import (
    AlertRecord,
    ChannelEventRecord,
    EvidenceRecord,
    RawEventRecord,
    SnapshotRecord,
)
from market_intelligence.workflows.names import WORKFLOW_INGESTION
from market_intelligence.workflows.temporal_engine import TemporalWorkflowEngine
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow
from market_intelligence.workflows.worker import build_temporal_worker


class SyntheticMarketplaceAdapter:
    name = "mercadolivre"

    def __init__(self) -> None:
        self.fetch_calls = 0

    async def fetch_resource(self, resource: str) -> dict:
        self.fetch_calls += 1
        if self.fetch_calls <= 2:
            raise RuntimeError("synthetic transient read failure")
        return {
            "id": "MLB-R13-ITEM",
            "status": "active",
            "available_quantity": 0,
            "price": 199.90,
        }

    def normalize_notification(self, payload: dict) -> RawEvent:
        raise NotImplementedError


@pytest.mark.temporal
@pytest.mark.postgres
def test_r13_vertical_is_durable_idempotent_and_persists_alert_evidence() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        suffix = uuid4().hex
        adapter = SyntheticMarketplaceAdapter()
        observed = datetime.now(UTC).replace(microsecond=0)
        external_id = f"r13-event-{suffix}"
        entity_id = f"MLB-R13-{suffix}"
        raw_payload = {"topic": "items", "resource": f"/items/{entity_id}"}
        raw_event = {
            "source": "mercadolivre",
            "event_type": "items",
            "external_id": external_id,
            "resource": f"/items/{entity_id}",
            "occurred_at": observed.isoformat(),
            "received_at": observed.isoformat(),
            "payload_hash": canonical_payload_hash(raw_payload),
            "payload": raw_payload,
        }
        channel_event = {
            "marketplace": "mercadolivre",
            "direction": "inbound",
            "operation": "synthetic-notification",
            "observed_at": observed.isoformat(),
            "status_code": 200,
            "latency_ms": 12.5,
            "attempt": 1,
            "correlation_id": f"corr-{suffix}",
            "request_id": f"req-{suffix}",
            "attributes": {
                "topic": "items",
                "authorization": "synthetic-value-must-be-redacted",
            },
        }
        radar_observation = {
            "entity_id": entity_id,
            "observed_at": observed.isoformat(),
            "metrics": {"available_quantity": 0.0},
            "history": {},
            "context": {
                "known_rule_violation": True,
                "known_rule_summary": "Item sem estoque disponível",
                "estimated_impact": 199.90,
                "recommended_action": "Revisar reposição do item",
                "responsible": "operacao",
            },
        }
        payload = {
            "marketplace": "mercadolivre",
            "raw_event": raw_event,
            "channel_event": channel_event,
            "resource": f"/items/{entity_id}",
            "entity_type": "item",
            "entity_id": entity_id,
            "radar_observation": radar_observation,
        }

        try:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                queue = f"r13-{suffix}"
                worker = build_temporal_worker(
                    env.client,
                    task_queue=queue,
                    sessions=sessions,
                    adapters={"mercadolivre": adapter},
                )
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=queue)
                    first_id = await engine.start(
                        WORKFLOW_INGESTION, payload, idempotency_key=f"r13-first-{suffix}"
                    )
                    first = env.client.get_workflow_handle(first_id, result_type=dict)
                    result = await first.result()
                    assert result["channel_event_inserted"] is True
                    assert result["raw_event_inserted"] is True
                    assert result["resource_fetched"] is True
                    assert result["snapshot_changed"] is True
                    assert result["radar_evaluated"] is True
                    assert result["radar_finding"]["anomalous"] is True
                    assert result["alert_created"] is True
                    assert adapter.fetch_calls == 3

                    history = await first.fetch_history()
                    await Replayer(workflows=[MarketIntelligenceIngestionWorkflow]).replay_workflow(history)

                    second_id = await engine.start(
                        WORKFLOW_INGESTION, payload, idempotency_key=f"r13-second-{suffix}"
                    )
                    second = env.client.get_workflow_handle(second_id, result_type=dict)
                    duplicate = await second.result()
                    assert duplicate["channel_event_inserted"] is False
                    assert duplicate["raw_event_inserted"] is False
                    assert duplicate["snapshot_changed"] is False
                    assert duplicate["alert_created"] is False

            async with sessions() as session:
                raw_count = await session.scalar(
                    select(func.count()).select_from(RawEventRecord).where(
                        RawEventRecord.external_id == external_id
                    )
                )
                channel_rows = (
                    await session.execute(
                        select(ChannelEventRecord).where(
                            ChannelEventRecord.correlation_id == f"corr-{suffix}"
                        )
                    )
                ).scalars().all()
                snapshot_count = await session.scalar(
                    select(func.count()).select_from(SnapshotRecord).where(
                        SnapshotRecord.entity_id == entity_id
                    )
                )
                alerts = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalars().all()
                evidence_count = await session.scalar(
                    select(func.count()).select_from(EvidenceRecord).where(
                        EvidenceRecord.entity_id == entity_id
                    )
                )

                assert raw_count == 1
                assert len(channel_rows) == 1
                assert channel_rows[0].attributes["authorization"] == "[REDACTED]"
                assert snapshot_count == 1
                assert len(alerts) == 1
                assert alerts[0].severity == "critical"
                assert alerts[0].dedupe_key is not None
                assert evidence_count == 1
        finally:
            await database.dispose()

    asyncio.run(scenario())
