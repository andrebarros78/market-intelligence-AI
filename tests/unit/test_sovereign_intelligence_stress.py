from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.sovereign.core import SovereignIntelligenceCore
from market_intelligence.intelligence.sovereign.models import SignalEnvelope


KINDS = ("snapshot_item", "price_suggestion", "item_competition", "catalog_suggestion", "question_created", "order", "claim", "shipment")


def _signal(index: int, kind: str, *, offset: int = 0) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=f"{kind}-{index}-{offset}", marketplace="mercadolivre", entity_type="item",
        entity_id=f"MLB{index % 97}", kind=kind, source="stress_official_read",
        observed_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC) + timedelta(seconds=index + offset),
        payload={"price": float(100 + (index % 13)), "available_quantity": int(1 + (index % 25)), "sold_quantity": int(index % 7)},
        provenance={"source": "synthetic_stress", "case": index}, official_resource_fetched=True,
        confidence=0.55 + ((index % 40) / 100.0),
    )


def test_sovereign_intelligence_core_stress_12000_zero_marketplace_writes() -> None:
    core = SovereignIntelligenceCore()
    failures = unsafe = marketplace_writes = 0
    for index in range(12000):
        kind = KINDS[index % len(KINDS)]
        current = _signal(index, kind)
        history = (_signal(index, kind, offset=-120), _signal(index, kind, offset=-60))
        investigation = None
        if index % 5 == 0:
            investigation = {
                "finding_hash": f"{index:064x}"[-64:], "status_after": "confirmed",
                "confidence_after": 0.88, "observation_count": 3,
                "evidence_summary": {"stress": True, "index": index}, "hypotheses": [], "causal_claim": False,
            }
        try:
            report = core.process(current, history=history, investigation=investigation)
            marketplace_writes += report.marketplace_writes
            unsafe += int(report.action_intent.direct_marketplace_write)
            unsafe += int(report.audit.unsafe_authority_detected)
        except Exception:
            failures += 1
    assert failures == 0
    assert unsafe == 0
    assert marketplace_writes == 0
