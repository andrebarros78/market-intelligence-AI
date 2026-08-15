import pytest
from market_intelligence.marketplaces.base import MarketplaceReadError
from market_intelligence.marketplaces.registry import MarketplaceConnectionState,default_marketplace_registry
from market_intelligence.marketplaces.shopee import ShopeeReadOnlyAdapter
@pytest.mark.asyncio
async def test_shopee_fails_closed_without_external_authorization():
    adapter=ShopeeReadOnlyAdapter()
    with pytest.raises(MarketplaceReadError,match="shopee_external_authorization_required"):
        await adapter.fetch_resource("/product")
def test_registry_has_ml_active_and_shopee_external_gate():
    rows={x.marketplace:x for x in default_marketplace_registry()}
    assert rows["mercadolivre"].state is MarketplaceConnectionState.CONNECTED_READ_ONLY
    assert rows["mercadolivre"].read_only is True
    assert rows["shopee"].state is MarketplaceConnectionState.BLOCKED_EXTERNAL_AUTH
    assert all(x.read_only for x in rows.values())
