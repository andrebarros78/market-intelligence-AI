from __future__ import annotations

import base64
import binascii
import os

from fastapi import FastAPI

from market_intelligence.api.app import create_app
from market_intelligence.api.real_read_oauth import build_real_read_oauth_router
from market_intelligence.core.config import Settings
from market_intelligence.marketplaces.mercadolivre.oauth.real_read import (
    RealReadOAuthSettings,
    build_real_read_oauth_runtime,
    close_real_read_oauth_runtime,
)
from market_intelligence.persistence.database import (
    create_database_engine,
    create_session_factory,
)


def decode_oauth_key(value: str) -> bytes:
    if not value:
        raise RuntimeError("MI_ML_OAUTH_KEY_B64 is required")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("MI_ML_OAUTH_KEY_B64 is invalid") from exc
    if len(decoded) != 32:
        raise RuntimeError("MI_ML_OAUTH_KEY_B64 must decode to exactly 32 bytes")
    return decoded


def create_real_read_app_from_env() -> FastAPI:
    settings = Settings.from_env()
    settings.assert_module01_operational_security()
    if not settings.database_url:
        raise RuntimeError("MI_DATABASE_URL is required for REAL-READ-01")

    oauth_settings = RealReadOAuthSettings.from_env()
    oauth_settings.assert_enabled()
    encryption_key = decode_oauth_key(os.getenv("MI_ML_OAUTH_KEY_B64", ""))

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    runtime = build_real_read_oauth_runtime(
        sessions=sessions,
        encryption_key=encryption_key,
        settings=oauth_settings,
    )

    app = create_app(settings=settings)
    app.include_router(build_real_read_oauth_router(runtime))
    app.state.real_read_oauth_runtime = runtime
    app.state.real_read_database_engine = engine

    async def shutdown_real_read_runtime() -> None:
        await close_real_read_oauth_runtime(runtime)
        await engine.dispose()

    app.add_event_handler("shutdown", shutdown_real_read_runtime)
    return app
