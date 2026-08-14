import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _payload() -> dict:
    observation = RadarObservation(
        entity_id="R114-PATH",
        observed_at=datetime.now(UTC),
        metrics={"visits": 75},
        history={"visits": HISTORY},
        context={
            "control_candidates": [
                {
                    "entity_id": name,
                    "metrics": {"visits": current},
                    "history": {"visits": HISTORY},
                }
                for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
            ]
        },
    )
    return observation.model_dump(mode="json")


def _iad_payload() -> dict:
    payload = _payload()
    payload["entity_id"] = "R116-PATH"
    payload["context"]["iad_calibration"] = {
        "version": "historical-fixture-v1",
        "source_type": "historical_validation",
        "weights": {
            "traffic_deviation": 0.5,
            "control_divergence": 0.5,
        },
        "threshold": 0.70,
        "min_components": 2,
        "production_approved": True,
        "sample_count": 20,
        "positive_count": 10,
        "negative_count": 10,
        "metrics": {"balanced_accuracy": 0.9},
    }
    return payload


def _channel_payload() -> dict:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=11)
    events = []
    for index in range(12):
        recent = index >= 8
        events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/items/MLB-R115",
                "observed_at": (start + timedelta(minutes=index)).isoformat(),
                "status_code": 503 if recent else 200,
                "latency_ms": 450.0 if recent else 90.0,
                "attempt": 2 if recent else 1,
                "attributes": {"partial_content": True} if recent else {},
            }
        )
    return RadarObservation(
        entity_id="R115-PATH",
        observed_at=now,
        metrics={"visits": 55},
        history={"visits": HISTORY},
        context={"channel_events": events},
    ).model_dump(mode="json")


def _counterfactual(results: list[dict]) -> dict:
    return next(item for item in results if item["detector"] == "operational_counterfactual_v1")


def _channel_regime(results: list[dict]) -> dict:
    return next(item for item in results if item["detector"] == "channel_regime_correlation_v1")


def _iad(results: list[dict]) -> dict:
    return next(item for item in results if item["detector"] == "distribution_anomaly_index_v1")


def test_http_radar_evaluate_exposes_operational_counterfactual() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/evaluate", json=_payload())
    assert response.status_code == 200
    result = _counterfactual(response.json()["detector_results"])
    assert result["attributes"]["counterfactual_expected"] == 100.0
    assert result["attributes"]["causal_claim"] is False


def test_radar_activity_preserves_operational_counterfactual() -> None:
    finding = asyncio.run(RadarActivities(build_default_radar()).evaluate(_payload()))
    result = _counterfactual(finding["detector_results"])
    assert result["attributes"]["counterfactual_kind"] == "operational_not_causal"
    assert result["attributes"]["fit_uses_current_target"] is False


def test_http_radar_evaluate_exposes_channel_regime_correlation() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/evaluate", json=_channel_payload())
    assert response.status_code == 200
    result = _channel_regime(response.json()["detector_results"])
    assert result["level"] == "inference"
    assert result["attributes"]["correlation_status"] == "joint_regime_detected"
    assert result["attributes"]["causal_claim"] is False


def test_radar_activity_preserves_channel_regime_correlation() -> None:
    finding = asyncio.run(RadarActivities(build_default_radar()).evaluate(_channel_payload()))
    result = _channel_regime(finding["detector_results"])
    assert result["attributes"]["channel_regime_detected"] is True
    assert result["attributes"]["internal_platform_cause_confirmed"] is False


def test_http_radar_evaluate_exposes_calibrated_iad() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/evaluate", json=_iad_payload())
    assert response.status_code == 200
    result = _iad(response.json()["detector_results"])
    assert result["level"] == "inference"
    assert result["attributes"]["iad_decision"] is True
    assert result["attributes"]["calibration_version"] == "historical-fixture-v1"
    assert result["attributes"]["causal_claim"] is False


def test_radar_activity_preserves_calibrated_iad() -> None:
    finding = asyncio.run(RadarActivities(build_default_radar()).evaluate(_iad_payload()))
    result = _iad(finding["detector_results"])
    assert result["attributes"]["alert_eligible"] is True
    assert result["attributes"]["component_count"] == 2
    assert result["attributes"]["internal_platform_cause_confirmed"] is False
