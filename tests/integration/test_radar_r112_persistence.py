import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord, EvidenceRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository

HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


@pytest.mark.postgres
def test_automatic_control_comparison_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        observed_at = datetime.now(UTC)
        entity_id = f"R112-{uuid4().hex}"
        candidates = [
            {
                "entity_id": name,
                "metrics": {"visits": current},
                "history": {"visits": HISTORY},
            }
            for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
        ]
        finding = build_default_radar().evaluate(
            RadarObservation(
                entity_id=entity_id,
                observed_at=observed_at,
                metrics={"visits": 75},
                history={"visits": HISTORY},
                context={"control_candidates": candidates},
            )
        )
        alert = alert_from_finding(
            finding=finding,
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=observed_at,
            context={},
        )
        assert alert is not None
        repo = PostgresAlertRepository(sessions)
        try:
            assert await repo.save_if_new(alert) is True
            assert await repo.save_if_new(alert) is False
            async with sessions() as session:
                row = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()
                counterfactual_evidence = (
                    await session.execute(
                        select(EvidenceRecord).where(
                            EvidenceRecord.entity_id == entity_id,
                            EvidenceRecord.source == "radar:operational_counterfactual_v1",
                        )
                    )
                ).scalar_one()
            assert "relational-control@2.0.0" in (row.detector_version or "")
            assert "operational-counterfactual@1.0.0" in (row.detector_version or "")
            assert row.control_comparison is not None
            assert row.control_comparison["selection"]["mode"] == "automatic"
            assert row.control_comparison["selection"]["selection_uses_current_values"] is False
            assert counterfactual_evidence.level == "inference"
            assert counterfactual_evidence.attributes["counterfactual_kind"] == "operational_not_causal"
            assert counterfactual_evidence.attributes["causal_claim"] is False
            assert counterfactual_evidence.attributes["fit_uses_current_target"] is False
        finally:
            await db.dispose()

    asyncio.run(run())


@pytest.mark.postgres
def test_channel_regime_correlation_evidence_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        observed_at = datetime.now(UTC)
        entity_id = f"R115-{uuid4().hex}"
        start = observed_at - timedelta(minutes=11)
        events = []
        for index in range(12):
            recent = index >= 8
            events.append(
                {
                    "marketplace": "mercadolivre",
                    "direction": "inbound",
                    "operation": f"/items/{entity_id}",
                    "observed_at": start + timedelta(minutes=index),
                    "status_code": 503 if recent else 200,
                    "latency_ms": 450.0 if recent else 90.0,
                    "attempt": 2 if recent else 1,
                    "attributes": (
                        {"partial_content": True, "opaque_marker": "must_not_propagate"}
                        if recent
                        else {}
                    ),
                }
            )
        finding = build_default_radar().evaluate(
            RadarObservation(
                entity_id=entity_id,
                observed_at=observed_at,
                metrics={"visits": 55},
                history={"visits": HISTORY},
                context={"channel_events": events},
            )
        )
        channel_result = next(
            item for item in finding.detector_results
            if item.detector == "channel_regime_correlation_v1"
        )
        assert channel_result.level.value == "inference"
        alert = alert_from_finding(
            finding=finding,
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=observed_at,
            context={},
        )
        assert alert is not None
        repo = PostgresAlertRepository(sessions)
        try:
            assert await repo.save_if_new(alert) is True
            assert await repo.save_if_new(alert) is False
            async with sessions() as session:
                row = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()
                channel_evidence = (
                    await session.execute(
                        select(EvidenceRecord).where(
                            EvidenceRecord.entity_id == entity_id,
                            EvidenceRecord.source == "radar:channel_regime_correlation_v1",
                        )
                    )
                ).scalar_one()
            assert "channel-regime-correlation@1.0.0" in (row.detector_version or "")
            assert channel_evidence.level == "inference"
            assert channel_evidence.attributes["correlation_status"] == "joint_regime_detected"
            assert channel_evidence.attributes["causal_claim"] is False
            assert channel_evidence.attributes["internal_platform_cause_confirmed"] is False
            assert "opaque_marker" not in str(channel_evidence.attributes)
        finally:
            await db.dispose()

    asyncio.run(run())
