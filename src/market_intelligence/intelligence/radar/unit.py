from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from market_intelligence.intelligence.radar.runtime import run_cycle, run_forever


@dataclass(frozen=True, slots=True)
class RadarSovereignIdentity:
    unit_id: str = "radar-universal-sovereign"
    classification: str = "sovereign_universal_unit"
    runtime_scope: str = "universal_multimarketplace"
    lifecycle: str = "always_on"
    operational_horizon_years: int = 5000
    llm_required: bool = False
    marketplace_write_capability: bool = False


RADAR_SOVEREIGN_IDENTITY = RadarSovereignIdentity()


async def run_unit_cycle(database_url: str) -> dict[str, object]:
    status = await run_cycle(database_url)
    status.update(
        {
            "unit_id": RADAR_SOVEREIGN_IDENTITY.unit_id,
            "unit_classification": RADAR_SOVEREIGN_IDENTITY.classification,
            "runtime_scope": RADAR_SOVEREIGN_IDENTITY.runtime_scope,
            "lifecycle": RADAR_SOVEREIGN_IDENTITY.lifecycle,
            "operational_horizon_years": RADAR_SOVEREIGN_IDENTITY.operational_horizon_years,
            "llm_required": RADAR_SOVEREIGN_IDENTITY.llm_required,
            "marketplace_write_capability": RADAR_SOVEREIGN_IDENTITY.marketplace_write_capability,
        }
    )
    return status


async def run_unit_forever(
    database_url: str,
    *,
    status_path: Path,
    interval_seconds: float = 30.0,
) -> None:
    await run_forever(
        database_url,
        status_path=status_path,
        interval_seconds=interval_seconds,
        status_enricher=lambda status: {
            **status,
            "unit_id": RADAR_SOVEREIGN_IDENTITY.unit_id,
            "unit_classification": RADAR_SOVEREIGN_IDENTITY.classification,
            "runtime_scope": RADAR_SOVEREIGN_IDENTITY.runtime_scope,
            "lifecycle": RADAR_SOVEREIGN_IDENTITY.lifecycle,
            "operational_horizon_years": RADAR_SOVEREIGN_IDENTITY.operational_horizon_years,
            "llm_required": RADAR_SOVEREIGN_IDENTITY.llm_required,
            "marketplace_write_capability": RADAR_SOVEREIGN_IDENTITY.marketplace_write_capability,
        },
    )
