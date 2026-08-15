from __future__ import annotations

from datetime import UTC, datetime

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.skills.evidence_feed import ValidatedMarketplaceEvidence
from market_intelligence.skills.executor import execute_validated_evidence


def test_validated_evidence_can_flow_radar_then_skills_without_marketplace_io() -> None:
    observation = RadarObservation(
        entity_id="MLB-SMOKE",
        observed_at=datetime.now(UTC),
        metrics={"available_quantity": 0.0},
        history={"available_quantity": [12.0, 11.0, 10.0, 9.0, 8.0]},
        context={"validated_evidence": True, "proof_id": "smoke-proof"},
    )
    finding = build_default_radar().evaluate(observation)
    assert finding.entity_id == "MLB-SMOKE"

    evidence = ValidatedMarketplaceEvidence(
        marketplace="mercadolivre",
        entity_type="listing",
        entity_id="MLB-SMOKE",
        observed_at=observation.observed_at,
        statement="official GET and webhook validated the observed state",
        source="official_api_get_plus_webhook",
        evidence={
            "classification": "FATO",
            "webhook_validated": True,
            "official_get_validated": True,
            "proof_id": "smoke-proof",
        },
    )
    insights = execute_validated_evidence(evidence)
    assert insights
    assert all(item.entity_id == finding.entity_id for item in insights)
