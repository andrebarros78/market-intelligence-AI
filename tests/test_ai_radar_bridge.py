from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from market_intelligence.ai.providers import ProviderConfigurationError
from market_intelligence.ai.radar_bridge import (
    RADAR_AI_BRIDGE_VERSION,
    RADAR_AI_PURPOSE,
    radar_finding_to_ai_data,
    start_radar_ai_explanation,
)
from market_intelligence.ai.temporal_queue import build_minimized_ai_job
from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import (
    DetectorResult,
    RadarFinding,
    RadarObservation,
)


def _observation() -> RadarObservation:
    return RadarObservation(
        entity_id="MLB-REAL-123456789",
        observed_at=datetime(2026, 8, 14, 15, 0, tzinfo=UTC),
        metrics={"visits": 20.0, "conversion": 0.02},
        history={"visits": [100.0, 110.0, 90.0], "conversion": [0.02, 0.021, 0.019]},
        context={
            "buyer_email": "person@example.com",
            "authorization": "Bearer must-never-leave",
            "raw_marketplace_payload": {"secret": "blocked"},
        },
    )


def _finding(*, hypothesis: bool = False) -> RadarFinding:
    results = [
        DetectorResult(
            detector="temporal-pattern@1.0.0",
            score=0.82,
            level=EvidenceLevel.INFERENCE,
            summary="internal summary not exported",
        )
    ]
    if hypothesis:
        results.append(
            DetectorResult(
                detector="regime-change@1.0.0",
                score=0.74,
                level=EvidenceLevel.HYPOTHESIS,
                summary="unconfirmed internal hypothesis",
            )
        )
    return RadarFinding(
        entity_id="MLB-REAL-123456789",
        score=0.88,
        anomalous=True,
        detector_results=results,
    )


def test_bridge_excludes_raw_entity_context_and_detector_summaries() -> None:
    observation = _observation()
    data = radar_finding_to_ai_data(finding=_finding(), observation=observation)

    rendered = repr(data).lower()
    assert data["entity_alias"].startswith("entity-")
    assert data["entity_alias"] != observation.entity_id
    assert data["entity_type"] == "marketplace_entity"
    assert data["observed_change"] == "anomaly_detected"
    assert data["evidence_class"] == "INFERENCIA"
    assert data["severity"] == "critical"
    assert data["detector_version"] == RADAR_AI_BRIDGE_VERSION
    assert data["metric_name"] == "visits"
    assert data["observed_value"] == 20.0
    assert data["expected_value"] == 100.0
    assert data["deviation_percent"] == -80.0
    assert data["sample_size"] == 3

    assert "mlb-real-123456789" not in rendered
    assert "person@example.com" not in rendered
    assert "bearer" not in rendered
    assert "raw_marketplace_payload" not in rendered
    assert "internal summary" not in rendered


def test_bridge_preserves_conservative_epistemic_classification() -> None:
    data = radar_finding_to_ai_data(finding=_finding(hypothesis=True), observation=_observation())

    assert data["evidence_class"] == "HIPOTESE"
    assert data["hypotheses"] == ["regime-change@1.0.0"]
    assert data["observable_causes"] == ["temporal-pattern@1.0.0"]


def test_bridge_output_is_accepted_by_mandatory_gateway_before_temporal() -> None:
    observation = _observation()
    data = radar_finding_to_ai_data(finding=_finding(), observation=observation)
    job = build_minimized_ai_job(
        request_id="radar-case-001",
        role="system",
        purpose=RADAR_AI_PURPOSE,
        data=data,
    )

    assert job["mode"] == "minimized"
    assert job["role"] == "system"
    gateway = job["gateway_result"]
    assert gateway["purpose"] == RADAR_AI_PURPOSE
    assert gateway["credential_exposed"] is False
    assert gateway["pii_exposed"] is False
    assert gateway["business_data_minimized"] is True
    assert "MLB-REAL-123456789" not in repr(gateway)


def test_bridge_rejects_entity_mismatch() -> None:
    finding = _finding().model_copy(update={"entity_id": "another-entity"})
    with pytest.raises(ProviderConfigurationError, match="radar_ai_entity_mismatch"):
        radar_finding_to_ai_data(finding=finding, observation=_observation())


@pytest.mark.asyncio
async def test_dispatch_uses_only_ia07_minimized_starter_contract() -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    async def fake_starter(client: object, **kwargs: Any) -> object:
        captured["client"] = client
        captured.update(kwargs)
        return sentinel

    client = object()
    result = await start_radar_ai_explanation(
        client,  # type: ignore[arg-type]
        request_id="radar-case-002",
        finding=_finding(),
        observation=_observation(),
        starter=fake_starter,  # type: ignore[arg-type]
    )

    assert result is sentinel
    assert captured["client"] is client
    assert captured["request_id"] == "radar-case-002"
    assert captured["role"] == "system"
    assert captured["purpose"] == RADAR_AI_PURPOSE
    assert "prompt" not in captured
    assert "MLB-REAL-123456789" not in repr(captured["data"])
