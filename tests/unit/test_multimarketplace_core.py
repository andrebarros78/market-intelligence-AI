from market_intelligence.marketplaces.canonical import (
    CanonicalEntityRef,
    CanonicalEntityType,
    CanonicalObservation,
    EvidenceKind,
    EvidencePlane,
)
from market_intelligence.marketplaces.capabilities import (
    CapabilityAvailability,
    CapabilityDeclaration,
    MarketplaceCapability,
    MarketplaceCapabilityRegistry,
)
from market_intelligence.marketplaces.entity_resolution import (
    ProductIdentity,
    ResolutionStatus,
    resolve_product_identity,
)
from market_intelligence.skills.registry import (
    SkillDescriptor,
    SkillExecutionStatus,
    SkillLicenseStatus,
    SkillRegistry,
)


def test_canonical_model_is_marketplace_neutral() -> None:
    entity = CanonicalEntityRef(
        marketplace="amazon-br",
        entity_type=CanonicalEntityType.PRODUCT,
        external_id="B0-SYNTHETIC",
    )
    observation = CanonicalObservation(
        entity=entity,
        plane=EvidencePlane.MARKET,
        kind=EvidenceKind.FACT,
        source="synthetic-adapter",
        observed_at="2026-08-14T15:00:00-03:00",
        payload_hash="a" * 64,
    )
    assert observation.entity.marketplace == "amazon-br"
    assert observation.entity.entity_type is CanonicalEntityType.PRODUCT
    assert observation.kind is EvidenceKind.FACT


def test_capability_registry_fails_closed_and_blocks_writes() -> None:
    registry = MarketplaceCapabilityRegistry()
    assert not registry.is_read_allowed("shopee-br", MarketplaceCapability.PRODUCT_READ)

    registry.register(
        "shopee-br",
        [
            CapabilityDeclaration(
                capability=MarketplaceCapability.PRODUCT_READ,
                availability=CapabilityAvailability.AVAILABLE,
                source="synthetic-contract",
            ),
            CapabilityDeclaration(
                capability=MarketplaceCapability.WRITE_PRICE,
                availability=CapabilityAvailability.AVAILABLE,
                source="synthetic-contract",
            ),
        ],
    )
    assert registry.is_read_allowed("shopee-br", MarketplaceCapability.PRODUCT_READ)
    assert not registry.is_read_allowed("shopee-br", MarketplaceCapability.WRITE_PRICE)
    assert not registry.is_write_allowed("shopee-br", MarketplaceCapability.WRITE_PRICE)


def test_entity_resolution_uses_strong_identifiers_only() -> None:
    ml = ProductIdentity(marketplace="mercado-livre", external_id="MLB1", gtin="7891234567890")
    amazon = ProductIdentity(marketplace="amazon-br", external_id="ASIN1", gtin="7891234567890")
    result = resolve_product_identity(ml, amazon)
    assert result.same_product is True
    assert result.status is ResolutionStatus.STRONG
    assert result.reason == "matching_gtin"

    shopee = ProductIdentity(marketplace="shopee-br", external_id="S1", gtin="7899999999999")
    conflict = resolve_product_identity(ml, shopee)
    assert conflict.same_product is False
    assert conflict.status is ResolutionStatus.CONFLICT

    weak_left = ProductIdentity(marketplace="amazon-br", external_id="A2", brand="Acme", model="X")
    weak_right = ProductIdentity(marketplace="tiktok-shop-br", external_id="T2", brand="Acme", model="X")
    unresolved = resolve_product_identity(weak_left, weak_right)
    assert unresolved.same_product is False
    assert unresolved.status is ResolutionStatus.UNRESOLVED


def test_proprietary_or_quarantine_skill_cannot_execute() -> None:
    registry = SkillRegistry()
    registry.register(
        SkillDescriptor(
            skill_id="nexscope-reference",
            function="pricing",
            supported_marketplaces=("amazon-br",),
            license_status=SkillLicenseStatus.PROPRIETARY,
            execution_status=SkillExecutionStatus.REFERENCE_ONLY,
            source="warehouse:nexscope",
        )
    )
    assert registry.resolve(function="pricing", marketplace="amazon-br") == ()

    registry.register(
        SkillDescriptor(
            skill_id="internal-pricing",
            function="pricing",
            supported_marketplaces=("*",),
            license_status=SkillLicenseStatus.INTERNAL,
            execution_status=SkillExecutionStatus.APPROVED_ACTIVE,
            source="project",
        )
    )
    active = registry.resolve(function="pricing", marketplace="mercado-livre")
    assert [item.skill_id for item in active] == ["internal-pricing"]
