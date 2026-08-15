from __future__ import annotations
from dataclasses import dataclass
import httpx
from market_intelligence.core.windows_credentials import read_generic_credential, write_generic_credential
CLIENT_SECRET_TARGET="MarketIntelligenceAI/MercadoLivre/ClientSecret"
ACCESS_TARGET="MarketIntelligenceAI/MercadoLivre/ControlledWriteToken"
REFRESH_TARGET="MarketIntelligenceAI/MercadoLivre/ControlledWriteRefreshToken"
TOKEN_URL="https://api.mercadolibre.com/oauth/token"
APP_ID="3438551912770538"
@dataclass(frozen=True, slots=True)
class VaultTokenState:
    access_token: str
    refreshed: bool=False
def load_access_token()->str:
    token=read_generic_credential(ACCESS_TARGET)
    if not token: raise RuntimeError("mercadolivre_access_token_missing")
    return token
async def refresh_access_token()->VaultTokenState:
    refresh=read_generic_credential(REFRESH_TARGET); secret=read_generic_credential(CLIENT_SECRET_TARGET)
    if not refresh or not secret: raise RuntimeError("mercadolivre_refresh_credentials_missing")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response=await client.post(TOKEN_URL,data={"grant_type":"refresh_token","client_id":APP_ID,"client_secret":secret,"refresh_token":refresh},headers={"Accept":"application/json"})
    if response.status_code>=300: raise RuntimeError(f"mercadolivre_refresh_rejected:{response.status_code}")
    payload=response.json(); access=payload.get("access_token") if isinstance(payload,dict) else None; new_refresh=payload.get("refresh_token") if isinstance(payload,dict) else None
    if not isinstance(access,str) or not access: raise RuntimeError("mercadolivre_refresh_access_missing")
    if not isinstance(new_refresh,str) or not new_refresh: raise RuntimeError("mercadolivre_refresh_token_missing")
    write_generic_credential(ACCESS_TARGET,access); write_generic_credential(REFRESH_TARGET,new_refresh)
    return VaultTokenState(access_token=access,refreshed=True)
