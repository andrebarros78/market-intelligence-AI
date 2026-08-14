from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.feedback import AlertOutcomeSubmission, DetectorFeedbackReport
from market_intelligence.persistence.feedback import PostgresFeedbackRepository


def build_feedback_router(
    sessions: async_sessionmaker[AsyncSession] | None,
    *,
    trusted_for_calibration: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/v1/internal/radar", tags=["radar-feedback"])
    repository = (
        PostgresFeedbackRepository(
            sessions,
            trusted_for_calibration=trusted_for_calibration,
        )
        if sessions is not None
        else None
    )

    def require_repository() -> PostgresFeedbackRepository:
        if repository is None:
            raise HTTPException(status_code=503, detail="posterior_feedback_persistence_not_configured")
        return repository

    @router.post("/alerts/{alert_id}/outcomes")
    async def record_outcome(
        alert_id: UUID,
        submission: AlertOutcomeSubmission,
    ) -> dict[str, object]:
        try:
            result = await require_repository().record(alert_id=alert_id, submission=submission)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            **result,
            "trusted_runtime": bool(repository and repository.trusted_for_calibration),
            "auto_calibration_applied": False,
        }

    @router.get("/alerts/{alert_id}/outcomes")
    async def outcome_history(alert_id: UUID) -> dict[str, object]:
        try:
            outcomes = await require_repository().history(alert_id=alert_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "alert_id": str(alert_id),
            "outcomes": outcomes,
            "append_only": True,
            "causal_claim": False,
        }

    @router.get("/feedback/report", response_model=DetectorFeedbackReport)
    async def feedback_report(
        detector_version: str | None = Query(default=None, max_length=160),
    ) -> DetectorFeedbackReport:
        return await require_repository().report(detector_version=detector_version)

    return router
