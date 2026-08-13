from __future__ import annotations

from datetime import UTC, datetime

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector
from market_intelligence.workflows.activities import RadarActivities


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _observation(
    current: float,
    *,
    expected: float | None = 100.0,
    effects: list[dict] | None = None,
    history: list[float] | None = None,
) -> RadarObservation:
    analysis: dict = {
        "metric": "visits",
        "observable_effects": effects or [],
    }
    if expected is not None:
        analysis["expected"] = expected
    return RadarObservation(
        entity_id="TARGET",
        observed_at=datetime.now(UTC),
        metrics={"visits": current},
        history={"visits": HISTORY if history is None else history},
        context={"residual_analysis": analysis},
    )


def test_detects_material_unexplained_residual() -> None:
    observation = _observation(
        60,
        effects=[
            {"name": "seasonality", "contribution": -2.0, "source": "calendar"},
            {"name": "competition", "contribution": -3.0, "source": "market"},
        ],
    )
    result = UnexplainedResidualDetector().evaluate(observation)
    assert result is not None
    assert result.level == EvidenceLevel.INFERENCE
    assert result.attributes["pattern"] == "unexplained_residual"
    assert result.attributes["observed_delta"] == -40.0
    assert result.attributes["explained_delta"] == -5.0
    assert result.attributes["unexplained_residual"] == -35.0
    assert result.attributes["unexplained_fraction"] == 0.875
    assert result.attributes["observable_causes"] == ["seasonality", "competition"]
    assert result.attributes["cause_status"] == "unknown_not_inferred"
    assert result.attributes["detector_version"] == "unexplained-residual@1.0.0"


def test_does_not_alert_when_observable_effects_explain_change() -> None:
    result = UnexplainedResidualDetector().evaluate(
        _observation(60, effects=[{"name": "known_factor", "contribution": -38.0}])
    )
    assert result is None


def test_does_not_alert_for_small_total_change() -> None:
    assert UnexplainedResidualDetector().evaluate(_observation(92)) is None


def test_derives_expected_from_history_when_explicit_expected_is_absent() -> None:
    result = UnexplainedResidualDetector().evaluate(
        _observation(60, expected=None, effects=[])
    )
    assert result is not None
    assert result.attributes["expected"] == 100.0
    assert result.attributes["reference_source"] == "history_median"


def test_fails_closed_without_enough_history_for_expected() -> None:
    result = UnexplainedResidualDetector().evaluate(
        _observation(60, expected=None, history=[100, 101, 99])
    )
    assert result is None


def test_invalid_residual_analysis_is_ignored() -> None:
    observation = RadarObservation(
        entity_id="TARGET",
        observed_at=datetime.now(UTC),
        metrics={"visits": 60},
        history={"visits": HISTORY},
        context={
            "residual_analysis": {
                "metric": "visits",
                "expected": 100,
                "observable_effects": [{"name": "bad", "contribution": "invalid"}],
            }
        },
    )
    assert UnexplainedResidualDetector().evaluate(observation) is None


def test_default_radar_and_alert_contract_propagate_residual_evidence() -> None:
    observation = _observation(
        60,
        effects=[
            {"name": "seasonality", "contribution": -2.0},
            {"name": "competition", "contribution": -3.0},
        ],
    )
    finding = build_default_radar().evaluate(observation)
    residuals = [r for r in finding.detector_results if r.detector == "unexplained_residual_v1"]
    assert residuals
    alert = alert_from_finding(
        finding=finding,
        marketplace="mercadolivre",
        entity_type="item",
        observed_at=observation.observed_at,
        context={},
    )
    assert alert is not None
    assert alert.unexplained_residual == -35.0
    assert alert.observable_causes == ["seasonality", "competition"]
    assert "unexplained-residual@1.0.0" in (alert.detector_version or "")
    assert alert.evidence_classification in {EvidenceLevel.INFERENCE, EvidenceLevel.HYPOTHESIS}


async def test_temporal_radar_activity_uses_same_residual_detector() -> None:
    observation = _observation(60, effects=[])
    result = await RadarActivities(build_default_radar()).evaluate(
        observation.model_dump(mode="json")
    )
    by_name = {item["detector"]: item for item in result["detector_results"]}
    residual = by_name["unexplained_residual_v1"]
    assert residual["level"] == "inference"
    assert residual["attributes"]["unexplained_residual"] == -40.0
