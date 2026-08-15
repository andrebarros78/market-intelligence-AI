from __future__ import annotations
from pydantic import BaseModel,ConfigDict,Field
from market_intelligence.marketplaces.entity_resolution import ProductIdentity,ResolutionStatus,resolve_product_identity
class MarketplaceMetrics(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    marketplace:str; price:float|None=None; available_quantity:float|None=None; sold_quantity:float|None=None; visits:float|None=None
class CrossMarketplaceCorrelation(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    same_product:bool; resolution_status:ResolutionStatus; confidence:float=Field(ge=0,le=1); price_delta:float|None=None; availability_delta:float|None=None; sales_velocity_signal:str|None=None; fact_eligible:bool=False; reason:str
def correlate_marketplaces(a:ProductIdentity,b:ProductIdentity,am:MarketplaceMetrics,bm:MarketplaceMetrics)->CrossMarketplaceCorrelation:
    r=resolve_product_identity(a,b)
    if not r.same_product:return CrossMarketplaceCorrelation(same_product=False,resolution_status=r.status,confidence=r.confidence,reason=r.reason)
    pd=(bm.price-am.price) if am.price is not None and bm.price is not None else None
    ad=(bm.available_quantity-am.available_quantity) if am.available_quantity is not None and bm.available_quantity is not None else None
    vel=None
    if am.sold_quantity is not None and bm.sold_quantity is not None:
        vel=f"{am.marketplace}_higher_sales_signal" if am.sold_quantity>bm.sold_quantity else f"{bm.marketplace}_higher_sales_signal" if bm.sold_quantity>am.sold_quantity else "sales_signal_equal"
    return CrossMarketplaceCorrelation(same_product=True,resolution_status=r.status,confidence=r.confidence,price_delta=pd,availability_delta=ad,sales_velocity_signal=vel,fact_eligible=r.status in {ResolutionStatus.EXACT,ResolutionStatus.STRONG},reason=r.reason)
