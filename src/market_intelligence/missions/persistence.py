from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.missions.models import MissionCreate

ACTIVE_STATES=("RECEIVED","PLANNING","COLLECTING","CORRELATING","INVESTIGATING","VALIDATING","REPORTING","DEGRADED")


def stable_hash(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class PostgresMissionRepository:
    def __init__(self,sessions:async_sessionmaker[AsyncSession])->None:
        self.sessions=sessions

    @staticmethod
    def row(value:Any)->dict[str,Any]:
        return dict(value)

    async def create(self,request:MissionCreate,*,dedupe_key:str|None=None)->tuple[dict[str,Any],bool]:
        if request.authority not in {"owner_read_only","system_read_only","radar_read_only"}:
            raise PermissionError("mission_authority_rejected")
        if request.idempotency_key and not dedupe_key:
            dedupe_key=stable_hash({"directed":request.idempotency_key})
        mid="MI-"+uuid4().hex[:20].upper()
        async with self.sessions() as s:
            if dedupe_key:
                existing=(await s.execute(text("SELECT * FROM sovereign_missions WHERE dedupe_key=:k"),{"k":dedupe_key})).mappings().first()
                if existing:
                    return dict(existing),False
            result=await s.execute(text("""
                INSERT INTO sovereign_missions(mission_id,dedupe_key,origin,objective,mission_type,marketplace_scope,authority,priority,status,deadline_at,checkpoint,marketplace_writes)
                VALUES(:id,:dk,:origin,:objective,:mtype,CAST(:scope AS jsonb),:authority,:priority,'RECEIVED',:deadline,CAST(:cp AS jsonb),0)
                RETURNING *
            """),{"id":mid,"dk":dedupe_key,"origin":request.origin.value,"objective":request.objective,"mtype":request.mission_type.value,"scope":json.dumps(list(request.marketplace_scope)),"authority":request.authority,"priority":request.priority,"deadline":request.deadline_at,"cp":json.dumps({"last_safe_state":"RECEIVED","marketplace_writes":0})})
            row=dict(result.mappings().one()); await s.commit(); return row,True

    async def get(self,mid:str)->dict[str,Any]|None:
        async with self.sessions() as s:
            row=(await s.execute(text("SELECT * FROM sovereign_missions WHERE mission_id=:id"),{"id":mid})).mappings().first()
            return dict(row) if row else None

    async def list(self,limit:int=50)->list[dict[str,Any]]:
        async with self.sessions() as s:
            rows=(await s.execute(text("SELECT * FROM sovereign_missions ORDER BY created_at DESC LIMIT :n"),{"n":limit})).mappings().all()
            return [dict(r) for r in rows]

    async def latest(self)->dict[str,Any]|None:
        rows=await self.list(1); return rows[0] if rows else None

    async def claim_next(self)->dict[str,Any]|None:
        async with self.sessions() as s:
            row=(await s.execute(text("""
                SELECT * FROM sovereign_missions WHERE status=ANY(CAST(:states AS text[]))
                ORDER BY priority DESC,created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1
            """),{"states":list(ACTIVE_STATES)})).mappings().first()
            if not row:
                await s.rollback(); return None
            if row["started_at"] is None:
                await s.execute(text("UPDATE sovereign_missions SET started_at=now(),updated_at=now() WHERE mission_id=:id"),{"id":row["mission_id"]})
            await s.commit(); return dict(row)

    async def transition(self,mid:str,from_state:str,to_state:str,checkpoint:dict[str,Any])->bool:
        if int(checkpoint.get("marketplace_writes",0))!=0:
            raise RuntimeError("mission_checkpoint_write_boundary")
        async with self.sessions() as s:
            current=(await s.execute(text("SELECT status FROM sovereign_missions WHERE mission_id=:id FOR UPDATE"),{"id":mid})).scalar_one()
            if current!=from_state:
                await s.rollback(); return False
            await s.execute(text("""
                INSERT INTO mission_steps(id,mission_id,step_key,state,status,attempt,checkpoint,completed_at)
                VALUES(:sid,:mid,:key,:state,'COMPLETED',1,CAST(:cp AS jsonb),now())
                ON CONFLICT(mission_id,step_key) DO NOTHING
            """),{"sid":uuid4(),"mid":mid,"key":from_state.lower(),"state":from_state,"cp":json.dumps(checkpoint,default=str)})
            completed="now()" if to_state=="COMPLETED" else "NULL"
            await s.execute(text(f"UPDATE sovereign_missions SET status=:to_state,checkpoint=CAST(:cp AS jsonb),updated_at=now(),completed_at={completed},marketplace_writes=0 WHERE mission_id=:mid"),{"to_state":to_state,"cp":json.dumps(checkpoint,default=str),"mid":mid})
            await s.commit(); return True

    async def fail(self,mid:str,error_code:str)->None:
        async with self.sessions() as s:
            await s.execute(text("UPDATE sovereign_missions SET status=CASE WHEN retry_count<3 THEN 'DEGRADED' ELSE 'FAILED' END,error_code=:err,retry_count=retry_count+1,updated_at=now(),marketplace_writes=0 WHERE mission_id=:mid"),{"err":error_code[:160],"mid":mid}); await s.commit()

    async def add_evidence(self,mid:str,evidence_type:str,source:str,payload:dict[str,Any],observed_at:datetime|None=None)->None:
        observed_at=observed_at or datetime.now(UTC); dk=stable_hash({"t":evidence_type,"s":source,"p":payload})
        async with self.sessions() as s:
            await s.execute(text("""
                INSERT INTO mission_evidence(id,mission_id,dedupe_key,evidence_type,source,observed_at,evidence_json)
                VALUES(:id,:mid,:dk,:t,:src,:obs,CAST(:p AS jsonb)) ON CONFLICT(mission_id,dedupe_key) DO NOTHING
            """),{"id":uuid4(),"mid":mid,"dk":dk,"t":evidence_type,"src":source,"obs":observed_at,"p":json.dumps(payload,default=str,ensure_ascii=False)}); await s.commit()

    async def add_finding(self,mid:str,finding_type:str,knowledge_state:str,severity:str,confidence:float,payload:dict[str,Any])->None:
        dk=stable_hash({"t":finding_type,"p":payload})
        async with self.sessions() as s:
            await s.execute(text("""
                INSERT INTO mission_findings(id,mission_id,dedupe_key,finding_type,knowledge_state,severity,confidence,finding_json)
                VALUES(:id,:mid,:dk,:t,:ks,:sev,:c,CAST(:p AS jsonb)) ON CONFLICT(mission_id,dedupe_key) DO NOTHING
            """),{"id":uuid4(),"mid":mid,"dk":dk,"t":finding_type,"ks":knowledge_state,"sev":severity,"c":max(0,min(1,float(confidence))),"p":json.dumps(payload,default=str,ensure_ascii=False)}); await s.commit()

    async def findings(self,mid:str)->list[dict[str,Any]]:
        async with self.sessions() as s:
            return [dict(r) for r in (await s.execute(text("SELECT finding_type,knowledge_state,severity,confidence,finding_json,created_at FROM mission_findings WHERE mission_id=:mid ORDER BY created_at"),{"mid":mid})).mappings().all()]

    async def evidence(self,mid:str)->list[dict[str,Any]]:
        async with self.sessions() as s:
            return [dict(r) for r in (await s.execute(text("SELECT evidence_type,source,observed_at,evidence_json FROM mission_evidence WHERE mission_id=:mid ORDER BY observed_at"),{"mid":mid})).mappings().all()]

    async def recent_sovereign(self,since:datetime|None,limit:int=200)->list[dict[str,Any]]:
        async with self.sessions() as s:
            q="SELECT * FROM sovereign_intelligence"; params={"n":limit}
            if since is not None: q+=" WHERE observed_at>=:since"; params["since"]=since
            q+=" ORDER BY observed_at DESC LIMIT :n"
            return [dict(r) for r in (await s.execute(text(q),params)).mappings().all()]

    async def exposures(self,limit:int=100)->list[dict[str,Any]]:
        async with self.sessions() as s:
            return [dict(r) for r in (await s.execute(text("SELECT * FROM exposure_map ORDER BY last_observed_at DESC LIMIT :n"),{"n":limit})).mappings().all()]

    async def save_report(self,mid:str,report:dict[str,Any],markdown:str,confidence:float)->None:
        async with self.sessions() as s:
            await s.execute(text("""
                INSERT INTO mission_reports(id,mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes)
                VALUES(:id,:mid,'mission-report@1.0.0',CAST(:r AS jsonb),:md,:c,0)
                ON CONFLICT(mission_id) DO UPDATE SET report_json=EXCLUDED.report_json,report_markdown=EXCLUDED.report_markdown,confidence=EXCLUDED.confidence,marketplace_writes=0,created_at=now()
            """),{"id":uuid4(),"mid":mid,"r":json.dumps(report,default=str,ensure_ascii=False),"md":markdown,"c":max(0,min(1,float(confidence)))}); await s.commit()

    async def get_report(self,mid:str)->dict[str,Any]|None:
        async with self.sessions() as s:
            row=(await s.execute(text("SELECT mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes,created_at FROM mission_reports WHERE mission_id=:mid"),{"mid":mid})).mappings().first(); return dict(row) if row else None

    async def latest_report(self)->dict[str,Any]|None:
        async with self.sessions() as s:
            row=(await s.execute(text("SELECT mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes,created_at FROM mission_reports ORDER BY created_at DESC LIMIT 1"))).mappings().first(); return dict(row) if row else None

    async def health(self)->dict[str,Any]:
        async with self.sessions() as s:
            rows=(await s.execute(text("SELECT status,count(*) n FROM sovereign_missions GROUP BY status"))).mappings().all(); counts={r["status"]:int(r["n"]) for r in rows}
            last=(await s.execute(text("SELECT mission_id FROM sovereign_missions WHERE status='COMPLETED' ORDER BY completed_at DESC NULLS LAST LIMIT 1"))).scalar_one_or_none()
            report_at=(await s.execute(text("SELECT created_at FROM mission_reports ORDER BY created_at DESC LIMIT 1"))).scalar_one_or_none()
            running=sum(counts.get(x,0) for x in ACTIVE_STATES if x!="RECEIVED")
            return {"counts":counts,"missions_running":running,"missions_pending":counts.get("RECEIVED",0),"last_completed_mission":last,"last_report_at":report_at}


    async def steps(self,mid:str)->list[dict[str,Any]]:
        async with self.sessions() as s:
            return [dict(r) for r in (await s.execute(text("SELECT step_key,state,status,attempt,checkpoint,started_at,completed_at,error_code FROM mission_steps WHERE mission_id=:mid ORDER BY started_at"),{"mid":mid})).mappings().all()]
    async def autonomous_candidates(self,limit:int=20)->list[dict[str,Any]]:
        async with self.sessions() as s:
            return [dict(r) for r in (await s.execute(text("SELECT id,marketplace,entity_type,entity_id,observed_change,severity,confidence,detector_version,created_at FROM alerts WHERE severity IN ('high','critical') ORDER BY created_at DESC LIMIT :n"),{"n":limit})).mappings().all()]

    async def radar_alert_already_missioned(self,alert_id:str)->bool:
        async with self.sessions() as s:
            count=int((await s.execute(text("""
                SELECT count(*) FROM mission_evidence
                WHERE evidence_type='radar_trigger' AND evidence_json->>'alert_id'=:alert_id
            """),{"alert_id":alert_id})).scalar_one())
            return count>0

    async def active_autonomous_count(self)->int:
        async with self.sessions() as s:
            return int((await s.execute(text("SELECT count(*) FROM sovereign_missions WHERE mission_type='AUTONOMOUS' AND status=ANY(CAST(:states AS text[]))"),{"states":list(ACTIVE_STATES)})).scalar_one())

    @staticmethod
    def autonomous_dedupe(alert:dict[str,Any],cooldown_hours:int=6)->str:
        dt=alert.get("created_at") or datetime.now(UTC)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=UTC)
        bucket=int(dt.timestamp()//(cooldown_hours*3600))
        return stable_hash({"m":alert.get("marketplace"),"et":alert.get("entity_type"),"eid":alert.get("entity_id"),"d":alert.get("detector_version"),"b":bucket})
