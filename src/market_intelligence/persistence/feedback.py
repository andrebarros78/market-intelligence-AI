from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.feedback import (
    AlertOutcomeSubmission,
    CauseClassification,
    DetectorFeedbackReport,
    OutcomeClassification,
    OutcomeSource,
)
from market_intelligence.persistence.feedback_models import AlertOutcomeRecord
from market_intelligence.persistence.models import AlertRecord


def outcome_dedupe_key(alert_id: UUID, submission: AlertOutcomeSubmission) -> str:
    payload = submission.model_dump(mode="json")
    encoded = json.dumps(
        {"alert_id": str(alert_id), "submission": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialize(record: AlertOutcomeRecord, *, inserted: bool) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "alert_id": str(record.alert_id),
        "inserted": inserted,
        "classification": record.classification,
        "cause_classification": record.cause_classification,
        "source": record.source,
        "actor": record.actor,
        "reason_code": record.reason_code,
        "evidence_refs": record.evidence_refs or [],
        "detector_version_snapshot": record.detector_version_snapshot,
        "calibration_eligible": record.calibration_eligible,
        "decided_at": record.decided_at.isoformat(),
        "causal_claim": False,
        "platform_internal_cause_confirmed": False,
    }


class PostgresFeedbackRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        trusted_for_calibration: bool = False,
    ) -> None:
        self._sessions = sessions
        self._trusted_for_calibration = bool(trusted_for_calibration)

    @property
    def trusted_for_calibration(self) -> bool:
        return self._trusted_for_calibration

    async def record(
        self,
        *,
        alert_id: UUID,
        submission: AlertOutcomeSubmission,
    ) -> dict[str, Any]:
        dedupe_key = outcome_dedupe_key(alert_id, submission)
        async with self._sessions() as session, session.begin():
            alert = (
                await session.execute(
                    select(AlertRecord).where(AlertRecord.id == alert_id).with_for_update()
                )
            ).scalar_one_or_none()
            if alert is None:
                raise LookupError("alert_not_found")

            duplicate = (
                await session.execute(
                    select(AlertOutcomeRecord).where(AlertOutcomeRecord.dedupe_key == dedupe_key)
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                return _serialize(duplicate, inserted=False)

            latest = (
                await session.execute(
                    select(AlertOutcomeRecord)
                    .where(AlertOutcomeRecord.alert_id == alert_id)
                    .order_by(AlertOutcomeRecord.decided_at.desc(), AlertOutcomeRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            calibration_eligible = bool(
                self._trusted_for_calibration
                and submission.source in {OutcomeSource.HUMAN, OutcomeSource.VERIFIED_IMPORT}
            )
            statement = (
                pg_insert(AlertOutcomeRecord)
                .values(
                    alert_id=alert_id,
                    dedupe_key=dedupe_key,
                    classification=submission.classification.value,
                    cause_classification=(
                        submission.cause_classification.value
                        if submission.cause_classification is not None
                        else None
                    ),
                    source=submission.source.value,
                    actor=(submission.actor or "").strip() or None,
                    reason_code=(submission.reason_code or "").strip() or None,
                    evidence_refs=[ref.strip() for ref in submission.evidence_refs],
                    detector_version_snapshot=alert.detector_version,
                    calibration_eligible=calibration_eligible,
                    decided_at=submission.decided_at,
                    causal_claim=False,
                    platform_internal_cause_confirmed=False,
                )
                .on_conflict_do_nothing(constraint="uq_alert_outcomes_dedupe_key")
                .returning(AlertOutcomeRecord.id)
            )
            outcome_id = (await session.execute(statement)).scalar_one_or_none()
            if outcome_id is None:
                existing = (
                    await session.execute(
                        select(AlertOutcomeRecord).where(AlertOutcomeRecord.dedupe_key == dedupe_key)
                    )
                ).scalar_one()
                return _serialize(existing, inserted=False)

            record = (
                await session.execute(
                    select(AlertOutcomeRecord).where(AlertOutcomeRecord.id == outcome_id)
                )
            ).scalar_one()
            if latest is None or submission.decided_at >= latest.decided_at:
                alert.outcome = submission.classification.value
            return _serialize(record, inserted=True)

    async def history(self, *, alert_id: UUID) -> list[dict[str, Any]]:
        async with self._sessions() as session:
            exists = (
                await session.execute(select(AlertRecord.id).where(AlertRecord.id == alert_id))
            ).scalar_one_or_none()
            if exists is None:
                raise LookupError("alert_not_found")
            records = (
                await session.execute(
                    select(AlertOutcomeRecord)
                    .where(AlertOutcomeRecord.alert_id == alert_id)
                    .order_by(AlertOutcomeRecord.decided_at.asc(), AlertOutcomeRecord.created_at.asc())
                )
            ).scalars().all()
            return [_serialize(record, inserted=False) for record in records]

    async def report(self, *, detector_version: str | None = None) -> DetectorFeedbackReport:
        async with self._sessions() as session:
            statement = select(AlertOutcomeRecord).where(
                AlertOutcomeRecord.calibration_eligible.is_(True)
            )
            if detector_version is not None:
                statement = statement.where(
                    AlertOutcomeRecord.detector_version_snapshot == detector_version
                )
            records = (
                await session.execute(
                    statement.order_by(
                        AlertOutcomeRecord.alert_id.asc(),
                        AlertOutcomeRecord.decided_at.desc(),
                        AlertOutcomeRecord.created_at.desc(),
                    )
                )
            ).scalars().all()

        latest_by_alert: dict[UUID, AlertOutcomeRecord] = {}
        for record in records:
            latest_by_alert.setdefault(record.alert_id, record)
        latest = list(latest_by_alert.values())

        classification_counts = {item.value: 0 for item in OutcomeClassification}
        cause_counts = {item.value: 0 for item in CauseClassification}
        for record in latest:
            classification_counts[record.classification] = (
                classification_counts.get(record.classification, 0) + 1
            )
            if record.cause_classification:
                cause_counts[record.cause_classification] = (
                    cause_counts.get(record.cause_classification, 0) + 1
                )

        false_positive_count = classification_counts[OutcomeClassification.FALSE_POSITIVE.value]
        inconclusive_count = classification_counts[OutcomeClassification.INCONCLUSIVE.value]
        positive_classes = {
            OutcomeClassification.CONFIRMED.value,
            OutcomeClassification.PARTIALLY_CONFIRMED.value,
            OutcomeClassification.RESOLVED.value,
            OutcomeClassification.PERSISTENT.value,
        }
        validated_positive_count = sum(classification_counts[item] for item in positive_classes)
        decisive_outcomes = validated_positive_count + false_positive_count
        false_positive_rate = (
            false_positive_count / decisive_outcomes if decisive_outcomes else None
        )
        validated_positive_rate = (
            validated_positive_count / decisive_outcomes if decisive_outcomes else None
        )
        return DetectorFeedbackReport(
            detector_version=detector_version,
            total_latest_outcomes=len(latest),
            decisive_outcomes=decisive_outcomes,
            validated_positive_count=validated_positive_count,
            false_positive_count=false_positive_count,
            inconclusive_count=inconclusive_count,
            classification_counts=classification_counts,
            cause_counts=cause_counts,
            false_positive_rate=false_positive_rate,
            validated_positive_rate=validated_positive_rate,
            causal_claim=False,
            platform_internal_cause_confirmed=False,
        )
