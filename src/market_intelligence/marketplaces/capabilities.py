from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MarketplaceCapability(StrEnum):
    PRODUCT_SEARCH = "product_search"
    PRODUCT_READ = "product_read"
    OFFER_READ = "offer_read"
    PRICE_READ = "price_read"
    INVENTORY_READ = "inventory_read"
    ORDER_READ = "order_read"
    FULFILLMENT_READ = "fulfillment_read"
    REVIEW_READ = "review_read"
    ADS_METRICS_READ = "ads_metrics_read"
    COMPETITOR_PRICE_READ = "competitor_price_read"
    NOTIFICATIONS = "notifications"
    OAUTH = "oauth"
    WRITE_PRICE = "write_price"
    WRITE_INVENTORY = "write_inventory"
    WRITE_ADS = "write_ads"


class CapabilityAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


class CapabilityDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: MarketplaceCapability
    availability: CapabilityAvailability
    source: str = Field(min_length=1)
    freshness_seconds: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class MarketplaceCapabilityRegistry:
    """Fail-closed registry. Unknown and write capabilities never become allowed implicitly."""

    def __init__(self) -> None:
        self._items: dict[str, dict[MarketplaceCapability, CapabilityDeclaration]] = {}

    @staticmethod
    def _key(marketplace: str) -> str:
        value = marketplace.strip().lower()
        if not value:
            raise ValueError("marketplace_required")
        return value

    def register(self, marketplace: str, declarations: list[CapabilityDeclaration]) -> None:
        key = self._key(marketplace)
        self._items[key] = {item.capability: item for item in declarations}

    def get(self, marketplace: str, capability: MarketplaceCapability) -> CapabilityDeclaration:
        key = self._key(marketplace)
        declared = self._items.get(key, {}).get(capability)
        if declared is not None:
            return declared
        return CapabilityDeclaration(
            capability=capability,
            availability=CapabilityAvailability.UNKNOWN,
            source="registry:undeclared",
            confidence=0.0,
        )

    def is_read_allowed(self, marketplace: str, capability: MarketplaceCapability) -> bool:
        if capability.value.startswith("write_"):
            return False
        return self.get(marketplace, capability).availability is CapabilityAvailability.AVAILABLE

    def is_write_allowed(self, marketplace: str, capability: MarketplaceCapability) -> bool:
        # Global architectural gate: current project remains read-only/fail-closed.
        _ = marketplace, capability
        return False


CAPABILITY_REGISTRY = MarketplaceCapabilityRegistry()
