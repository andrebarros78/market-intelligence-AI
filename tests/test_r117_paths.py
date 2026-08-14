import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


VISITS_HISTORY = [
    100, 101, 99, 100, 102, 98, 101, 99, 100, 100, 101, 99,
    100, 102, 98, 101, 99, 100, 101, 100, 99, 102, 98, 100,
]
CONVERSION_HISTORY = [
    0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101, 0.099,
    0.100, 0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101,
    0.099, 0.100, 0.101, 0.100, 0.099, 0.102, 0.098, 0.100,
]


def _trusted_profile() -> dict:
    return {
        "version": "historical-runtime-fixture-v1",
        "source_type": "historical_validation",
        "detector_weights": {"ecod": 0.5, "iforest": 0.5},
        "threshold": 0.80,
        "feature_names": ["visits", "conversion"],
        "min_history": 12,
        "production_approved": True,
        "sample_count": 20,
        "positive_count": 10,
        "negative_count": 10,
        "metrics": {
            "balanced_accuracy": 0.90,
            "sensitivity": 0.90,
            "specificity": 0.90,
        },
        "detector_metrics": {
            "ecod": {"balanced_accuracy": 0.90},
            "iforest": {"balanced_accuracy": 0.90},
        },
    }


def _payload(*, experimental: bool = False, malicious_profile: bool = False) -> dict:
    context: dict = {}
    if experimental:
        context["pyod_experimental"] = True
    if malicious_profile:
        context["pyod_profile"] = _trusted_profile()
    return RadarObservation(
        entity_id="R117-PATH",
        observed_at=datetime.now(UTC),
        metrics={"visits": 180, "conversion": 0.35},
        history={
            "visits": VISITS_HISTORY,
            "conversion": CONVERSION_HISTORY,
        },
        context=context,
    ).model_dump(mode="json")


def _pyod(results: list[dict]) -> dict:
    return next(item for item in results if item["detector"] == "pyod_ensemble_v1")


def test_capabilities_expose_pyod_without_false_production_promotion() -> None:
    radar = TestClient(create_app(Settings())).get("/v1/system/capabilities").json()["radar"]
    assert radar["pyod_ensemble"] is True
    assert radar["pyod_library_version"] == "3.6.2"
    assert radar["pyod_ensemble_detector"] == "pyod-ensemble@1.0.0"
    assert radar["pyod_benchmark_engine"] == "pyod-benchmark@1.0.0"
    assert radar["pyod_candidate_detectors"] == ["ecod", "iforest", "knn"]
    assert radar["pyod_request_can_promote"] is False
    assert radar["pyod_runtime_profile_configured"] is False
    assert radar["pyod_production_promoted"] is False
    assert radar["pyod_profile_version"] is None
    assert radar["pyod_causal_claim"] is False


def test_capabilities_report_trusted_runtime_profile() -> None:
    radar = TestClient(
        create_app(Settings(), pyod_profile=_trusted_profile())
    ).get("/v1/system/capabilities").json()["radar"]
    assert radar["pyod_runtime_profile_configured"] is True
    assert radar["pyod_production_promoted"] is True
    assert radar["pyod_profile_version"] == "historical-runtime-fixture-v1"


def test_http_experimental_path_cannot_self_promote_with_payload_profile() -> None:
    response = TestClient(create_app(Settings())).post(
        "/v1/radar/evaluate",
        json=_payload(experimental=True, malicious_profile=True),
    )
    assert response.status_code == 200
    result = _pyod(response.json()["detector_results"])
    assert result["level"] == "hypothesis"
    assert result["score"] < 0.60
    assert result["attributes"]["trust_boundary"] == "request_experimental"
    assert result["attributes"]["production_approved"] is False
    assert result["attributes"]["ensemble_threshold"] is None
    assert result["attributes"]["ensemble_decision"] is False
    assert result["attributes"]["alert_eligible"] is False


def test_http_trusted_runtime_profile_can_promote_benchmarked_pyod() -> None:
    response = TestClient(
        create_app(Settings(), pyod_profile=_trusted_profile())
    ).post("/v1/radar/evaluate", json=_payload())
    assert response.status_code == 200
    result = _pyod(response.json()["detector_results"])
    assert result["level"] == "inference"
    assert result["attributes"]["trust_boundary"] == "trusted_runtime"
    assert result["attributes"]["profile_version"] == "historical-runtime-fixture-v1"
    assert result["attributes"]["ensemble_decision"] is True
    assert result["attributes"]["alert_eligible"] is True
    assert result["attributes"]["causal_claim"] is False


def test_radar_activity_preserves_trusted_pyod_evidence() -> None:
    finding = asyncio.run(
        RadarActivities(build_default_radar(pyod_profile=_trusted_profile())).evaluate(_payload())
    )
    result = _pyod(finding["detector_results"])
    assert result["attributes"]["trust_boundary"] == "trusted_runtime"
    assert result["attributes"]["ensemble_decision"] is True
    assert result["attributes"]["alert_eligible"] is True
    assert result["attributes"]["pyod_library_version"] == "3.6.2"
