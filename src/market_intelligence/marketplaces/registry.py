from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel,ConfigDict
class MarketplaceConnectionState(StrEnum):
    CONNECTED_READ_ONLY="connected_read_only"
    READY_FOR_CREDENTIALS="ready_for_credentials"
    PLANNED="planned"
    BLOCKED_EXTERNAL_AUTH="blocked_external_auth"
class MarketplaceDescriptor(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    marketplace:str; adapter:str; state:MarketplaceConnectionState; read_only:bool=True; continuous_sensor_target:bool=True; credential_required:bool=True; notes:str=""
def default_marketplace_registry()->tuple[MarketplaceDescriptor,...]:
    return (
        MarketplaceDescriptor(marketplace="mercadolivre",adapter="MercadoLivreReadOnlyAdapter",state=MarketplaceConnectionState.CONNECTED_READ_ONLY,notes="first active marketplace; permanent writes disabled"),
        MarketplaceDescriptor(marketplace="shopee",adapter="ShopeeReadOnlyAdapter",state=MarketplaceConnectionState.BLOCKED_EXTERNAL_AUTH,notes="real collection requires official Shopee Open Platform credentials/authorization"),
        MarketplaceDescriptor(marketplace="amazon",adapter="AmazonSellingPartnerReadOnlyAdapter",state=MarketplaceConnectionState.READY_FOR_CREDENTIALS),
        MarketplaceDescriptor(marketplace="tiktok_shop",adapter="TikTokShopReadOnlyAdapter",state=MarketplaceConnectionState.READY_FOR_CREDENTIALS),
        MarketplaceDescriptor(marketplace="shein",adapter="SheinReadOnlyAdapter",state=MarketplaceConnectionState.READY_FOR_CREDENTIALS),
        MarketplaceDescriptor(marketplace="magalu",adapter="MagaluReadOnlyAdapter",state=MarketplaceConnectionState.PLANNED),
        MarketplaceDescriptor(marketplace="aliexpress",adapter="AliExpressReadOnlyAdapter",state=MarketplaceConnectionState.PLANNED),
        MarketplaceDescriptor(marketplace="ebay",adapter="EbayReadOnlyAdapter",state=MarketplaceConnectionState.PLANNED),
        MarketplaceDescriptor(marketplace="walmart",adapter="WalmartReadOnlyAdapter",state=MarketplaceConnectionState.PLANNED),
    )
