from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from market_intelligence.intelligence.sovereign.models import (
    CorrelationFinding,
    KnowledgeState,
    SignalEnvelope,
    ValidationVerdict,
)
from market_intelligence.intelligence.sovereign.organs import SovereignPredictor
from market_intelligence.missions.prediction_semantics import compare, contract_from_prediction

NOW = datetime(2026, 8, 18, 13, 0, tzinfo=UTC)


def sig(value: float | None, *, entity_type: str = "visits", metric: str = "visits", minutes: int = -1, source: str = "universal_sensor_snapshot") -> SignalEnvelope:
    payload = {} if value is None else ({"price": value} if metric == "listing.price" else {metric: value})
    return SignalEnvelope(signal_id=f"s-{entity_type}-{metric}-{minutes}-{value}", marketplace="mercadolivre", entity_type=entity_type, entity_id="MLB-V2-TEST", kind=f"snapshot_{entity_type}", source=source, observed_at=NOW+timedelta(minutes=minutes), payload=payload, provenance={"record":"snapshots"}, official_resource_fetched=True, confidence=0.8)


def valid() -> ValidationVerdict:
    return ValidationVerdict(state=KnowledgeState.VALIDATED, confidence=0.9, evidence_sufficient=True, provenance_complete=True, repeated_observation=True, causal_validated=False, reason="validated_repeated_observation")


def corr() -> CorrelationFinding:
    return CorrelationFinding(related_signal_ids=("h1","h2"), shared_dimensions=("visits",), numeric_changes={"visits":1.0}, strength=0.8, fact_eligible=True, reason="repeated")


def forecast(*, current: float = 100, history=(120, 110), entity_type="visits", metric="visits"):
    p=SovereignPredictor()
    hs=tuple(sig(v, entity_type=entity_type, metric=metric, minutes=m) for v,m in zip(history,(-3,-2)))
    return p.predict(sig(current, entity_type=entity_type, metric=metric), corr(), valid(), history=hs, created_at=NOW)


def test_valid_decrease_forecast() -> None:
    p=forecast(); assert p.prediction_type=="FORECAST"; assert p.operator=="DECREASE"; assert p.expected_direction=="DOWN"


def test_valid_increase_forecast() -> None:
    p=forecast(history=(80,90)); assert p.prediction_type=="FORECAST"; assert p.operator=="INCREASE"; assert p.expected_direction=="UP"


def test_forecast_has_complete_semantic_contract() -> None:
    p=forecast(); d=p.model_dump(mode="json")
    for key in ("target_entity","target_metric","operator","baseline_value","baseline_source","baseline_observed_at","tolerance","evaluation_window","evidence_source","confidence","falsifier","created_at"):
        assert d[key] not in (None,"")
    assert contract_from_prediction(d, entity_id=p.target_entity, observed_at=NOW-timedelta(minutes=1)) is not None


def test_baseline_is_observed_before_created_at() -> None:
    p=forecast(); assert p.baseline_observed_at <= p.created_at


def test_future_history_fails_closed_without_lookahead() -> None:
    predictor=SovereignPredictor(); current=sig(100)
    h1=sig(80,minutes=-3); future=sig(120,minutes=0)
    p=predictor.predict(current,corr(),valid(),history=(h1,future),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.abstention_reason=="future_history_rejected"


def test_future_baseline_fails_closed() -> None:
    p=SovereignPredictor().predict(sig(100,minutes=1),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.abstention_reason=="baseline_from_future_rejected"


def test_missing_metric_abstains() -> None:
    p=SovereignPredictor().predict(sig(None),corr(),valid(),history=(sig(80,minutes=-3),sig(90,minutes=-2)),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.abstention_reason=="baseline_missing"


def test_missing_baseline_abstains() -> None:
    p=SovereignPredictor().predict(sig(None),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"


def test_missing_observer_abstains() -> None:
    p=SovereignPredictor().predict(sig(100,source="universal_sensor_channel"),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.abstention_reason=="observer_not_supported"


def test_orders_are_not_enabled_without_entity_compatible_observer() -> None:
    p=SovereignPredictor().predict(sig(1,entity_type="order",metric="orders"),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.abstention_reason=="observer_not_supported_for_order_count"


def test_insufficient_evidence_is_abstention_not_generic_forecast() -> None:
    weak=valid().model_copy(update={"state":KnowledgeState.OBSERVED,"evidence_sufficient":False})
    p=SovereignPredictor().predict(sig(100),corr(),weak,history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.operator is None; assert p.target_metric is None


def test_contract_rejects_abstention() -> None:
    p=SovereignPredictor().predict(sig(100),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert contract_from_prediction(p.model_dump(mode="json"),entity_id="MLB-V2-TEST",observed_at=NOW-timedelta(minutes=1)) is None


def test_contract_rejects_window_moved_before_creation() -> None:
    p=forecast(); d=p.model_dump(mode="json"); d["evaluation_window"]["start_at"]=(NOW-timedelta(minutes=1)).isoformat()
    assert contract_from_prediction(d,entity_id=p.target_entity,observed_at=NOW-timedelta(minutes=1)) is None


def test_forecast_contract_is_immutable() -> None:
    p=forecast()
    with pytest.raises(ValidationError): p.operator="INCREASE"


def test_tolerance_is_frozen_by_metric_policy() -> None:
    assert forecast().tolerance==1.0
    lp=forecast(current=100,history=(120,110),entity_type="listing",metric="listing.price"); assert lp.tolerance==0.01


def test_listing_stock_is_enabled_with_deterministic_observer() -> None:
    p=forecast(current=8,history=(10,9),entity_type="listing",metric="available_quantity")
    assert p.prediction_type=="FORECAST"; assert p.target_metric=="available_quantity"; assert p.evidence_source=="snapshots:listing"


def test_current_price_and_price_to_win_are_semantically_distinct() -> None:
    p=forecast(current=90,history=(100,95),entity_type="catalog_competition",metric="current_price")
    assert p.target_metric=="current_price"; assert p.evidence_source.endswith(":current_price")


def test_compare_correct_partial_incorrect_for_frozen_decrease() -> None:
    assert compare(operator="DECREASE",observed=90,expected=None,baseline=100,tolerance=1)==("EVALUATED_CORRECT",1.0)
    assert compare(operator="DECREASE",observed=100.5,expected=None,baseline=100,tolerance=1)==("EVALUATED_PARTIAL",0.5)
    assert compare(operator="DECREASE",observed=102,expected=None,baseline=100,tolerance=1)==("EVALUATED_INCORRECT",0.0)


def test_abstention_has_no_semantic_target_or_calibration_contract() -> None:
    p=SovereignPredictor().predict(sig(100),corr(),valid(),history=(),created_at=NOW)
    assert p.prediction_type=="ABSTAIN"; assert p.target_entity is None; assert p.target_metric is None; assert p.evaluation_window is None
