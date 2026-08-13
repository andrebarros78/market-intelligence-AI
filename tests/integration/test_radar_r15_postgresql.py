from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.core.contracts import (
    Alert,
    EntityRef,
    Evidence,
    EvidenceLevel,
    Severity,
)
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord, EvidenceRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_r15_full_evidence_contract_round_trips_and_deduplicates() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        suffix = uuid4().hex
        first = datetime.now(UTC).replace(microsecond=0)
        last = first + timedelta(minutes=15)
        entity_id = f"MLB-R15-{suffix}"
        alert = Alert(
            entity=EntityRef(
                marketplace="mercadolivre",
                entity_type="item",
                entity_id=entity_id,
            ),
            observed_change="queda anormal de distribuição sem explicação suficiente",
            evidence=[
                Evidence(
                    level=EvidenceLevel.FACT,
                    statement="visitas caíram 68%",
                    source="metric:visits",
                    observed_at=first,
                    attributes={"delta": -0.68},
                ),
                Evidence(
                    level=EvidenceLevel.INFERENCE,
                    statement="fatores observáveis explicam apenas parte do desvio",
                    source="radar:residual",
                    observed_at=last,
                    attributes={"explained": -0.07},
                ),
            ],
            hypotheses=["mudança de distribuição merece investigação"],
            severity=Severity.CRITICAL,
            estimated_impact=8450.0,
            confidence=0.93,
            observable_causes=["sazonalidade", "competição observável"],
            unexplained_residual=-0.61,
            control_comparison={"investigated_delta": -0.68, "control_delta": -0.05},
            recommended_action="priorizar investigação humana",
            responsible="operacao",
            first_observed_at=first,
            last_observed_at=last,
            detector_version="radar-evidence-v2-test",
        )
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
                evidence = (
                    await session.execute(
                        select(EvidenceRecord)
                        .where(EvidenceRecord.alert_id == row.id)
                        .order_by(EvidenceRecord.observed_at)
                    )
                ).scalars().all()
                assert row.evidence_classification == "hypothesis"
                assert row.observable_causes == ["sazonalidade", "competição observável"]
                assert row.unexplained_residual == -0.61
                assert row.hypotheses == ["mudança de distribuição merece investigação"]
                assert row.control_comparison == {
                    "investigated_delta": -0.68,
                    "control_delta": -0.05,
                }
                assert row.first_observed_at == first
                assert row.last_observed_at == last
                assert row.detector_version == "radar-evidence-v2-test"
                assert len(evidence) == 2
                assert [item.level for item in evidence] == ["fact", "inference"]
        finally:
            await database.dispose()

    asyncio.run(scenario())
