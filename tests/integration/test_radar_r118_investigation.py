import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from temporalio.testing import WorkflowEnvironment

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.ingestion.events import canonical_payload_hash
from market_intelligence.intelligence.radar.models import DetectorResult, RadarFinding, RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.investigations import PostgresInvestigationRepository
from market_intelligence.persistence.models import InvestigationCaseRecord, InvestigationEventRecord
from market_intelligence.workflows.investigation_activities import InvestigationActivities
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow
from market_intelligence.workflows.worker import build_temporal_worker


def _observation(entity_id: str, observed_at: datetime) -> RadarObservation:
    return RadarObservation(
        entity_id=entity_id,
        observed_at=observed_at,
        metrics={"visits": 40.0},
        history={"visits": [100.0] * 12},
        context={"hypotheses": ["Mudança de distribuição merece investigação"]},
    )


def _finding(entity_id: str, *, anomalous: bool, score: float) -> RadarFinding:
    results = []
    if anomalous:
        results = [
            DetectorResult(
                detector="distribution_anomaly_index_v1",
                score=score,
                level=EvidenceLevel.HYPOTHESIS,
                summary="Distribution anomaly requires investigation",
                attributes={
                    "detector_version": "distribution-anomaly-index@1.0.0",
                    "causal_claim": False,
                },
            )
        ]
    return RadarFinding(
        entity_id=entity_id,
        score=score,
        anomalous=anomalous,
        detector_results=results,
    )


def _workflow_payload(entity_id: str, observed_at: datetime, external_id: str) -> dict:
    raw_payload = {"entity_id": entity_id, "kind": "r118-temporal-proof"}
    return {
        "marketplace": "mercadolivre",
        "entity_type": "item",
        "raw_event": {
            "source": "mercadolivre",
            "event_type": "r118_temporal_proof",
            "external_id": external_id,
            "received_at": observed_at.isoformat(),
            "payload_hash": canonical_payload_hash(raw_payload),
            "payload": raw_payload,
        },
        "radar_observation": {
            "entity_id": entity_id,
            "observed_at": observed_at.isoformat(),
            "metrics": {"visits": 10.0},
            "history": {
                "visits": [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 101.0, 99.0]
            },
            "context": {"hypotheses": ["Distribuição merece investigação"]},
        },
    }


