from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ResolutionStatus(StrEnum):
    EXACT = "exact"
    STRONG = "strong"
    CONFLICT = "conflict"
    UNRESOLVED = "unresolved"


class ProductIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    marketplace: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    gtin: str | None = None
    brand: str | None = None
    mpn: str | None = None
    model: str | None = None


class EntityResolutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ResolutionStatus
    same_product: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().lower().split())
    return normalized or None


def resolve_product_identity(left: ProductIdentity, right: ProductIdentity) -> EntityResolutionResult:
    """Resolve only with deterministic strong evidence; never let fuzzy similarity become fact."""

    if _norm(left.marketplace) == _norm(right.marketplace) and left.external_id == right.external_id:
        return EntityResolutionResult(
            status=ResolutionStatus.EXACT,
            same_product=True,
            reason="same_marketplace_external_id",
            confidence=1.0,
        )

    left_gtin = _norm(left.gtin)
    right_gtin = _norm(right.gtin)
    if left_gtin and right_gtin:
        if left_gtin == right_gtin:
            return EntityResolutionResult(
                status=ResolutionStatus.STRONG,
                same_product=True,
                reason="matching_gtin",
                confidence=0.99,
            )
        return EntityResolutionResult(
            status=ResolutionStatus.CONFLICT,
            same_product=False,
            reason="conflicting_gtin",
            confidence=0.99,
        )

    left_brand, right_brand = _norm(left.brand), _norm(right.brand)
    left_mpn, right_mpn = _norm(left.mpn), _norm(right.mpn)
    if left_brand and right_brand and left_mpn and right_mpn:
        if left_brand == right_brand and left_mpn == right_mpn:
            return EntityResolutionResult(
                status=ResolutionStatus.STRONG,
                same_product=True,
                reason="matching_brand_mpn",
                confidence=0.95,
            )
        if left_mpn != right_mpn:
            return EntityResolutionResult(
                status=ResolutionStatus.CONFLICT,
                same_product=False,
                reason="conflicting_mpn",
                confidence=0.9,
            )

    return EntityResolutionResult(
        status=ResolutionStatus.UNRESOLVED,
        same_product=False,
        reason="insufficient_strong_identifiers",
        confidence=0.0,
    )
