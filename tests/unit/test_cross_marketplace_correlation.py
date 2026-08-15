from market_intelligence.correlation import MarketplaceMetrics,correlate_marketplaces
from market_intelligence.marketplaces.entity_resolution import ProductIdentity,ResolutionStatus
def test_matching_gtin_allows_fact_eligible_correlation():
    a=ProductIdentity(marketplace="mercadolivre",external_id="MLB1",gtin="7891234567890")
    b=ProductIdentity(marketplace="shopee",external_id="S1",gtin="7891234567890")
    result=correlate_marketplaces(a,b,MarketplaceMetrics(marketplace="mercadolivre",price=100,available_quantity=5,sold_quantity=10),MarketplaceMetrics(marketplace="shopee",price=110,available_quantity=8,sold_quantity=7))
    assert result.same_product is True
    assert result.resolution_status is ResolutionStatus.STRONG
    assert result.fact_eligible is True
    assert result.price_delta==10
    assert result.availability_delta==3
def test_unresolved_identity_never_becomes_cross_market_fact():
    a=ProductIdentity(marketplace="mercadolivre",external_id="MLB1",brand="A")
    b=ProductIdentity(marketplace="shopee",external_id="S1",brand="A")
    result=correlate_marketplaces(a,b,MarketplaceMetrics(marketplace="mercadolivre"),MarketplaceMetrics(marketplace="shopee"))
    assert result.same_product is False
    assert result.fact_eligible is False
