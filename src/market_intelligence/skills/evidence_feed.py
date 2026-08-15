from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidatedMarketplaceEvidence:
    marketplace: str
    entity_type: str
    entity_id: str
    observed_at: datetime
    statement: str
    evidence: dict[str, Any]
    source: str = "official_api_get_plus_webhook"


def build_validated_status_cycle_evidence(
    *,
    item_id: str,
    observed_at: datetime,
    before_status: str,
    paused_status: str,
    after_status: str,
    webhook_validated: bool,
    official_get_validated: bool,
    proof_id: str,
) -> ValidatedMarketplaceEvidence:
    if before_status != "active":
        raise ValueError("before_status_not_active")
    if paused_status != "paused":
        raise ValueError("pause_not_confirmed")
    if after_status != "active":
        raise ValueError("reactivation_not_confirmed")
    if not webhook_validated:
        raise ValueError("webhook_not_validated")
    if not official_get_validated:
        raise ValueError("official_get_not_validated")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at_must_be_timezone_aware")

    return ValidatedMarketplaceEvidence(
        marketplace="mercadolivre",
        entity_type="listing",
        entity_id=item_id,
        observed_at=observed_at,
        statement="Ciclo controlado active→paused→active confirmado por GET oficial e webhook real.",
        evidence={
            "proof_id": proof_id,
            "before_status": before_status,
            "paused_status": paused_status,
            "after_status": after_status,
            "webhook_validated": True,
            "official_get_validated": True,
            "classification": "FATO",
        },
    )
