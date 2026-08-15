from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.sovereign.investigation_bridge import (
    build_radar_observation,
    normalize_investigation_result,
    signal_metrics,
)
from market_intelligence.intelligence.sovereign.models import SignalEnvelope


def _signal(
    *,
    signal_id: str = "s1",
    entity_type: str = "item",
    kind: str = "snapshot_item",
    payload: dict | None = None,
    seconds: int = 0,
) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=signal_id,
        marketplace="mercadolivre",
        entity_type=entity_type,
        entity_id="MLB1",
        kind=kind,
        source="test",
        observed_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC) + timedelta(seconds=seconds),
        payload=payload or {"price": 100.0, "available_quantity": 10, "sold_quantity": 3},
        provenance={"source": "test"},
        official_resource_fetched=True,
        confidence=0.8,
    )


def test_snapshot_metrics_are_numeric_and_minimized() -> None:
    metrics = signal_metrics(
        _signal(payload={"price": 101.5, "available_quantity": 9, "sold_quantity": 4, "title": "never-forward"})
    )
    assert metrics == {"price": 101.5, "available_quantity": 9.0, "sold_quantity": 4.0}


def test_surface_metrics_use_structure_not_values() -> None:
    surface = _signal(
        entity_type="surface",
        kind="har_surface",
        payload={
            "status": 200,
            "schema_paths": ["$.a:int", "$.b:str"],
            "top_level_fields": ["a", "b"],
            "request_query_keys": ["limit"],
            "request_metadata": {"header_count": 5, "credential_header_present": True},
            "response_metadata": {
                "header_count": 7,
                "json_schema": {"schema_paths": ["$.x:int"], "top_level_fields": ["x"]},
            },
        },
    )
    metrics = signal_metrics(surface)
    assert metrics["status_code"] == 200.0
    assert metrics["schema_path_count"] == 2.0
    assert metrics["request_credential_header_present"] == 1.0
    assert metrics["response_schema_path_count"] == 1.0


def test_build_radar_observation_projects_history_and_instigated_hypotheses() -> None:
    current = _signal(payload={"price": 120.0, "available_quantity": 8})
    history = (
        _signal(signal_id="h1", payload={"price": 100.0, "available_quantity": 10}, seconds=-120),
        _signal(signal_id="h2", payload={"price": 105.0, "available_quantity": 9}, seconds=-60),
    )
    observation = build_radar_observation(
        current,
        history,
        hypotheses=("Preço pode ter mudado de regime.",),
    )
    assert observation is not None
    assert observation.metrics == {"price": 120.0, "available_quantity": 8.0}
    assert observation.history["price"] == [100.0, 105.0]
    assert observation.context["hypotheses"] == ["Preço pode ter mudado de regime."]
    assert observation.context["causal_claim"] is False


def test_signal_without_supported_metrics_is_not_forced_into_investigator() -> None:
    signal = _signal(payload={"status": "active", "title": "no numeric signal"})
    assert build_radar_observation(signal, ()) is None


def test_investigation_result_is_normalized_for_validator_and_mclp() -> None:
    normalized = normalize_investigation_result(
        {
            "case_id": "case-1",
            "event_id": "event-1",
            "event_inserted": True,
            "event_ignored": False,
            "status": "confirmed",
            "confidence": 0.91,
            "observation_count": 3,
            "anomalous_observation_count": 3,
            "ever_confirmed": True,
            "hypotheses": [{"key": "h", "statement": "x"}],
            "engine_version": "progressive-investigation@1.0.0",
            "step": {
                "finding_hash": "a" * 64,
                "status_after": "confirmed",
                "confidence_after": 0.91,
                "evidence_summary": {"causal_claim": False},
            },
        }
    )
    assert normalized is not None
    assert normalized["status_after"] == "confirmed"
    assert normalized["confidence_after"] == 0.91
    assert normalized["observation_count"] == 3
    assert normalized["causal_claim"] is False
    assert normalized["evidence_summary"]["case_id"] == "case-1"


def test_none_investigation_stays_none() -> None:
    assert normalize_investigation_result(None) is None
