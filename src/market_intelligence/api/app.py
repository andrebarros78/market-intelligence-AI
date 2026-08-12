from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI

from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation
from market_intelligence.intelligence.radar.service import RadarService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    radar = RadarService([KnownRuleDetector(), RobustZScoreDetector()])
    app = FastAPI(title="Market Intelligence IA", version="0.3.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "time": datetime.now(UTC).isoformat()}

    @app.get("/ready")
    def ready() -> dict[str, object]:
        return {
            "ready": True,
            "environment": cfg.environment,
            "read_only": cfg.read_only,
            "marketplace_writes": cfg.allow_marketplace_writes and not cfg.read_only,
            "persistence_configured": bool(cfg.database_url),
            "temporal_enabled": cfg.temporal_enabled,
        }

    @app.get("/v1/system/capabilities")
    def capabilities() -> dict[str, object]:
        return {
            "marketplaces": ["mercadolivre"],
            "persistence": {
                "postgresql_schema": True,
                "alembic_migrations": True,
                "raw_event_idempotency": True,
                "entity_upsert": True,
                "change_snapshots": True,
                "alert_evidence_atomic_save": True,
                "oauth_state_single_consume": True,
                "runtime_connection_configured": bool(cfg.database_url),
            },
            "radar": {
                "known_rules": True,
                "statistical_baseline": True,
                "temporal": False,
                "multivariate": False,
                "regime_change": False,
                "counterfactual": False,
                "unexplained_residual": False,
            },
            "channel_sensor": True,
            "production_workflows": {
                "engine": "temporal",
                "implemented": True,
                "runtime_enabled": cfg.temporal_enabled,
                "durable_ingestion": True,
                "activity_retries": True,
                "workflow_idempotency": True,
                "marketplace_reads_only": True,
            },
        }

    @app.post("/v1/radar/evaluate", response_model=RadarFinding)
    def evaluate(observation: RadarObservation) -> RadarFinding:
        return radar.evaluate(observation)

    return app


app = create_app()
