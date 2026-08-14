from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def _approved_iad_profile() -> dict:
    return {
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


def test_operational_counterfactual_capability_is_separate_from_causal() -> None:
    client = TestClient(create_app(Settings()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["operational_counterfactual"] is True
    assert radar["operational_counterfactual_detector"] == "operational-counterfactual@1.0.0"
    assert radar["counterfactual"] is False


def test_channel_sensor_exposes_noncausal_regime_correlation() -> None:
    client = TestClient(create_app(Settings()))
    details = client.get("/v1/system/capabilities").json()["channel_sensor_details"]
    assert details["persistent"] is True
    assert details["regime_correlation"] is True
    assert details["regime_correlation_detector"] == "channel-regime-correlation@1.0.0"
    assert details["business_correlation"] is True
    assert details["causal_claim"] is False


def test_iad_capability_is_implemented_but_not_falsely_production_calibrated() -> None:
    client = TestClient(create_app(Settings()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["distribution_anomaly_index"] is True
    assert radar["distribution_anomaly_index_version"] == "distribution-anomaly-index@1.0.0"
    assert radar["iad_calibrator_version"] == "iad-calibrator@1.0.0"
    assert radar["iad_requires_versioned_calibration"] is True
    assert radar["iad_runtime_profile_configured"] is False
    assert radar["iad_production_calibrated"] is False
    assert radar["iad_calibration_version"] is None
    assert radar["iad_causal_claim"] is False


def test_iad_capability_reports_only_runtime_trusted_profile_as_calibrated() -> None:
    client = TestClient(create_app(Settings(), iad_profile=_approved_iad_profile()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["iad_runtime_profile_configured"] is True
    assert radar["iad_production_calibrated"] is True
    assert radar["iad_calibration_version"] == "historical-fixture-v1"
    assert radar["iad_causal_claim"] is False
