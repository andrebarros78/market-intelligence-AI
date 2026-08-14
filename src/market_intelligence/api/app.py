from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI

from market_intelligence.api.ingestion import build_synthetic_ingestion_router
from market_intelligence.api.oauth import build_synthetic_oauth_router
from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import SyntheticOAuthRuntime
from market_intelligence.workflows.contracts import WorkflowEngine


def create_app(
    settings: Settings | None = None,
    *,
    oauth_runtime: SyntheticOAuthRuntime | None = None,
    oauth_refresh_engine: WorkflowEngine | None = None,
    ingestion_engine: WorkflowEngine | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    radar = build_default_radar()
    app = FastAPI(title="Market Intelligence IA", version="0.12.0")

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
            "oauth_synthetic_configured": oauth_runtime is not None,
            "oauth_refresh_workflow_configured": oauth_refresh_engine is not None,
            "synthetic_ingestion_workflow_configured": ingestion_engine is not None,
        }

    @app.get("/v1/system/capabilities")
    def capabilities() -> dict[str, object]:
        return {
            "marketplaces": ["mercadolivre"],
            "mercadolivre_read_adapter": {
                "implemented": True,
                "default_network_mode": "blocked",
                "synthetic_transport": True,
                "capability_auditor": True,
                "schema_fingerprint": True,
                "partial_content_206": True,
                "rate_limit_429": True,
                "real_network_enabled": False,
            },
            "persistence": {
                "postgresql_schema": True,
                "alembic_migrations": True,
                "raw_event_idempotency": True,
                "channel_event_idempotency": True,
                "entity_upsert": True,
                "change_snapshots": True,
                "alert_evidence_atomic_save": True,
                "alert_idempotency": True,
                "oauth_state_single_consume": True,
                "runtime_connection_configured": bool(cfg.database_url),
            },
            "oauth": {
                "synthetic_foundation": True,
                "internal_routes": True,
                "runtime_configured": oauth_runtime is not None,
                "temporal_refresh_configured": oauth_refresh_engine is not None,
                "pkce_s256": True,
                "encrypted_credentials": True,
                "real_network_enabled": False,
                "marketplace_writes_enabled": False,
            },
            "radar": {
                "known_rules": True,
                "statistical_baseline": True,
                "vertical_synthetic_path": True,
                "persistent_alerts": True,
                "evidence_contract_v2": True,
                "epistemic_classification": True,
                "investigation_context_persistence": True,
                "temporal": True,
                "temporal_detector": "temporal-pattern@1.0.0",
                "seasonality": False,
                "multivariate": True,
                "multivariate_detector": "multivariate-relationship@1.0.0",
                "regime_change": True,
                "regime_change_detector": "regime-change@1.0.0",
                "relational_controls": True,
                "relational_control_detector": "relational-control@1.0.0",
                "control_group_comparison": True,
                "operational_counterfactual": True,
                "operational_counterfactual_detector": "operational-counterfactual@1.0.0",
                "counterfactual": False,
                "unexplained_residual_detector": True,
                "unexplained_residual_detector_version": "unexplained-residual@1.0.0",
                "distribution_anomaly_index": True,
                "distribution_anomaly_index_version": "distribution-anomaly-index@1.0.0",
                "iad_calibrator_version": "iad-calibrator@1.0.0",
                "iad_requires_versioned_calibration": True,
                "iad_production_calibrated": False,
                "iad_causal_claim": False,
            },
            "channel_sensor": True,
            "channel_sensor_details": {
                "persistent": True,
                "synthetic_only": True,
                "regime_correlation": True,
                "regime_correlation_detector": "channel-regime-correlation@1.0.0",
                "business_correlation": True,
                "causal_claim": False,
            },
            "production_workflows": {
                "engine": "temporal",
                "implemented": True,
                "runtime_enabled": cfg.temporal_enabled,
                "durable_ingestion": True,
                "synthetic_ingestion_configured": ingestion_engine is not None,
                "durable_synthetic_oauth_refresh": True,
                "activity_retries": True,
                "workflow_idempotency": True,
                "marketplace_reads_only": True,
            },
        }

    @app.post("/v1/radar/evaluate", response_model=RadarFinding)
    def evaluate(observation: RadarObservation) -> RadarFinding:
        return radar.evaluate(observation)

    app.include_router(build_synthetic_oauth_router(oauth_runtime, oauth_refresh_engine))
    app.include_router(build_synthetic_ingestion_router(ingestion_engine))
    return app


app = create_app()
