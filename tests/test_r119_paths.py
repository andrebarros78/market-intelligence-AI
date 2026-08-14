import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.core.contracts import Alert, EntityRef, Evidence, EvidenceLevel, Severity
from market_intelligence.intelligence.radar.feedback import AlertOutcomeSubmission
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.feedback import PostgresFeedbackRepository
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


def test_r119_unconfigured_feedback_route_is_fail_closed() -> None:
    async def scenario() -> None:
        app = create_app(Settings())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            capabilities = (await client.get("/v1/system/capabilities")).json()
            assert capabilities["radar"]["posterior_feedback"] is True
            assert capabilities["radar"]["posterior_feedback_persistence_configured"] is False
            assert capabilities["radar"]["posterior_feedback_request_can_promote"] is False
            assert capabilities["radar"]["posterior_feedback_http_calibration_trusted"] is False
            response = await client.post(
                f"/v1/internal/radar/alerts/{uuid4()}/outcomes",
                json={
                    "classification": "confirmed",
                    "decided_at": datetime.now(UTC).isoformat(),
                    "source": "human",
                    "actor": "reviewer",
                },
            )
            assert response.status_code == 503

    asyncio.run(scenario())


@pytest.mark.postgres
def test_r119_http_never_promotes_and_trusted_repository_path_can_qualify() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def scenario() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        now = datetime.now(UTC)
        entity_id = f"R119-HTTP-{uuid4().hex}"
        detector_version = "r119-http-detector@1.0.0"
        try:
            alert = Alert(
                entity=EntityRef(
                    marketplace="mercadolivre",
                    entity_type="item",
                    entity_id=entity_id,
                ),
                observed_change="synthetic R1.19 HTTP target",
                evidence=[
                    Evidence(
                        level=EvidenceLevel.FACT,
                        statement="synthetic HTTP feedback alert",
                        source="test:r119:http",
                        observed_at=now,
                    )
                ],
                severity=Severity.MEDIUM,
                confidence=0.80,
                detector_version=detector_version,
            )
            assert await PostgresAlertRepository(sessions).save_if_new(alert) is True
            async with sessions() as session:
                alert_id = (
                    await session.execute(
                        select(AlertRecord.id).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()

            app = create_app(Settings(), feedback_sessions=sessions)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                capabilities = (await client.get("/v1/system/capabilities")).json()
                assert capabilities["radar"]["posterior_feedback_http_calibration_trusted"] is False
                assert capabilities["radar"]["posterior_feedback_trusted_repository_path"] is True
                assert capabilities["radar"]["posterior_feedback_auto_calibration"] is False

                attempted_promotion = await client.post(
                    f"/v1/internal/radar/alerts/{alert_id}/outcomes",
                    json={
                        "classification": "false_positive",
                        "cause_classification": "unidentified",
                        "decided_at": now.isoformat(),
                        "source": "human",
                        "actor": "request-reviewer",
                        "calibration_eligible": True,
                    },
                )
                assert attempted_promotion.status_code == 422

                untrusted = await client.post(
                    f"/v1/internal/radar/alerts/{alert_id}/outcomes",
                    json={
                        "classification": "false_positive",
                        "cause_classification": "unidentified",
                        "decided_at": now.isoformat(),
                        "source": "human",
                        "actor": "request-reviewer",
                        "reason_code": "initial_review",
                        "evidence_refs": ["evidence:r119:http:1"],
                    },
                )
                assert untrusted.status_code == 200
                assert untrusted.json()["calibration_eligible"] is False
                assert untrusted.json()["trusted_runtime"] is False
                assert untrusted.json()["calibration_write_path"] == "untrusted_http"

                empty_report = await client.get(
                    "/v1/internal/radar/feedback/report",
                    params={"detector_version": detector_version},
                )
                assert empty_report.status_code == 200
                assert empty_report.json()["total_latest_outcomes"] == 0

            trusted_repository = PostgresFeedbackRepository(
                sessions,
                trusted_for_calibration=True,
            )
            trusted = await trusted_repository.record(
                alert_id=alert_id,
                submission=AlertOutcomeSubmission(
                    classification="confirmed",
                    cause_classification="external",
                    decided_at=now + timedelta(minutes=10),
                    source="human",
                    actor="trusted-internal-reviewer",
                    reason_code="validated_followup",
                    evidence_refs=["evidence:r119:trusted:2"],
                ),
            )
            assert trusted["calibration_eligible"] is True
            assert trusted["platform_internal_cause_confirmed"] is False

            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                history = await client.get(
                    f"/v1/internal/radar/alerts/{alert_id}/outcomes"
                )
                assert history.status_code == 200
                assert history.json()["append_only"] is True
                assert len(history.json()["outcomes"]) == 2

                report = await client.get(
                    "/v1/internal/radar/feedback/report",
                    params={"detector_version": detector_version},
                )
                assert report.status_code == 200
                body = report.json()
                assert body["total_latest_outcomes"] == 1
                assert body["validated_positive_count"] == 1
                assert body["false_positive_count"] == 0
                assert body["false_positive_rate"] == 0.0
                assert body["platform_internal_cause_confirmed"] is False
        finally:
            await database.dispose()

    asyncio.run(scenario())
