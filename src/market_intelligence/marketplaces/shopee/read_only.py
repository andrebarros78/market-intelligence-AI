from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from market_intelligence.ingestion.events import RawEvent
from market_intelligence.marketplaces.base import MarketplaceReadError
@dataclass(frozen=True,slots=True)
class ShopeeAuthorizationState:
    partner_id_configured:bool; partner_key_configured:bool; shop_id_configured:bool; access_token_configured:bool
    @property
    def ready(self)->bool:return all((self.partner_id_configured,self.partner_key_configured,self.shop_id_configured,self.access_token_configured))
class ShopeeReadOnlyAdapter:
    name="shopee"
    def __init__(self,authorization:ShopeeAuthorizationState|None=None)->None:self.authorization=authorization or ShopeeAuthorizationState(False,False,False,False)
    async def fetch_resource(self,resource:str)->dict[str,Any]:
        del resource
        if not self.authorization.ready:raise MarketplaceReadError("shopee_external_authorization_required",retryable=False)
        raise MarketplaceReadError("shopee_request_signing_not_yet_validated",retryable=False)
    def normalize_notification(self,payload:dict[str,Any])->RawEvent:
        del payload
        raise MarketplaceReadError("shopee_webhook_contract_not_yet_validated",retryable=False)