@pytest.mark.postgres
def test_r118_investigation_is_durable_idempotent_restart_and_order_safe() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        entity_id = f"R118-{uuid4().hex}"
        started = datetime.now(UTC)
        first_observation = _observation(entity_id, started)
        first_finding = _finding(entity_id, anomalous=True, score=0.82)
        repository = PostgresInvestigationRepository(sessions)
        try:
            first = await repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=first_finding,
                observation=first_observation,
            )
            assert first is not None
            assert first["status"] == "open"
            assert first["event_inserted"] is True
            assert first["event_ignored"] is False
            assert first["observation_count"] == 1
            assert first["causal_claim"] is False

            duplicate = await repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=first_finding,
                observation=first_observation,
            )
            assert duplicate is not None
            assert duplicate["case_id"] == first["case_id"]
            assert duplicate["event_id"] == first["event_id"]
            assert duplicate["event_inserted"] is False
            assert duplicate["observation_count"] == 1

            restarted_repository = PostgresInvestigationRepository(sessions)
            second_observation = _observation(entity_id, started + timedelta(minutes=10))
            second = await restarted_repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=_finding(entity_id, anomalous=True, score=0.88),
                observation=second_observation,
            )
            assert second is not None
            assert second["case_id"] == first["case_id"]
            assert second["status"] == "confirmed"
            assert second["ever_confirmed"] is True
            assert second["observation_count"] == 2
            assert second["hypotheses"]
            assert any(item["status"] == "supported" for item in second["hypotheses"])

            out_of_order_observation = _observation(entity_id, started + timedelta(minutes=5))
            ignored = await restarted_repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=_finding(entity_id, anomalous=False, score=0.10),
                observation=out_of_order_observation,
            )
            assert ignored is not None
            assert ignored["case_id"] == first["case_id"]
            assert ignored["status"] == "confirmed"
            assert ignored["observation_count"] == 2
            assert ignored["event_inserted"] is True
            assert ignored["event_ignored"] is True
            assert ignored["ignored_reason"] == "out_of_order_observation"
            assert ignored["last_observed_at"] == second_observation.observed_at.isoformat()

            ignored_retry = await restarted_repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=_finding(entity_id, anomalous=False, score=0.10),
                observation=out_of_order_observation,
            )
            assert ignored_retry is not None
            assert ignored_retry["event_inserted"] is False
            assert ignored_retry["event_ignored"] is True
            assert ignored_retry["observation_count"] == 2

            activity = InvestigationActivities(sessions)
            third_observation = _observation(entity_id, started + timedelta(minutes=20))
            third = await activity.advance(
                {
                    "marketplace": "mercadolivre",
                    "entity_type": "item",
                    "observation": third_observation.model_dump(mode="json"),
                    "finding": _finding(
                        entity_id,
                        anomalous=False,
                        score=0.20,
                    ).model_dump(mode="json"),
                }
            )
            assert third is not None and third["status"] == "monitoring"

            fourth_observation = _observation(entity_id, started + timedelta(minutes=30))
            fourth = await activity.advance(
                {
                    "marketplace": "mercadolivre",
                    "entity_type": "item",
                    "observation": fourth_observation.model_dump(mode="json"),
                    "finding": _finding(
                        entity_id,
                        anomalous=False,
                        score=0.18,
                    ).model_dump(mode="json"),
                }
            )
            assert fourth is not None
            assert fourth["status"] == "resolved"
            assert fourth["active"] is False
            assert fourth["observation_count"] == 4

            async with sessions() as session:
                case_count = (
                    await session.execute(
                        select(func.count(InvestigationCaseRecord.id)).where(
                            InvestigationCaseRecord.entity_id == entity_id
                        )
                    )
                ).scalar_one()
                event_count = (
                    await session.execute(
                        select(func.count(InvestigationEventRecord.id))
                        .join(
                            InvestigationCaseRecord,
                            InvestigationEventRecord.case_id == InvestigationCaseRecord.id,
                        )
                        .where(InvestigationCaseRecord.entity_id == entity_id)
                    )
                ).scalar_one()
            assert case_count == 1
            assert event_count == 5

            stale_after_close = await restarted_repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=_finding(entity_id, anomalous=True, score=0.90),
                observation=_observation(entity_id, started + timedelta(minutes=25)),
            )
            assert stale_after_close is not None
            assert stale_after_close["case_id"] == first["case_id"]
            assert stale_after_close["event_ignored"] is True
            assert stale_after_close["active"] is False

            later_observation = _observation(entity_id, started + timedelta(hours=2))
            later = await restarted_repository.advance(
                marketplace="mercadolivre",
                entity_type="item",
                finding=_finding(entity_id, anomalous=True, score=0.84),
                observation=later_observation,
            )
            assert later is not None
            assert later["status"] == "open"
            assert later["case_id"] != first["case_id"]
        finally:
            await database.dispose()

    asyncio.run(run())


@pytest.mark.postgres
def test_r118_full_temporal_workflow_advances_the_same_durable_case() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        entity_id = f"R118-TEMPORAL-{uuid4().hex}"
        queue = f"r118-{uuid4().hex}"
        started = datetime.now(UTC)
        env = await WorkflowEnvironment.start_time_skipping()
        worker = build_temporal_worker(
            env.client,
            task_queue=queue,
            sessions=sessions,
            adapters={},
        )
        try:
            async with worker:
                first = await env.client.execute_workflow(
                    MarketIntelligenceIngestionWorkflow.run,
                    _workflow_payload(entity_id, started, f"evt-{uuid4().hex}"),
                    id=f"r118-first-{uuid4().hex}",
                    task_queue=queue,
                )
                assert first["radar_evaluated"] is True
                assert first["radar_finding"]["anomalous"] is True
                assert first["investigation"] is not None
                assert first["investigation"]["status"] == "open"
                assert first["investigation"]["event_inserted"] is True

                second = await env.client.execute_workflow(
                    MarketIntelligenceIngestionWorkflow.run,
                    _workflow_payload(
                        entity_id,
                        started + timedelta(minutes=10),
                        f"evt-{uuid4().hex}",
                    ),
                    id=f"r118-second-{uuid4().hex}",
                    task_queue=queue,
                )
                assert second["investigation"] is not None
                assert second["investigation"]["case_id"] == first["investigation"]["case_id"]
                assert second["investigation"]["status"] == "confirmed"
                assert second["investigation"]["observation_count"] == 2

            async with sessions() as session:
                case_count = await session.scalar(
                    select(func.count(InvestigationCaseRecord.id)).where(
                        InvestigationCaseRecord.entity_id == entity_id
                    )
                )
                event_count = await session.scalar(
                    select(func.count(InvestigationEventRecord.id))
                    .join(
                        InvestigationCaseRecord,
                        InvestigationEventRecord.case_id == InvestigationCaseRecord.id,
                    )
                    .where(InvestigationCaseRecord.entity_id == entity_id)
                )
            assert case_count == 1
            assert event_count == 2
        finally:
            await env.shutdown()
            await database.dispose()

    asyncio.run(run())
