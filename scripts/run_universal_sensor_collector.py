from __future__ import annotations
import argparse,asyncio,json,os
from datetime import UTC,datetime
from pathlib import Path
from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.marketplaces.mercadolivre.full_read_collector import MercadoLivreFullReadCollector
from market_intelligence.persistence.database import create_database_engine,create_session_factory
from market_intelligence.sensors.history import HistoricalMemoryService
def args():
    p=argparse.ArgumentParser(); p.add_argument("--once",action="store_true"); p.add_argument("--interval-seconds",type=float,default=300.0); p.add_argument("--max-items-per-cycle",type=int,default=20); p.add_argument("--status-path",default="runtime/sensors/status.json"); return p.parse_args()
def policy():
    if os.getenv("MI_READ_ONLY","true").lower()!="true":raise RuntimeError("sensor_collector_requires_read_only")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES","false").lower()!="false":raise RuntimeError("sensor_collector_forbids_marketplace_writes")
def write_status(path:Path,data:dict):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8"); tmp.replace(path)
async def cycle(db:str,max_items:int)->dict:
    engine=create_database_engine(db); sessions=create_session_factory(engine)
    try:
        r=await MercadoLivreFullReadCollector(sessions,max_items_per_cycle=max_items).collect_once(); m=await HistoricalMemoryService(sessions).summary()
        return {"timestamp":datetime.now(UTC).isoformat(),"collector_state":"ACTIVE","runtime_scope":"universal_multimarketplace","active_marketplaces":["mercadolivre"],"pending_external_authorization":["shopee"],"mercadolivre_success":r.success,"mercadolivre_items_seen":r.items_seen,"mercadolivre_item_snapshots":r.item_snapshots,"mercadolivre_order_snapshots":r.order_snapshots,"mercadolivre_questions_seen":r.questions_seen,"mercadolivre_claims_seen":r.claims_seen,"mercadolivre_channel_events_new":r.channel_events,"mercadolivre_errors":list(r.errors),"token_refreshed":r.token_refreshed,"memory_raw_events":m.raw_events,"memory_channel_events":m.channel_events,"memory_snapshots":m.snapshots,"memory_evidence":m.evidence,"memory_marketplaces":list(m.marketplaces),"memory_oldest_snapshot_at":m.oldest_snapshot_at.isoformat() if m.oldest_snapshot_at else None,"memory_newest_snapshot_at":m.newest_snapshot_at.isoformat() if m.newest_snapshot_at else None,"permanent_read_only":True,"permanent_marketplace_writes":False,"new_marketplace_write_executed":False}
    finally:await engine.dispose()
async def run(db:str,status:Path,interval:float,max_items:int,once:bool)->int:
    while True:
        try:
            data=await cycle(db,max_items); write_status(status,data)
            if once:print(json.dumps(data,sort_keys=True,separators=(",",":")));return 0
        except Exception as exc:
            data={"timestamp":datetime.now(UTC).isoformat(),"collector_state":"DEGRADED_RETRYING","error":type(exc).__name__,"runtime_scope":"universal_multimarketplace","permanent_read_only":True,"permanent_marketplace_writes":False,"new_marketplace_write_executed":False}; write_status(status,data)
            if once:print(json.dumps(data,sort_keys=True,separators=(",",":")));return 1
        await asyncio.sleep(max(30.0,interval))
def main()->int:
    policy(); a=args(); db=(os.getenv("MI_DATABASE_URL") or "").strip()
    if not db:raise RuntimeError("MI_DATABASE_URL_missing")
    status=Path(a.status_path); status=status if status.is_absolute() else Path(__file__).resolve().parents[1]/status
    with asyncio.Runner(loop_factory=psycopg_compatible_loop) as runner:return runner.run(run(db,status,a.interval_seconds,a.max_items_per_cycle,a.once))
if __name__=="__main__":raise SystemExit(main())
