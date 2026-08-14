from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CanonicalEntityType(StrEnum):
    ACCOUNT = "account"
    SELLER = "seller"
    STORE = "store"
    PRODUCT = "product"
    SKU = "sku"
    VARIANT = "variant"
    OFFER = "offer"
    CATALOG_ITEM = "catalog_item"
    CATEGORY = "category"
    PRICE = "price"
    FEE = "fee"
    PROMOTION = "promotion"
    INVENTORY = "inventory"
    ORDER = "order"
    SHIPMENT = "shipment"
    RETURN = "return"
    REFUND = "refund"
    CLAIM = "claim"
    REVIEW = "review"
    AD_CAMPAIGN = "ad_campaign"
    AD_METRIC = "ad_metric"
    SEARCH_KEYWORD = "search_keyword"
    RANKING = "ranking"
    COMPETITOR_OFFER = "competitor_offer"
    METRIC = "metric"
    EVENT = "event"
    EVIDENCE = "evidence"
    ALERT = "alert"
    RECOMMENDATION = "recommendation"


class EvidencePlane(StrEnum):
    OPERATIONAL = "operational"
    MARKET = "market"


class EvidenceKind(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class CanonicalEntityRef(BaseModel):
    """Provider-neutral reference used by the intelligence core."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    marketplace: str = Field(min_length=1)
    entity_type: CanonicalEntityType
    external_id: str = Field(min_length=1)
    account_id: str | None = None
    seller_id: str | None = None


class CanonicalObservation(BaseModel):
    """Evidence envelope crossing from an adapter into the core."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: CanonicalEntityRef
    plane: EvidencePlane
    kind: EvidenceKind = EvidenceKind.FACT
    source: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)
    payload_hash: str = Field(min_length=64, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


CANONICAL_MODEL_VERSION = "1.0"
