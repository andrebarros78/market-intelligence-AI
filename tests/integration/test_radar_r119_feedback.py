import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.core.contracts import Alert, EntityRef, Evidence, EvidenceLevel, Severity
from market_intelligence.intelligence.radar.feedback import AlertOutcomeSubmission
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.feedback import PostgresFeedbackRepository
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_r119_feedback_is_durable_idempotent_ordered_and_calibration_safe() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def scenario() -> None:
        database = create_database_engine(url)
        sessions = create_session_factory(database)
        now = datetime.now(UTC)
        suffix = uuid4().hex
        entity_id = f"R119-{suffix}"
        detector_version = f"r119-test-detector@1.0.0-{suffix}"
        alert = Alert(
            entity=EntityRef(
                marketplace="mercadolivre",
                entity_type="item",
                entity_id=entity_id,
            ),
            observed_change="synthetic posterior feedback target",
            evidence=[
                Evidence(
                    level=EvidenceLevel.FACT,
                    statement="synthetic alert created for R1.19",
                    source="test:r119",
                    observed_at=now,
                )
            ],
            severity=Severity.HIGH,
            confidence=0.90,
            detector_version=detector_version,
        )
        alerts = PostgresAlertRepository(sessions)
        try:
            assert await alerts.save_if_new(alert) is True
            async with sessions() as session:
                alert_row = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()
                alert_id = alert_row.id

            untrusted = PostgresFeedbackRepository(
                sessions,
                trusted_for_calibration=False,
            )
            first_submission = AlertOutcomeSubmission(
                classification="false_positive",
                cause_classification="unidentified",
                decided_at=now,
                source="human",
                actor="reviewer-untrusted",
                reason_code="synthetic_review",
                evidence_refs=["evidence:r119:first"],
            )
            first = await untrusted.record(alert_id=alert_id, submission=first_submission)
            assert first["inserted"] is True
            assert first["calibration_eligible"] is False
            duplicate = await untrusted.record(alert_id=alert_id, submission=first_submission)
            assert duplicate["inserted"] is False
            assert duplicate["id"] == first["id"]
            assert (await untrusted.report(detector_version=detector_version)).total_latest_outcomes == 0

            trusted = PostgresFeedbackRepository(
                sessions,
                trusted_for_calibration=True,
            )
            trusted_replay = await trusted.record(
                alert_id=alert_id,
                submission=first_submission,
            )
            assert trusted_replay["inserted"] is False
            assert trusted_replay["id"] == first["id"]
            assert trusted_replay["calibration_eligible"] is False
            assert (await trusted.report(detector_version=detector_version)).total_latest_outcomes == 0

            confirmed = await trusted.record(
                alert_id=alert_id,
                submission=AlertOutcomeSubmission(
                    classification="confirmed",
                    cause_classification="external",
                    decided_at=now + timedelta(minutes=10),
                    source="human",
                    actor="reviewer-trusted",
                    reason_code="validated_external_cause",
                    evidence_refs=["evidence:r119:confirmed"],
                ),
            )
            assert confirmed["calibration_eligible"] is True
            assert confirmed["platform_internal_cause_confirmed"] is False

            older = await trusted.record(
                alert_id=alert_id,
                submission=AlertOutcomeSubmission(
                    classification="false_positive",
                    cause_classification="unidentified",
                    decided_at=now + timedelta(minutes=5),
                    source="verified_import",
                    actor="migration-r119",
                    reason_code="late_verified_import",
                    evidence_refs=["evidence:r119:older"],
                ),
            )
            assert older["calibration_eligible"] is True

            report = await trusted.report(detector_version=detector_version)
            assert report.total_latest_outcomes == 1
            assert report.decisive_outcomes == 1
            assert report.validated_positive_count == 1
            assert report.false_positive_count == 0
            assert report.false_positive_rate == 0.0
            assert report.validated_positive_rate == 1.0
            assert report.cause_counts["external"] == 1
            assert report.platform_internal_cause_confirmed is False

            observed = await trusted.record(
                alert_id=alert_id,
                submission=AlertOutcomeSubmission(
                    classification="persistent",
                    cause_classification="unidentified",
                    decided_at=now + timedelta(minutes=20),
                    source="system_observed",
                    reason_code="synthetic_persistence",
                    evidence_refs=["evidence:r119:system"],
                ),
            )
            assert observed["calibration_eligible"] is False

            restarted = PostgresFeedbackRepository(
                sessions,
                trusted_for_calibration=True,
            )
            history = await restarted.history(alert_id=alert_id)
            assert len(history) == 4
            assert [item["classification"] for item in history] == [
                "false_positive",
                "false_positive",
                "confirmed",
                "persistent",
            ]

            async with sessions() as session:
                persisted_alert = (
                    await session.execute(select(AlertRecord).where(AlertRecord.id == alert_id))
                ).scalar_one()
                assert persisted_alert.outcome == "persistent"

            report_after_restart = await restarted.report(detector_version=detector_version)
            assert report_after_restart.total_latest_outcomes == 1
            assert report_after_restart.classification_counts["confirmed"] == 1
            assert report_after_restart.classification_counts["false_positive"] == 0

            with pytest.raises(LookupError, match="alert_not_found"):
                await restarted.record(
                    alert_id=uuid4(),
                    submission=first_submission,
                )
        finally:
            await database.dispose()

    asyncio.run(scenario())
