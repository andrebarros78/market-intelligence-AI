from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker
from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.marketplaces.canonical import EvidenceKind
from market_intelligence.marketplaces.mercadolivre.http_client import MercadoLivreReadError,MercadoLivreReadOnlyAdapter,MercadoLivreReadResult
from market_intelligence.marketplaces.mercadolivre.read_sanitize import safe_claims,safe_item,safe_items_search,safe_orders_search,safe_questions,safe_user
from market_intelligence.marketplaces.mercadolivre.vault_token import load_access_token,refresh_access_token
from market_intelligence.persistence.postgresql import PostgresChannelEventRepository,PostgresEntityRepository,PostgresRawEventRepository,PostgresSnapshotRepository
from market_intelligence.sensors import SensorEntity,SensorSignal,SensorSignalKind,UniversalSensorBus
@dataclass(frozen=True,slots=True)
class MercadoLivreCollectionReport:
    success:bool; account_id:str|None; items_seen:int; item_snapshots:int; order_snapshots:int; questions_seen:int; claims_seen:int; channel_events:int; errors:tuple[str,...]; token_refreshed:bool
def _channel_event(result:MercadoLivreReadResult)->ChannelEvent:
    t=result.telemetry
    return ChannelEvent(marketplace="mercadolivre",direction="outbound",operation=t.endpoint,observed_at=t.observed_at,status_code=t.status_code,latency_ms=t.latency_ms,attempt=t.attempts,request_id=t.request_id,attributes={"retry_after":t.retry_after,"partial_content":t.partial_content,"operational_headers":t.operational_headers})
class MercadoLivreFullReadCollector:
    def __init__(self,sessions:async_sessionmaker[AsyncSession],max_items_per_cycle:int=20)->None:
        self.sessions=sessions; self.max_items=max(1,min(max_items_per_cycle,50)); self.raw=PostgresRawEventRepository(sessions); self.channel=PostgresChannelEventRepository(sessions); self.entities=PostgresEntityRepository(sessions); self.snapshots=PostgresSnapshotRepository(sessions); self.bus=UniversalSensorBus()
    def _adapter(self,token:str|None=None)->MercadoLivreReadOnlyAdapter:return MercadoLivreReadOnlyAdapter(access_token=SecretStr(token or load_access_token()),network_allowed=True)
    async def _persist(self,result:MercadoLivreReadResult,event_type:str,payload:dict[str,Any],entity_type:str|None=None,entity_id:str|None=None)->tuple[bool,bool]:
        at=result.telemetry.observed_at; ch=await self.channel.append_if_new(_channel_event(result)); snap=False
        await self.raw.append_if_new(build_raw_event(source="mercadolivre_api",event_type=event_type,payload=payload,external_id=entity_id,resource=result.telemetry.endpoint,occurred_at=at,received_at=at))
        if entity_type and entity_id:
            entity=EntityRef(marketplace="mercadolivre",entity_type=entity_type,entity_id=str(entity_id)); await self.entities.upsert(entity,payload,at); snap=await self.snapshots.append_if_changed(entity,payload,at)
        await self.bus.publish(SensorSignal(marketplace="mercadolivre",kind=SensorSignalKind.BUSINESS_EVENT,evidence_kind=EvidenceKind.FACT,source=f"official_api_get:{result.telemetry.endpoint}",observed_at=at,entity=SensorEntity(entity_type=entity_type,entity_id=str(entity_id)) if entity_type and entity_id else None,payload={"event_type":event_type,"schema_fingerprint":result.schema_fingerprint,"partial":result.degraded},validated=True))
        return ch,snap
    async def collect_once(self)->MercadoLivreCollectionReport:
        errors:list[str]=[]; token_refreshed=False; adapter=self._adapter()
        try:
            try: me_result=await adapter.read_user_me()
            except MercadoLivreReadError as exc:
                if exc.status_code!=401: raise
                await adapter.aclose(); token=await refresh_access_token(); token_refreshed=token.refreshed; adapter=self._adapter(token.access_token); me_result=await adapter.read_user_me()
            me=safe_user(me_result.payload); account_id=str(me.get("id") or "")
            if not account_id.isdigit(): raise RuntimeError("mercadolivre_account_id_invalid")
            channel_count=int((await self._persist(me_result,"account_snapshot",me,"account",account_id))[0])
            item_search=await adapter._read(f"/users/{account_id}/items/search",params={"status":"active","limit":"50"}); item_search_payload=safe_items_search(item_search.payload)
            channel_count+=int((await self._persist(item_search,"active_items_search",item_search_payload))[0]); item_ids=[str(x) for x in item_search_payload.get("results") or [] if x][:self.max_items]; item_snapshots=0
            for item_id in item_ids:
                try:
                    item=await adapter.read_listing(item_id); c,s=await self._persist(item,"listing_snapshot",safe_item(item.payload),"listing",item_id); channel_count+=int(c); item_snapshots+=int(s)
                    visits=await adapter.read_visits(item_id); channel_count+=int((await self._persist(visits,"listing_visits",visits.payload,"visits",item_id))[0])
                    try:
                        comp=await adapter.read_catalog_competition(item_id); channel_count+=int((await self._persist(comp,"catalog_competition",comp.payload,"catalog_competition",item_id))[0])
                    except MercadoLivreReadError as exc: errors.append(f"catalog_competition:{item_id}:{exc.status_code or exc.code}")
                except MercadoLivreReadError as exc: errors.append(f"item:{item_id}:{exc.status_code or exc.code}")
            order_snapshots=0
            try:
                orders=await adapter._read("/orders/search",params={"seller":account_id,"sort":"date_desc","limit":"20"}); safe_orders=safe_orders_search(orders.payload); channel_count+=int((await self._persist(orders,"orders_search",safe_orders))[0])
                for order in safe_orders.get("results") or []:
                    oid=str(order.get("id") or "")
                    if oid:
                        entity=EntityRef(marketplace="mercadolivre",entity_type="order",entity_id=oid); await self.entities.upsert(entity,order,orders.telemetry.observed_at); order_snapshots+=int(await self.snapshots.append_if_changed(entity,order,orders.telemetry.observed_at))
            except MercadoLivreReadError as exc: errors.append(f"orders:{exc.status_code or exc.code}")
            questions_seen=0
            try:
                questions=await adapter._read("/questions/search",params={"seller_id":account_id,"api_version":"4","limit":"50"}); safe_q=safe_questions(questions.payload); questions_seen=len(safe_q.get("questions") or []); channel_count+=int((await self._persist(questions,"questions_search",safe_q))[0])
            except MercadoLivreReadError as exc: errors.append(f"questions:{exc.status_code or exc.code}")
            claims_seen=0
            try:
                claims=await adapter._read("/post-purchase/v1/claims/search",params={"status":"opened","limit":"30"}); safe_c=safe_claims(claims.payload); claims_seen=len(safe_c.get("data") or []); channel_count+=int((await self._persist(claims,"open_claims",safe_c))[0])
            except MercadoLivreReadError as exc: errors.append(f"claims:{exc.status_code or exc.code}")
            return MercadoLivreCollectionReport(success=True,account_id=account_id,items_seen=len(item_ids),item_snapshots=item_snapshots,order_snapshots=order_snapshots,questions_seen=questions_seen,claims_seen=claims_seen,channel_events=channel_count,errors=tuple(errors),token_refreshed=token_refreshed)
        finally:
            await adapter.aclose()
