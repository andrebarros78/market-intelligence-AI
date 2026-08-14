import asyncio
import os
from datetime import UTC, datetime
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
def test_r116_iad_evidence_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        entity_id = f"R116-{uuid4().hex}"
        observed_at = datetime.now(UTC)
        controls = [
            {
                "entity_id": name,
                "metrics": {"visits": current},
                "history": {"visits": HISTORY},
            }
            for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
        ]
        profile = {
            "version": "historical-fixture-v1",
            "source_type": "historical_validation",
            "weights": {
                "traffic_deviation": 0.5,
                "control_divergence": 0.5,
            },
            "threshold": 0.70,
            "min_components": 2,
            "production_approved": True,
            "sample_count": 20,
            "positive_count": 10,
            "negative_count": 10,
            "metrics": {"balanced_accuracy": 0.90},
        }
        observation = RadarObservation(
            entity_id=entity_id,
            observed_at=observed_at,
            metrics={"visits": 75},
            history={"visits": HISTORY},
            context={"control_candidates": controls},
        )
        finding = build_default_radar(iad_profile=profile).evaluate(observation)
        iad = next(
            result for result in finding.detector_results
            if result.detector == "distribution_anomaly_index_v1"
        )
        assert iad.attributes["iad_decision"] is True
        assert iad.attributes["calibration_trust"] == "trusted_runtime"
        alert = alert_from_finding(
            finding=finding,
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=observed_at,
            context={},
        )
        assert alert is not None
        repository = PostgresAlertRepository(sessions)
        try:
            assert await repository.save_if_new(alert) is True
            assert await repository.save_if_new(alert) is False
            async with sessions() as session:
                alert_row = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()
                evidence = (
                    await session.execute(
                        select(EvidenceRecord).where(
                            EvidenceRecord.entity_id == entity_id,
                            EvidenceRecord.source == "radar:distribution_anomaly_index_v1",
                        )
                    )
                ).scalar_one()
            assert "distribution-anomaly-index@1.0.0" in (alert_row.detector_version or "")
            assert evidence.level == "inference"
            assert evidence.attributes["calibration_version"] == "historical-fixture-v1"
            assert evidence.attributes["calibration_trust"] == "trusted_runtime"
            assert evidence.attributes["production_approved"] is True
            assert evidence.attributes["iad_decision"] is True
            assert evidence.attributes["causal_claim"] is False
            assert evidence.attributes["internal_platform_cause_confirmed"] is False
        finally:
            await database.dispose()

    asyncio.run(run())
