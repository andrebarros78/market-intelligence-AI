from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SovereignIntelligenceCoreIdentity:
    unit_id: str = "sovereign-market-intelligence-core"
    classification: str = "sovereign_intelligence_counterintelligence_core"
    runtime_scope: str = "universal_multimarketplace"
    lifecycle: str = "always_on"
    operational_horizon_years: int = 5000
    radar_is_subsystem: bool = True
    llm_required: bool = False
    marketplace_write_capability: bool = False
    direct_external_action_capability: bool = False


SOVEREIGN_INTELLIGENCE_CORE_IDENTITY = SovereignIntelligenceCoreIdentity()
