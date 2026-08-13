from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_r113_attribution_persists_and_deduplicates() -> None:
    url = Settings.from_env().database_url
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        now = datetime.now(UTC)
        entity_id = f"R113-{uuid4().hex}"
        observation = RadarObservation(
            entity_id=entity_id,
            observed_at=now,
            metrics={"visits": 85},
            history={"visits": [100, 110, 105, 115, 110, 120, 115, 125]},
            context={
                "factor_attribution": {
                    "metric": "visits",
                    "expected": 125,
                    "factors": [{
                        "name": "competition",
                        "current": 55,
                        "history": [50, 55, 52.5, 57.5, 55, 60, 57.5, 62.5],
                        "source": "market",
                    }],
                }
            },
        )
        alert = alert_from_finding(
            finding=build_default_radar().evaluate(observation),
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=now,
            context={},
        )
        assert alert is not None
        repo = PostgresAlertRepository(sessions)
        try:
            assert await repo.save_if_new(alert) is True
            assert await repo.save_if_new(alert) is False
            async with sessions() as session:
                row = (await session.execute(
                    select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                )).scalar_one()
            assert row.observable_causes == ["competition"]
            assert row.unexplained_residual == -25.0
            assert "factor-attribution@1.0.0" in (row.detector_version or "")
            assert "unexplained-residual@2.0.0" in (row.detector_version or "")
        finally:
            await db.dispose()

    asyncio.run(run())
