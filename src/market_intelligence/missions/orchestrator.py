from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from market_intelligence.intelligence.sovereign.runtime import run_cycle as run_sovereign_cycle
from market_intelligence.missions.models import MissionCreate, MissionOrigin, MissionType
from market_intelligence.missions.persistence import PostgresMissionRepository

STATE_NEXT={"RECEIVED":"PLANNING","PLANNING":"COLLECTING","COLLECTING":"CORRELATING","CORRELATING":"INVESTIGATING","INVESTIGATING":"VALIDATING","VALIDATING":"REPORTING","REPORTING":"COMPLETED","DEGRADED":"COLLECTING"}


class SovereignMissionOrchestrator:
    version="sovereign-mission-orchestrator@1.0.0"

    def __init__(self,repository:PostgresMissionRepository,database_url:str,runtime_root:Path,step_delay_seconds:float=0.5)->None:
        self.repo=repository; self.database_url=database_url; self.runtime_root=runtime_root; self.step_delay_seconds=step_delay_seconds

    @staticmethod
    def assert_security()->None:
        if os.getenv("MI_READ_ONLY","true").strip().lower()!="true": raise RuntimeError("mission_orchestrator_requires_read_only")
        if os.getenv("MI_ALLOW_MARKETPLACE_WRITES","false").strip().lower()!="false": raise RuntimeError("mission_orchestrator_forbids_marketplace_writes")
        if os.getenv("MARKETPLACE_WRITES","0").strip()!="0": raise RuntimeError("mission_orchestrator_marketplace_writes_nonzero")

    async def run_forever(self)->None:
        self.assert_security()
        while True:
            try:
                await self.open_autonomous_from_radar()
                mission=await self.repo.claim_next()
                if mission: await self.advance(mission)
            except asyncio.CancelledError: raise
            except Exception: await asyncio.sleep(1)
            await asyncio.sleep(self.step_delay_seconds)

    async def advance(self,mission:dict[str,Any])->None:
        self.assert_security(); mid=mission["mission_id"]; state=mission["status"]; cp=dict(mission.get("checkpoint") or {})
        cp.update({"last_safe_state":state,"marketplace_writes":0,"updated_at":datetime.now(UTC).isoformat()})
        try:
            if state=="RECEIVED":
                cp["plan"]={"protocol":"sovereign-mission@1.0.0","steps":["collect","correlate","investigate","validate","report"],"uses_existing_sovereign_core":True,"read_only":True}
            elif state=="PLANNING":
                text=mission["objective"].lower(); cp["lookback_hours"]=None if ("baseline" in text or "todo historico" in text or "todo hist\u00f3rico" in text) else 24
            elif state=="COLLECTING":
                core=await run_sovereign_cycle(self.database_url,max_records=64)
                if core.get("marketplace_writes")!=0: raise RuntimeError("core_write_boundary_violation")
                if core.get("core_health") not in {"PASS","DEGRADED"}: raise RuntimeError("core_collection_failed")
                cp["core_cycle"]={k:core.get(k) for k in ("core_health","processed_this_cycle","new_intelligence_records","investigations_advanced_this_cycle","learning_episodes_total","marketplace_writes")}
                await self.repo.add_evidence(mid,"core_cycle","sovereign_core",cp["core_cycle"])
            elif state=="CORRELATING":
                since=None if cp.get("lookback_hours") is None else datetime.now(UTC)-timedelta(hours=int(cp.get("lookback_hours",24)))
                rows=await self.repo.recent_sovereign(since,200); cp["sovereign_records_considered"]=len(rows)
                for row in rows[:100]:
                    await self.repo.add_finding(mid,"sovereign_intelligence",row["knowledge_state"],row["severity"],row["confidence"],{"signal_kind":row["signal_kind"],"summary":row["summary"],"entity_type":row["entity_type"],"entity_id":row["entity_id"],"observed_at":row["observed_at"].isoformat(),"report":row.get("report_json") or {}})
            elif state=="INVESTIGATING":
                findings=await self.repo.findings(mid); cp["findings_count"]=len(findings)
                await self.repo.add_evidence(mid,"investigation_checkpoint","progressive_investigator",{"findings_count":len(findings),"causal_claim":False,"marketplace_writes":0})
            elif state=="VALIDATING":
                findings=await self.repo.findings(mid); cp["validation"]={"total":len(findings),"validated":sum(1 for f in findings if f["knowledge_state"]=="validated"),"rejected_or_quarantined":sum(1 for f in findings if f["knowledge_state"] in {"rejected","quarantined"}),"causal_claim_without_evidence":False}
            elif state=="REPORTING":
                report,md,confidence=await self.build_report(mission); await self.repo.save_report(mid,report,md,confidence); await self.write_projection(mission,report,md)
                cp["report_generated_at"]=datetime.now(UTC).isoformat(); cp["report_confidence"]=confidence
            else: return
            await self.repo.transition(mid,state,STATE_NEXT[state],cp)
        except Exception as exc:
            await self.repo.fail(mid,type(exc).__name__); raise

    async def build_report(self,mission:dict[str,Any])->tuple[dict[str,Any],str,float]:
        mid=mission["mission_id"]; findings=await self.repo.findings(mid); evidence=await self.repo.evidence(mid); exposures=await self.repo.exposures(50)
        validated=[f for f in findings if f["knowledge_state"]=="validated"]
        hypotheses=[f for f in findings if f["knowledge_state"] in {"hypothesis","observed","correlated","tested","quarantined"}]
        predictions=[]; opportunities=[]; threats=[]; correlations=[]
        for f in findings:
            data=f.get("finding_json") or {}; report=data.get("report") or {}; pred=report.get("prediction") or {}; intel=report.get("intelligence") or {}; corr=report.get("correlation") or {}
            if pred: predictions.append({"statement":pred.get("statement"),"confidence":pred.get("confidence"),"state":pred.get("state")})
            if intel.get("opportunity") and intel.get("summary"): opportunities.append(intel["summary"])
            if (intel.get("threat") or str(f.get("severity")).lower() in {"high","critical"}) and (intel.get("summary") or data.get("summary")): threats.append(intel.get("summary") or data.get("summary"))
            if corr.get("related_signal_ids"): correlations.append({"reason":corr.get("reason"),"strength":corr.get("strength"),"related_signal_ids":corr.get("related_signal_ids")})
        confidence=round(sum(float(f["confidence"]) for f in findings)/len(findings),4) if findings else 0.0
        report={
            "mission":{"mission_id":mid,"objective":mission["objective"],"origin":mission["origin"],"mission_type":mission["mission_type"]},
            "period":{"created_at":mission["created_at"].isoformat(),"reported_at":datetime.now(UTC).isoformat()},
            "conclusion":f"Foram considerados {len(findings)} achados soberanos e {len(evidence)} evidencias persistidas. Conclusoes permanecem limitadas ao observavel e validado.",
            "evidence":[{"type":e["evidence_type"],"source":e["source"],"observed_at":e["observed_at"].isoformat(),"data":e["evidence_json"]} for e in evidence],
            "findings":[{"type":f["finding_type"],"state":f["knowledge_state"],"severity":f["severity"],"confidence":f["confidence"],"data":f["finding_json"]} for f in findings],
            "correlations":correlations[:50],"hypotheses":[f["finding_json"] for f in hypotheses[:50]],"validated":[f["finding_json"] for f in validated[:50]],"not_proven":[f["finding_json"] for f in hypotheses[:50]],
            "counterintelligence":[{"data_point":x["data_point"],"platform_observes":x["platform_observes"],"possible_inferences":x["possible_inferences"],"risk_level":x["risk_level"],"mitigation":x["mitigation"]} for x in exposures],
            "predictions":predictions[:50],"opportunities":list(dict.fromkeys(opportunities))[:30],"threats":list(dict.fromkeys(threats))[:30],
            "recommendations":["Manter coleta soberana em modo leitura.","Confirmar hipoteses por repeticao e evidencia independente antes de atribuir causalidade.","Priorizar achados de maior severidade e confianca sem atravessar o Action Gateway."],
            "confidence":confidence,"limitations":["Somente dados legitimamente disponiveis foram considerados.","Correlacao nao foi tratada como causalidade.","Nenhuma acao externa foi autorizada nesta missao."],"marketplace_action":"NENHUMA","marketplace_writes":0,
        }
        return report,self.to_markdown(report),confidence

    @staticmethod
    def to_markdown(r:dict[str,Any])->str:
        def u(*points:int)->str: return "".join(chr(x) for x in points)
        A_TILDE=u(0x00C3); A_ACUTE=u(0x00C1); C_CED=u(0x00C7); E_CIRC=u(0x00CA); I_ACUTE=u(0x00CD); O_ACUTE=u(0x00D3); O_TILDE=u(0x00D5)
        def b(title:str,value:Any)->str:
            if isinstance(value,list): body="\n".join("- "+json.dumps(x,ensure_ascii=False,default=str) for x in value) or "- Nenhum registro."
            elif isinstance(value,dict): body=json.dumps(value,ensure_ascii=False,default=str,indent=2)
            else: body=str(value)
            return "## "+title+"\n"+body+"\n"
        sections=[
            ("MISS"+A_TILDE+"O",r["mission"]),("PER"+I_ACUTE+"ODO",r["period"]),("CONCLUS"+A_TILDE+"O",r["conclusion"]),("EVID"+E_CIRC+"NCIAS",r["evidence"]),("DESCOBERTAS",r["findings"]),("CORRELA"+C_CED+O_TILDE+"ES",r["correlations"]),("HIP"+O_ACUTE+"TESES",r["hypotheses"]),("O QUE FOI VALIDADO",r["validated"]),("O QUE N"+A_TILDE+"O FOI PROVADO",r["not_proven"]),("CONTRAINTELIG"+E_CIRC+"NCIA",r["counterintelligence"]),("PREVIS"+O_TILDE+"ES",r["predictions"]),("OPORTUNIDADES",r["opportunities"]),("AMEA"+C_CED+"AS",r["threats"]),("RECOMENDA"+C_CED+O_TILDE+"ES",r["recommendations"]),("CONFIAN"+C_CED+"A",r["confidence"]),("LIMITA"+C_CED+O_TILDE+"ES",r["limitations"]),("A"+C_CED+A_TILDE+"O EXECUTADA NO MARKETPLACE","NENHUMA")]
        return "# RELAT"+O_ACUTE+"RIO SOBERANO OPERACIONAL\n\n"+"\n".join(b(k,v) for k,v in sections)

    async def write_projection(self,mission:dict[str,Any],report:dict[str,Any],md:str)->None:
        root=self.runtime_root/"missions"/mission["mission_id"]; root.mkdir(parents=True,exist_ok=True)
        current=await self.repo.get(mission["mission_id"]); evidence=await self.repo.evidence(mission["mission_id"]); findings=await self.repo.findings(mission["mission_id"])
        for name,payload in {"mission.json":mission,"status.json":current,"evidence.json":evidence,"findings.json":findings,"REPORT.json":report}.items(): (root/name).write_text(json.dumps(payload,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
        (root/"REPORT.md").write_text(md,encoding="utf-8")

    async def open_autonomous_from_radar(self)->None:
        if await self.repo.active_autonomous_count()>=4: return
        for alert in await self.repo.autonomous_candidates(20):
            if await self.repo.radar_alert_already_missioned(str(alert["id"])):
                continue
            key=self.repo.autonomous_dedupe(alert,6)
            req=MissionCreate(objective="Investigue autonomamente o sinal relevante detectado pelo Radar em "+str(alert["marketplace"])+"/"+str(alert["entity_type"])+":"+str(alert["entity_id"])+": "+str(alert["observed_change"])+". Nao atribua causalidade sem evidencia.",origin=MissionOrigin.RADAR,mission_type=MissionType.AUTONOMOUS,marketplace_scope=(alert["marketplace"],),authority="radar_read_only",priority=80 if str(alert["severity"]).lower()=="critical" else 70)
            mission,created=await self.repo.create(req,dedupe_key=key)
            if created:
                await self.repo.add_evidence(mission["mission_id"],"radar_trigger","radar",{"alert_id":str(alert["id"]),"severity":alert["severity"],"confidence":alert["confidence"],"detector_version":alert.get("detector_version"),"marketplace_writes":0},alert.get("created_at")); break
