from datetime import UTC, datetime

import pytest

from market_intelligence.core.contracts import (
    Alert,
    EntityRef,
    Evidence,
    EvidenceLevel,
    Severity,
)
from market_intelligence.intelligence.radar.ai_explainer import (
    build_radar_alert_ai_request,
    dispatch_radar_alert_explanation,
)


def _alert(
    *,
    level: EvidenceLevel = EvidenceLevel.INFERENCE,
    include_hypothesis: bool = False,
) -> Alert:
    observed = datetime(2026, 8, 14, 15, 0, tzinfo=UTC)
    return Alert(
        entity=EntityRef(
            marketplace="mercadolivre",
            entity_type="listing",
            entity_id="MLB-REAL-SENSITIVE-123",
        ),
        observed_change="traffic_drop_without_observed_listing_change",
        evidence=[
            Evidence(
                level=level,
                statement="Traffic fell while observable listing factors remained stable.",
                source="radar:distribution",
                observed_at=observed,
                attributes={"raw_platform_blob": {"must": "stay internal"}},
            )
        ],
        severity=Severity.HIGH,
        estimated_impact=1250.0,
        confidence=0.88,
        observable_causes=["price_stable", "stock_normal"],
        unexplained_residual=0.64,
        hypotheses=(
            ["distribution_change_requires_investigation"] if include_hypothesis else []
        ),
        control_comparison={"peer_change": -0.08, "target_change": -0.67},
        recommended_action="Compare controls and continue observing.",
        detector_version="distribution@1.0.0",
    )


def test_bridge_pseudonymizes_entity_and_preserves_epistemic_class() -> None:
    alert = _alert()
    request = build_radar_alert_ai_request(alert)

    assert request.role == "system"
    assert request.purpose == "radar_alert_explanation"
    assert request.data["evidence_class"] == "INFERENCIA"
    assert request.data["entity_alias"].startswith("entity-")
    rendered = str(request.data)
    assert "MLB-REAL-SENSITIVE-123" not in rendered
    assert "raw_platform_blob" not in rendered
    assert request.data["control_comparison"].startswith("{")


def test_bridge_request_id_is_deterministic_and_contains_no_raw_entity_id() -> None:
    first = build_radar_alert_ai_request(_alert())
    second = build_radar_alert_ai_request(_alert())

    assert first.request_id == second.request_id
    assert first.request_id.startswith("radar-alert:")
    assert "MLB-REAL-SENSITIVE-123" not in first.request_id


def test_bridge_does_not_upgrade_hypothesis() -> None:
    request = build_radar_alert_ai_request(
        _alert(level=EvidenceLevel.INFERENCE, include_hypothesis=True)
    )
    assert request.data["evidence_class"] == "HIPOTESE"
    assert request.data["hypotheses"] == ["distribution_change_requires_investigation"]


@pytest.mark.asyncio
async def test_dispatch_uses_only_minimized_temporal_path(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    async def fake_start(client, **kwargs):
        captured["client"] = client
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "market_intelligence.intelligence.radar.ai_explainer.start_minimized_ai_job",
        fake_start,
    )
    client = object()
    alert = _alert()

    result = await dispatch_radar_alert_explanation(client, alert)

    assert result is sentinel
    assert captured["client"] is client
    assert captured["role"] == "system"
    assert captured["purpose"] == "radar_alert_explanation"
    assert "MLB-REAL-SENSITIVE-123" not in str(captured["data"])
    assert "prompt" not in captured
