from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.investigation import (
    InvestigationState,
    InvestigationStatus,
    ProgressiveInvestigationEngine,
)
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation
from market_intelligence.persistence.models import (
    InvestigationCaseRecord,
    InvestigationEventRecord,
)


def investigation_active_key(marketplace: str, entity_type: str, entity_id: str) -> str:
    material = "\x1f".join([marketplace, entity_type, entity_id]).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def investigation_event_dedupe_key(
    marketplace: str,
    entity_type: str,
    entity_id: str,
    observation: RadarObservation,
    finding: RadarFinding,
) -> str:
    material = "\x1f".join(
        [
            marketplace,
            entity_type,
            entity_id,
            observation.observed_at.isoformat(),
            ProgressiveInvestigationEngine.finding_hash(finding),
        ]
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _state(case: InvestigationCaseRecord) -> InvestigationState:
    return InvestigationState.model_validate(
        {
            "status": case.status,
            "confidence": case.confidence,
            "observation_count": case.observation_count,
            "anomalous_observation_count": case.anomalous_observation_count,
            "anomaly_streak": case.anomaly_streak,
            "normal_streak": case.normal_streak,
            "ever_confirmed": case.ever_confirmed,
            "hypotheses": case.hypotheses or [],
        }
    )


def _event_result(
    case: InvestigationCaseRecord,
    event: InvestigationEventRecord,
    *,
    inserted: bool,
) -> dict[str, Any]:
    return {
        "case_id": str(case.id),
        "event_id": str(event.id),
        "event_inserted": inserted,
        "active": case.active_key is not None,
        "status": case.status,
        "confidence": case.confidence,
        "observation_count": case.observation_count,
        "anomalous_observation_count": case.anomalous_observation_count,
        "ever_confirmed": case.ever_confirmed,
        "first_observed_at": case.first_observed_at.isoformat(),
        "last_observed_at": case.last_observed_at.isoformat(),
        "hypotheses": case.hypotheses or [],
        "recommended_action": case.recommended_action,
        "engine_version": case.engine_version,
        "causal_claim": False,
        "step": {
            "observed_at": event.observed_at.isoformat(),
            "finding_hash": event.finding_hash,
            "status_before": event.status_before,
            "status_after": event.status_after,
            "anomalous": event.anomalous,
            "finding_score": event.finding_score,
            "confidence_before": event.confidence_before,
            "confidence_after": event.confidence_after,
            "confidence_delta": event.confidence_delta,
            "evidence_summary": event.evidence_summary,
            "hypotheses": event.hypotheses or [],
            "recommended_action": event.recommended_action,
            "engine_version": event.engine_version,
            "causal_claim": event.causal_claim,
        },
    }


class PostgresInvestigationRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        engine: ProgressiveInvestigationEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._engine = engine or ProgressiveInvestigationEngine()

    async def advance(
        self,
        *,
        marketplace: str,
        entity_type: str,
        finding: RadarFinding,
        observation: RadarObservation,
    ) -> dict[str, Any] | None:
        active_key = investigation_active_key(marketplace, entity_type, finding.entity_id)
        dedupe_key = investigation_event_dedupe_key(
            marketplace,
            entity_type,
            finding.entity_id,
            observation,
            finding,
        )

        async with self._sessions() as session, session.begin():
            existing_event = (
                await session.execute(
                    select(InvestigationEventRecord).where(
                        InvestigationEventRecord.dedupe_key == dedupe_key
                    )
                )
            ).scalar_one_or_none()
            if existing_event is not None:
                case = (
                    await session.execute(
                        select(InvestigationCaseRecord).where(
                            InvestigationCaseRecord.id == existing_event.case_id
                        )
                    )
                ).scalar_one()
                return _event_result(case, existing_event, inserted=False)

            case = (
                await session.execute(
                    select(InvestigationCaseRecord)
                    .where(InvestigationCaseRecord.active_key == active_key)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            previous = _state(case) if case is not None else None
            step = self._engine.advance(
                finding=finding,
                observation=observation,
                previous=previous,
            )
            if step is None:
                return None

            if case is None:
                case = InvestigationCaseRecord(
                    marketplace=marketplace,
                    entity_type=entity_type,
                    entity_id=finding.entity_id,
                    active_key=active_key,
                    status=step.status_after.value,
                    confidence=step.confidence_after,
                    observation_count=step.observation_count,
                    anomalous_observation_count=step.anomalous_observation_count,
                    anomaly_streak=step.anomaly_streak,
                    normal_streak=step.normal_streak,
                    ever_confirmed=step.ever_confirmed,
                    hypotheses=[item.model_dump(mode="json") for item in step.hypotheses],
                    recommended_action=step.recommended_action,
                    engine_version=step.engine_version,
                    first_observed_at=step.observed_at,
                    last_observed_at=step.observed_at,
                )
                session.add(case)
                await session.flush()
            else:
                case.status = step.status_after.value
                case.confidence = step.confidence_after
                case.observation_count = step.observation_count
                case.anomalous_observation_count = step.anomalous_observation_count
                case.anomaly_streak = step.anomaly_streak
                case.normal_streak = step.normal_streak
                case.ever_confirmed = step.ever_confirmed
                case.hypotheses = [item.model_dump(mode="json") for item in step.hypotheses]
                case.recommended_action = step.recommended_action
                case.engine_version = step.engine_version
                case.last_observed_at = step.observed_at

            if step.terminal:
                case.active_key = None

            event = InvestigationEventRecord(
                case_id=case.id,
                dedupe_key=dedupe_key,
                observed_at=step.observed_at,
                finding_hash=step.finding_hash,
                status_before=step.status_before.value if step.status_before else None,
                status_after=step.status_after.value,
                anomalous=step.anomalous,
                finding_score=step.finding_score,
                confidence_before=step.confidence_before,
                confidence_after=step.confidence_after,
                confidence_delta=step.confidence_delta,
                evidence_summary=step.evidence_summary,
                hypotheses=[item.model_dump(mode="json") for item in step.hypotheses],
                recommended_action=step.recommended_action,
                engine_version=step.engine_version,
                causal_claim=False,
            )
            session.add(event)
            await session.flush()
            return _event_result(case, event, inserted=True)
