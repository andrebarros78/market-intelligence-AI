from market_intelligence.intelligence.radar.runtime import EXPECTED_ALEMBIC_HEAD
from market_intelligence.intelligence.radar.unit import RADAR_SOVEREIGN_IDENTITY


def test_radar_is_sovereign_universal_unit_not_worker() -> None:
    identity = RADAR_SOVEREIGN_IDENTITY
    assert identity.unit_id == "radar-universal-sovereign"
    assert identity.classification == "sovereign_universal_unit"
    assert identity.runtime_scope == "universal_multimarketplace"
    assert identity.lifecycle == "always_on"
    assert identity.operational_horizon_years == 5000
    assert identity.llm_required is False
    assert identity.marketplace_write_capability is False


def test_radar_runtime_requires_sovereign_learning_schema() -> None:
    assert EXPECTED_ALEMBIC_HEAD == '0008_sovereign_learning'
