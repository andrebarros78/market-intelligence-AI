from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable

from market_intelligence.marketplaces.mercadolivre.http_client import (
    MercadoLivreReadError,
    MercadoLivreReadOnlyAdapter,
    MercadoLivreReadResult,
)
from market_intelligence.marketplaces.mercadolivre.schema import (
    SchemaBaselineRegistry,
    SchemaDrift,
)


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CapabilityTargets:
    listing_id: str | None = None
    order_id: str | None = None
    shipment_id: str | None = None
    visits_item_id: str | None = None
    catalog_item_id: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityProbe:
    capability: str
    state: CapabilityState
    status_code: int | None = None
    partial: bool = False
    missing_fields: tuple[str, ...] = ()
    schema_fingerprint: str | None = None
    schema_drift: SchemaDrift | None = None
    reason: str | None = None


class MercadoLivreCapabilityAuditor:
    """Observes API capability only. It never infers a business/platform cause."""

    def __init__(
        self,
        adapter: MercadoLivreReadOnlyAdapter,
        *,
        schemas: SchemaBaselineRegistry | None = None,
    ) -> None:
        self._adapter = adapter
        self._schemas = schemas or SchemaBaselineRegistry()

    async def _probe(
        self,
        capability: str,
        target: str | None,
        reader: Callable[[str], Awaitable[MercadoLivreReadResult]],
    ) -> CapabilityProbe:
        if not target:
            return CapabilityProbe(
                capability=capability,
                state=CapabilityState.UNKNOWN,
                reason="target_missing",
            )
        try:
            result = await reader(target)
        except MercadoLivreReadError as exc:
            return CapabilityProbe(
                capability=capability,
                state=(CapabilityState.UNKNOWN if exc.retryable
                       else CapabilityState.UNAVAILABLE),
                status_code=exc.status_code,
                reason=exc.code,
            )
        drift = self._schemas.observe(capability, result.payload)
        degraded = result.degraded or drift.changed
        return CapabilityProbe(
            capability=capability,
            state=CapabilityState.DEGRADED if degraded else CapabilityState.AVAILABLE,
            status_code=result.telemetry.status_code,
            partial=result.degraded,
            missing_fields=result.missing_fields,
            schema_fingerprint=result.schema_fingerprint,
            schema_drift=drift,
            reason=("partial_or_schema_drift" if degraded else None),
        )

    async def audit(self, targets: CapabilityTargets) -> tuple[CapabilityProbe, ...]:
        # Sequential by design in R1.4: avoid burst behavior and false 429s.
        return (
            await self._probe("listing", targets.listing_id, self._adapter.read_listing),
            await self._probe("order", targets.order_id, self._adapter.read_order),
            await self._probe("shipment", targets.shipment_id, self._adapter.read_shipment),
            await self._probe("visits", targets.visits_item_id, self._adapter.read_visits),
            await self._probe(
                "catalog_competition",
                targets.catalog_item_id,
                self._adapter.read_catalog_competition,
            ),
        )
