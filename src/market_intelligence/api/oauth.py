from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from market_intelligence.marketplaces.mercadolivre.oauth.runtime import SyntheticOAuthRuntime
from market_intelligence.workflows.contracts import WorkflowEngine
from market_intelligence.workflows.names import WORKFLOW_OAUTH_REFRESH

_SAFE_ID = r"^[A-Za-z0-9._:-]+$"


class OAuthStartRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=160, pattern=_SAFE_ID)
    redirect_uri: str | None = Field(default=None, max_length=2048)


class OAuthStartResponse(BaseModel):
    state: str
    code_challenge: str
    code_challenge_method: str
    expires_at: datetime


class OAuthCallbackRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=160, pattern=_SAFE_ID)
    state: SecretStr
    code: SecretStr


class OAuthCallbackResponse(BaseModel):
    credential_version: int


class OAuthRefreshRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=160, pattern=_SAFE_ID)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=_SAFE_ID)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=96, pattern=_SAFE_ID)


class OAuthRefreshResponse(BaseModel):
    workflow_id: str


def build_synthetic_oauth_router(
    runtime: SyntheticOAuthRuntime | None,
    refresh_engine: WorkflowEngine | None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/internal/oauth/synthetic", tags=["internal-oauth-synthetic"])

    def require_runtime() -> SyntheticOAuthRuntime:
        if runtime is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="synthetic_oauth_runtime_not_configured")
        return runtime

    @router.post("/start", response_model=OAuthStartResponse)
    async def start(request: OAuthStartRequest) -> OAuthStartResponse:
        service = require_runtime()
        try:
            plan = await service.transactions.start(account_id=request.account_id,
                                                    redirect_uri=request.redirect_uri)
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="synthetic_oauth_start_failed") from None
        return OAuthStartResponse(state=plan.state, code_challenge=plan.code_challenge,
                                  code_challenge_method=plan.code_challenge_method,
                                  expires_at=plan.expires_at)

    @router.post("/callback", response_model=OAuthCallbackResponse)
    async def callback(request: OAuthCallbackRequest) -> OAuthCallbackResponse:
        service = require_runtime()
        try:
            version = await service.transactions.callback(
                account_id=request.account_id,
                state=request.state.get_secret_value(),
                code=request.code.get_secret_value(),
            )
        except PermissionError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="synthetic_oauth_callback_rejected") from None
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="synthetic_oauth_callback_failed") from None
        return OAuthCallbackResponse(credential_version=version)

    @router.get("/health/{account_id}")
    async def credential_health(account_id: str) -> dict[str, object]:
        service = require_runtime()
        report = await service.health.get(account_id=account_id)
        return {
            "status": report.status.value,
            "expires_at": report.expires_at.isoformat() if report.expires_at else None,
            "refresh_eligible": report.refresh_eligible,
            "reasons": list(report.reasons),
        }

    @router.get("/ready")
    async def oauth_ready() -> dict[str, object]:
        service = require_runtime()
        report = await service.readiness()
        return {
            "ready": report.ready,
            "database_ok": report.database_ok,
            "schema_ok": report.schema_ok,
            "settings_ok": report.settings_ok,
            "reasons": list(report.reasons),
            "real_network": False,
            "marketplace_writes": False,
        }

    @router.post("/refresh", response_model=OAuthRefreshResponse, status_code=status.HTTP_202_ACCEPTED)
    async def refresh(request: OAuthRefreshRequest) -> OAuthRefreshResponse:
        require_runtime()
        if refresh_engine is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="oauth_refresh_workflow_not_configured")
        safe_payload = {"account_id": request.account_id}
        if request.correlation_id:
            safe_payload["correlation_id"] = request.correlation_id
        try:
            workflow_id = await refresh_engine.start(
                WORKFLOW_OAUTH_REFRESH,
                safe_payload,
                idempotency_key=request.idempotency_key,
            )
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="oauth_refresh_workflow_start_failed") from None
        return OAuthRefreshResponse(workflow_id=workflow_id)

    return router
