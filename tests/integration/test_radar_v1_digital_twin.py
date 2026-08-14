from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from market_intelligence.digital_twin import (
    SANDBOX_FALSE_POSITIVE_THRESHOLD,
    run_radar_v1_digital_twin,
)


@pytest.mark.postgres
def test_radar_v1_digital_twin_satisfies_all_sandbox_acceptance_criteria() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        report = await run_radar_v1_digital_twin(
            url,
            run_id=f"pytest-{uuid4().hex[:10]}",
        )
        assert report.synthetic_only is True
        assert report.sandbox_passed is True
        assert report.production_ready is False
        assert report.authorized_real_read_required is True
        assert report.real_historical_false_positive_homologation_required is True
        assert report.sandbox_false_positive_rate <= SANDBOX_FALSE_POSITIVE_THRESHOLD

        checks = {item.criterion: item for item in report.checks}
        required = {
            "event_snapshot_ingestion",
            "known_rule_detection",
            "unknown_anomaly_detection",
            "regime_shift_detection",
            "control_comparison",
            "unexplained_residual",
            "sanitized_channel_correlation",
            "sanitized_channel_telemetry_persistence",
            "epistemic_separation",
            "complete_alert_contract",
            "complete_alert_persistence",
            "business_impact_prioritization",
            "restart_without_history_loss",
            "sandbox_false_positive_threshold",
            "reproducible_evidence",
        }
        assert required <= set(checks)
        assert all(checks[name].passed for name in required)

    asyncio.run(scenario())
