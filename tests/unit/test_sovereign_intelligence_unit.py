from market_intelligence.intelligence.sovereign.unit import SOVEREIGN_INTELLIGENCE_CORE_IDENTITY


def test_sovereign_intelligence_core_is_top_level_cognitive_unit() -> None:
    identity = SOVEREIGN_INTELLIGENCE_CORE_IDENTITY
    assert identity.unit_id == "sovereign-market-intelligence-core"
    assert identity.classification == "sovereign_intelligence_counterintelligence_core"
    assert identity.runtime_scope == "universal_multimarketplace"
    assert identity.lifecycle == "always_on"
    assert identity.operational_horizon_years == 5000
    assert identity.radar_is_subsystem is True
    assert identity.llm_required is False
    assert identity.marketplace_write_capability is False
    assert identity.direct_external_action_capability is False
