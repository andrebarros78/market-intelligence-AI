from __future__ import annotations

import json
from pathlib import Path


def test_radar_sovereign_runtime_policy_is_permanent_and_read_only() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / "config" / "radar-runtime-policy.json").read_text(encoding="utf-8"))

    assert policy["classification"] == "sovereign_core"
    assert policy["architecture_scope"] == "universal_multimarketplace"
    assert policy["first_active_marketplace"] == "mercadolivre"
    assert {"mercadolivre", "amazon", "shopee", "tiktok_shop", "shein"}.issubset(
        set(policy["target_marketplaces"])
    )
    assert policy["lifecycle"] == "always_on"
    assert policy["availability_target"] == "24x7_continuous"
    assert policy["operational_horizon_years"] >= 5000
    assert policy["normal_expiration_allowed"] is False
    assert policy["operator_disable_allowed"] is False
    assert policy["automatic_shutdown_allowed"] is False
    assert policy["restart_policy"] == "always"
    assert policy["watchdog_required"] is True
    assert policy["self_recovery_required"] is True
    assert policy["startup_required"] is True
    assert policy["observation_scope"]["continuous_collection"] is True
    assert policy["observation_scope"]["continuous_investigation"] is True
    assert policy["observation_scope"]["mode"] == "all_authorized_observable_signals"
    assert policy["observation_scope"]["include_declared_signals"] is True
    assert policy["observation_scope"]["include_undeclared_but_observable_signals"] is True
    assert policy["observation_scope"]["include_derived_signals"] is True
    assert policy["observation_scope"]["include_absence_and_silence_signals"] is True
    assert policy["observation_scope"]["include_cross_signal_correlations"] is True
    assert policy["observation_scope"]["include_behavioral_drift"] is True
    assert policy["observation_scope"]["continuous_observation"] is True
    assert policy["observation_scope"]["secret_or_unauthorized_access"] is False
    assert policy["read_only_marketplace_policy"] == {
        "MI_READ_ONLY": True,
        "MI_ALLOW_MARKETPLACE_WRITES": False,
    }
    assert policy["llm_dependency"]["runtime_requires_llm"] is False
    assert policy["llm_dependency"]["radar_continues_if_llm_unavailable"] is True
