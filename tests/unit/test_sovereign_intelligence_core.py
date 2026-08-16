from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_intelligence.intelligence.sovereign.core import SovereignIntelligenceCore
from market_intelligence.intelligence.sovereign.models import (
    AutonomyLevel,
    KnowledgeState,
    SignalEnvelope,
)


def signal(
    *, signal_id: str = "s1", kind: str = "catalog_suggestion", confidence: float = 0.9,
    official: bool = True, payload: dict | None = None, seconds: int = 0,
) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=signal_id, marketplace="mercadolivre", entity_type="item", entity_id="MLB1",
        kind=kind, source="official_api",
        observed_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC) + timedelta(seconds=seconds),
        payload=payload or {"price": 100.0, "available_quantity": 10},
        provenance={"endpoint": "/items/MLB1", "method": "GET"},
        official_resource_fetched=official, confidence=confidence,
    )


def confirmed_investigation(*, causal_claim: bool = False) -> dict:
    return {
        "finding_hash": "a" * 64, "status_after": "confirmed", "confidence_after": 0.92,
        "observation_count": 3, "evidence_summary": {"official_reads": 3}, "hypotheses": [],
        "causal_claim": causal_claim,
    }


def test_core_closes_discovery_to_learning_prediction_loop() -> None:
    core = SovereignIntelligenceCore()
    history = (
        signal(signal_id="h1", payload={"price": 95.0, "available_quantity": 10}, seconds=-120),
        signal(signal_id="h2", payload={"price": 98.0, "available_quantity": 10}, seconds=-60),
    )
    report = core.process(signal(), history=history, investigation=confirmed_investigation())
    assert report.validation.state is KnowledgeState.VALIDATED
    assert report.learning["state"] == "validated_fact"
    assert report.probe.questions
    assert report.correlation.related_signal_ids == ("h1", "h2")
    assert report.intelligence.classification == "platform_behavior_signal"
    assert report.counterintelligence
    assert report.prediction.leading_indicators
    assert report.action_intent.direct_marketplace_write is False
    assert report.marketplace_writes == 0
    assert report.audit.passed is True


def test_core_quarantines_unproven_causal_claim() -> None:
    report = SovereignIntelligenceCore().process(
        signal(), history=(signal(signal_id="h1", seconds=-60),),
        investigation=confirmed_investigation(causal_claim=True),
    )
    assert report.validation.state is KnowledgeState.QUARANTINED
    assert report.learning["state"] == "quarantined"
    assert report.prediction.confidence <= 0.20
    assert report.prediction.state is KnowledgeState.QUARANTINED
    assert report.audit.passed is True
    assert report.action_intent.direct_marketplace_write is False


def test_sensitive_experiment_never_executes_inside_core() -> None:
    report = SovereignIntelligenceCore().process(
        signal(kind="price_suggestion"),
        history=(signal(signal_id="h1", kind="price_suggestion", seconds=-60),),
        investigation=confirmed_investigation(),
    )
    assert report.experiment.marketplace_write_required is True
    assert report.experiment.requires_action_gateway is True
    assert report.experiment.executable_now is False
    assert report.action_intent.autonomy_level is AutonomyLevel.HUMAN_REQUIRED
    assert report.action_intent.requires_human_approval is True
    assert report.action_intent.direct_marketplace_write is False


def test_unconfirmed_signal_stays_below_validated() -> None:
    report = SovereignIntelligenceCore().process(signal(confidence=0.99))
    assert report.validation.state is not KnowledgeState.VALIDATED
    assert report.learning["state"] == "under_investigation"
    assert report.intelligence.confidence == 0.95
    assert report.audit.passed is True
    assert report.action_intent.autonomy_level is AutonomyLevel.RECOMMEND


def test_read_only_boundary_is_fail_closed() -> None:
    core = SovereignIntelligenceCore()
    with pytest.raises(RuntimeError, match="read_only_violation"):
        core.process(signal(), marketplace_read_only=False)
    with pytest.raises(RuntimeError, match="read_only_violation"):
        core.process(signal(), marketplace_writes=1)


@pytest.mark.parametrize("payload", [{"access_token": "x"}, {"nested": {"client_secret": "x"}}, {"nested": [{"authorization": "Bearer x"}]}])
def test_secret_contamination_is_blocked(payload: dict) -> None:
    with pytest.raises(RuntimeError, match="secret_contamination"):
        SovereignIntelligenceCore().process(signal(payload=payload))


def test_counterintelligence_maps_behavioral_exposure_without_claiming_hidden_access() -> None:
    report = SovereignIntelligenceCore().process(signal(kind="question_created"))
    exposure = report.counterintelligence[0]
    assert "plataforma observa" in exposure.platform_observes.lower()
    assert exposure.possible_inferences
    assert "nao tentar ocultar" in exposure.mitigation


def test_every_action_remains_behind_action_gateway() -> None:
    core = SovereignIntelligenceCore()
    for kind in ("order", "question", "claim", "catalog_suggestion", "price_suggestion"):
        report = core.process(signal(signal_id=kind, kind=kind))
        assert report.action_intent.requires_action_gateway is True
        assert report.action_intent.direct_marketplace_write is False
        assert report.marketplace_writes == 0


def test_collector_generated_telemetry_cannot_become_market_fact() -> None:
    s = signal(
        signal_id="collector-channel",
        kind="/visits/items",
        payload={"status_code": 200, "latency_ms": 180.0, "attempt": 1},
    ).model_copy(
        update={
            "entity_type": "channel_operation",
            "entity_id": "/visits/items",
            "source": "universal_sensor_channel",
            "provenance": {
                "record": "channel_events",
                "collector_generated_pattern": True,
                "intelligence_scope": "instrumentation",
            },
        }
    )
    report = SovereignIntelligenceCore().process(
        s,
        history=(s.model_copy(update={"signal_id": "collector-h1"}),),
        investigation=confirmed_investigation(),
    )
    assert report.intelligence.classification == "collector_telemetry"
    assert report.intelligence.threat is False
    assert report.intelligence.opportunity is False
    assert report.learning["state"] == "rejected"
    assert report.validation.state is KnowledgeState.REJECTED


def test_snapshot_projection_keeps_commercial_values_without_pii() -> None:
    from market_intelligence.intelligence.sovereign.runtime import _safe_snapshot_payload

    visits = _safe_snapshot_payload({"MLB1": 123}, entity_type="visits", entity_id="MLB1")
    competition = _safe_snapshot_payload(
        {"current_price": 100.0, "price_to_win": 98.0, "visit_share": "maximum", "status": "winning"},
        entity_type="catalog_competition",
        entity_id="MLB1",
    )
    order = _safe_snapshot_payload(
        {"total_amount": 199.9, "paid_amount": 199.9, "currency_id": "BRL", "status": "paid", "buyer": {"email": "x@example.com"}},
        entity_type="order",
        entity_id="1",
    )
    assert visits["visits"] == 123
    assert competition["price_to_win"] == 98.0
    assert competition["visit_share"] == "maximum"
    assert order["total_amount"] == 199.9
    assert "buyer" not in order
