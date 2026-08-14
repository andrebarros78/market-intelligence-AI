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


VISITS_HISTORY = [
    100, 101, 99, 100, 102, 98, 101, 99, 100, 100, 101, 99,
    100, 102, 98, 101, 99, 100, 101, 100, 99, 102, 98, 100,
]
CONVERSION_HISTORY = [
    0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101, 0.099,
    0.100, 0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101,
    0.099, 0.100, 0.101, 0.100, 0.099, 0.102, 0.098, 0.100,
]


def _trusted_profile() -> dict:
    return {
        "version": "historical-runtime-fixture-v1",
        "source_type": "historical_validation",
        "detector_weights": {"ecod": 0.5, "iforest": 0.5},
        "threshold": 0.80,
        "feature_names": ["visits", "conversion"],
        "min_history": 12,
        "production_approved": True,
        "sample_count": 20,
        "positive_count": 10,
        "negative_count": 10,
        "metrics": {
            "balanced_accuracy": 0.90,
            "sensitivity": 0.90,
            "specificity": 0.90,
        },
        "detector_metrics": {
            "ecod": {"balanced_accuracy": 0.90},
            "iforest": {"balanced_accuracy": 0.90},
        },
    }


@pytest.mark.postgres
def test_r117_pyod_evidence_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        entity_id = f"R117-{uuid4().hex}"
        observed_at = datetime.now(UTC)
        observation = RadarObservation(
            entity_id=entity_id,
            observed_at=observed_at,
            metrics={"visits": 180, "conversion": 0.35},
            history={
                "visits": VISITS_HISTORY,
                "conversion": CONVERSION_HISTORY,
            },
            context={},
        )
        finding = build_default_radar(pyod_profile=_trusted_profile()).evaluate(observation)
        result = next(
            item for item in finding.detector_results if item.detector == "pyod_ensemble_v1"
        )
        assert result.attributes["ensemble_decision"] is True
        assert result.attributes["trust_boundary"] == "trusted_runtime"
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
                            EvidenceRecord.source == "radar:pyod_ensemble_v1",
                        )
                    )
                ).scalar_one()
            assert "pyod-ensemble@1.0.0" in (alert_row.detector_version or "")
            assert evidence.level == "inference"
            assert evidence.attributes["profile_version"] == "historical-runtime-fixture-v1"
            assert evidence.attributes["trust_boundary"] == "trusted_runtime"
            assert evidence.attributes["production_approved"] is True
            assert evidence.attributes["ensemble_decision"] is True
            assert evidence.attributes["alert_eligible"] is True
            assert evidence.attributes["pyod_library_version"] == "3.6.2"
            assert evidence.attributes["causal_claim"] is False
        finally:
            await database.dispose()

    asyncio.run(run())
