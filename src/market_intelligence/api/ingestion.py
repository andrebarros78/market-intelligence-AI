from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from market_intelligence.workflows.contracts import WorkflowEngine
from market_intelligence.workflows.names import WORKFLOW_INGESTION

_SAFE_ID = r"^[A-Za-z0-9._:-]+$"


class SyntheticIngestionRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=160, pattern=_SAFE_ID)
    marketplace: str = Field(min_length=1, max_length=64, pattern=_SAFE_ID)
    raw_event: dict[str, Any]
    channel_event: dict[str, Any] | None = None
    resource: str | None = Field(default=None, max_length=2048)
    entity_type: str | None = Field(default=None, max_length=64, pattern=_SAFE_ID)
    entity_id: str | None = Field(default=None, max_length=160, pattern=_SAFE_ID)
    radar_observation: dict[str, Any] | None = None


class SyntheticIngestionResponse(BaseModel):
    workflow_id: str


def build_synthetic_ingestion_router(engine: WorkflowEngine | None) -> APIRouter:
    router = APIRouter(prefix="/v1/internal/ingestion", tags=["internal-ingestion-synthetic"])

    @router.post(
        "/synthetic",
        response_model=SyntheticIngestionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def ingest(request: SyntheticIngestionRequest) -> SyntheticIngestionResponse:
        if engine is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="synthetic_ingestion_workflow_not_configured",
            )
        payload = request.model_dump(exclude={"idempotency_key"}, exclude_none=True)
        try:
            workflow_id = await engine.start(
                WORKFLOW_INGESTION,
                payload,
                idempotency_key=request.idempotency_key,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="synthetic_ingestion_workflow_start_failed",
            ) from None
        return SyntheticIngestionResponse(workflow_id=workflow_id)

    return router
