from __future__ import annotations

import os

from fastapi import FastAPI

from market_intelligence.api.app import create_app
from market_intelligence.api.mercadolivre_webhooks import build_mercadolivre_webhook_router
from market_intelligence.core.config import Settings
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.postgresql import PostgresRawEventRepository


def create_mercadolivre_webhook_app_from_env() -> FastAPI:
    settings = Settings.from_env()
    settings.assert_module01_operational_security()
    if not settings.database_url:
        raise RuntimeError("MI_DATABASE_URL is required for REAL-WEBHOOK-01")

    application_id = os.getenv("MI_ML_APP_ID", "").strip()
    if not application_id:
        raise RuntimeError("MI_ML_APP_ID is required for REAL-WEBHOOK-01")

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    raw_events = PostgresRawEventRepository(sessions)

    app = create_app(settings=settings)
    app.include_router(
        build_mercadolivre_webhook_router(
            raw_events,
            application_id=application_id,
        )
    )
    app.state.mercadolivre_webhook_database_engine = engine
    app.state.mercadolivre_webhook_sessions = sessions

    async def shutdown_webhook_runtime() -> None:
        await engine.dispose()

    app.add_event_handler("shutdown", shutdown_webhook_runtime)
    return app
