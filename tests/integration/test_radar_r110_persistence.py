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
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_residual_alert_is_persisted() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        entity_id = f"R110-{uuid4().hex}"
        now = datetime.now(UTC).replace(microsecond=0)
        observation = RadarObservation(
            entity_id=entity_id,
            observed_at=now,
            metrics={"visits": 60.0},
            history={"visits": [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]},
            context={"residual_analysis": {
                "metric": "visits",
                "expected": 100.0,
                "observable_effects": [
                    {"name": "seasonality", "contribution": -2.0},
                    {"name": "competition", "contribution": -3.0},
                ],
            }},
        )
        finding = build_default_radar().evaluate(observation)
        alert = alert_from_finding(
            finding=finding,
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
                assert row.unexplained_residual == -35.0
                assert row.observable_causes == ["seasonality", "competition"]
        finally:
            await db.dispose()

    asyncio.run(run())
