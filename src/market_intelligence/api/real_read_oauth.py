from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from market_intelligence.marketplaces.mercadolivre.oauth.real_read import (
    RealAuthorizationPlan,
    RealOAuthIdentity,
    RealReadOAuthRuntime,
)

_SAFE_ID = r"^[0-9]+$"


class RealOAuthStartRequest(BaseModel):
    expected_account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=_SAFE_ID,
    )


class RealOAuthStartResponse(BaseModel):
    authorization_url: str
    expires_at: str


class RealOAuthCallbackResponse(BaseModel):
    account_id: str
    site_id: str | None
    nickname: str | None
    status: str | None
    credential_version: int
    schema_fingerprint: str
    channel_event_persisted: bool


def _identity_response(identity: RealOAuthIdentity) -> RealOAuthCallbackResponse:
    return RealOAuthCallbackResponse(
        account_id=identity.account_id,
        site_id=identity.site_id,
        nickname=identity.nickname,
        status=identity.status,
        credential_version=identity.credential_version,
        schema_fingerprint=identity.schema_fingerprint,
        channel_event_persisted=identity.channel_event_persisted,
    )


def build_real_read_oauth_router(runtime: RealReadOAuthRuntime | None) -> APIRouter:
    router = APIRouter(tags=["mercadolivre-oauth-real-read"])

    def require_runtime() -> RealReadOAuthRuntime:
        if runtime is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mercadolivre_real_read_oauth_not_configured",
            )
        return runtime

    @router.get("/v1/internal/oauth/mercadolivre/read/ready")
    async def ready() -> dict[str, object]:
        service = require_runtime()
        report = await service.readiness()
        return {
            "ready": report.ready,
            "enabled": report.enabled,
            "database_ok": report.database_ok,
            "schema_ok": report.schema_ok,
            "settings_ok": report.settings_ok,
            "reasons": list(report.reasons),
            "marketplace_writes": False,
            "first_business_read": "/users/me",
        }

    @router.post(
        "/v1/internal/oauth/mercadolivre/read/start",
        response_model=RealOAuthStartResponse,
    )
    async def start(request: RealOAuthStartRequest) -> RealOAuthStartResponse:
        service = require_runtime()
        try:
            plan: RealAuthorizationPlan = await service.service.start(
                expected_account_id=request.expected_account_id
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mercadolivre_real_read_oauth_disabled",
            ) from None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mercadolivre_real_read_oauth_start_failed",
            ) from None
        return RealOAuthStartResponse(
            authorization_url=plan.authorization_url,
            expires_at=plan.expires_at.isoformat(),
        )

    @router.get(
        "/v1/oauth/mercadolivre/callback",
        response_model=RealOAuthCallbackResponse,
    )
    async def callback(
        code: str = Query(min_length=1, max_length=4096),
        state: str = Query(min_length=1, max_length=4096),
    ) -> RealOAuthCallbackResponse:
        service = require_runtime()
        try:
            identity = await service.service.callback(state=state, code=code)
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mercadolivre_oauth_callback_rejected",
            ) from None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mercadolivre_oauth_callback_failed",
            ) from None
        return _identity_response(identity)

    return router
