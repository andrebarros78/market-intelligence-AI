from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from market_intelligence.intelligence.sovereign.investigation_bridge import (
    SovereignInvestigationBridge,
)
from market_intelligence.intelligence.sovereign.models import SignalEnvelope
from market_intelligence.intelligence.sovereign.organs import (
    SovereignCounterIntelligence,
    SovereignInstigator,
)
from market_intelligence.intelligence.sovereign.runtime import run_cycle as run_sovereign_cycle
from market_intelligence.missions.models import MissionCreate, MissionOrigin, MissionType
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.missions.planner import CognitiveMissionPlanner
from market_intelligence.persistence.database import create_database_engine, create_session_factory

STATE_NEXT = {
    "RECEIVED": "PLANNING", "PLANNING": "COLLECTING", "COLLECTING": "CORRELATING",
    "CORRELATING": "INVESTIGATING", "INVESTIGATING": "VALIDATING", "VALIDATING": "REPORTING",
    "REPORTING": "COMPLETED", "DEGRADED": "COLLECTING",
}


def _average_confidence(findings: list[dict[str, Any]]) -> float:
    return sum(float(item.get("confidence") or 0.0) for item in findings) / len(findings) if findings else 0.0


class SovereignMissionOrchestrator:
    version = "sovereign-mission-orchestrator@1.1.0"

    def __init__(self, repository: PostgresMissionRepository, database_url: str, runtime_root: Path, step_delay_seconds: float = 0.5) -> None:
        self.repo = repository
        self.database_url = database_url
        self.runtime_root = runtime_root
        self.step_delay_seconds = step_delay_seconds
        self.planner = CognitiveMissionPlanner()
        self.instigator = SovereignInstigator()
        self.counterintelligence = SovereignCounterIntelligence()

    @staticmethod
    def assert_security() -> None:
        if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true": raise RuntimeError("mission_orchestrator_requires_read_only")
        if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false": raise RuntimeError("mission_orchestrator_forbids_marketplace_writes")
        if os.getenv("MARKETPLACE_WRITES", "0").strip() != "0": raise RuntimeError("mission_orchestrator_marketplace_writes_nonzero")

    async def run_forever(self) -> None:
        self.assert_security()
        while True:
            try:
                await self.open_autonomous_from_radar()
                mission = await self.repo.claim_next()
                if mission: await self.advance(mission)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1)
            await asyncio.sleep(self.step_delay_seconds)

    async def advance(self, mission: dict[str, Any]) -> None:
        self.assert_security(); mission_id = mission["mission_id"]; state = mission["status"]; checkpoint = dict(mission.get("checkpoint") or {})
        checkpoint.update({"last_safe_state": state, "marketplace_writes": 0, "updated_at": datetime.now(UTC).isoformat()})
        try:
            if state == "RECEIVED":
                checkpoint.update({"protocol": "sovereign-mission@1.1.0", "uses_existing_sovereign_core": True, "cognitive_loop": True, "read_only": True})
            elif state == "PLANNING":
                await self._plan(mission, checkpoint)
            elif state == "COLLECTING":
                await self._collect(mission, checkpoint)
            elif state == "CORRELATING":
                await self._correlate(mission, checkpoint)
            elif state == "INVESTIGATING":
                await self._investigate(mission, checkpoint)
            elif state == "VALIDATING":
                await self._validate(mission, checkpoint)
            elif state == "REPORTING":
                report, markdown, confidence = await self.build_report(mission)
                report_id = await self.repo.save_report(mission_id, report, markdown, confidence)
                await self.write_projection(mission, report, markdown)
                await self.repo.upsert_inbox(mission=mission, report_id=report_id, severity=self._report_severity(report), title=f"Intelligence: {mission['objective'][:180]}", summary=report["conclusion"], confidence=confidence)
                checkpoint.update({"report_generated_at": datetime.now(UTC).isoformat(), "report_confidence": confidence, "report_id": str(report_id)})
            else:
                return
            await self.repo.transition(mission_id, state, STATE_NEXT[state], checkpoint)
        except Exception as exc:
            await self.repo.fail(mission_id, type(exc).__name__)
            raise

    async def _plan(self, mission: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        request = MissionCreate(objective=mission["objective"], origin=MissionOrigin(mission["origin"]), mission_type=MissionType(mission["mission_type"]), marketplace_scope=tuple(mission["marketplace_scope"]), authority=mission["authority"], priority=int(mission["priority"]), deadline_at=mission.get("deadline_at"))
        inherited = None
        if mission.get("parent_mission_id"):
            inherited = {"parent_mission_id": mission["parent_mission_id"], "source_report_id": mission.get("source_report_id"), "source_finding_id": mission.get("source_finding_id"), "follow_up_question": mission.get("follow_up_question")}
        plan = self.planner.compile(request, data_inventory=await self.repo.data_inventory(), mode=str(mission.get("mode") or "standard"), inherited_context=inherited)
        await self.repo.save_plan(mission["mission_id"], plan)
        checkpoint.update({"plan_version": plan.plan_version, "lookback_hours": plan.temporal_window.get("lookback_hours"), "signal_families": plan.signal_families, "main_question": plan.main_question, "open_questions": plan.secondary_questions[:20], "iteration_count": 0})

    async def _collect(self, mission: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        core = await run_sovereign_cycle(self.database_url, max_records=64)
        if core.get("marketplace_writes") != 0: raise RuntimeError("core_write_boundary_violation")
        if core.get("core_health") not in {"PASS", "DEGRADED"}: raise RuntimeError("core_collection_failed")
        summary = {key: core.get(key) for key in ("core_health", "processed_this_cycle", "new_intelligence_records", "investigations_advanced_this_cycle", "learning_episodes_total", "validated_this_cycle", "quarantined_this_cycle", "marketplace_writes")}
        checkpoint["core_cycle"] = summary
        await self.repo.add_evidence(mission["mission_id"], "core_cycle", "sovereign_core", summary)

    async def _correlate(self, mission: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        stored = await self.repo.get_plan(mission["mission_id"])
        if not stored: raise RuntimeError("cognitive_mission_plan_missing")
        plan = stored["plan_json"]; lookback = (plan.get("temporal_window") or {}).get("lookback_hours")
        since = None if lookback is None else datetime.now(UTC) - timedelta(hours=int(lookback))
        rows = await self.repo.targeted_sovereign(plan, since=since, limit=300)
        checkpoint["objective_matched_records"] = len(rows); checkpoint["objective_filter_families"] = plan.get("signal_families") or []
        for row in rows:
            await self.repo.add_finding(mission["mission_id"], "objective_directed_sovereign_intelligence", row["knowledge_state"], row["severity"], row["confidence"], {"source_intelligence_id": str(row["id"]), "signal_kind": row["signal_kind"], "summary": row["summary"], "entity_type": row["entity_type"], "entity_id": row["entity_id"], "observed_at": row["observed_at"].isoformat(), "matched_signal_families": plan.get("signal_families") or [], "report": row.get("report_json") or {}})
        await self.repo.add_evidence(mission["mission_id"], "objective_directed_selection", "cognitive_mission_planner", {"main_question": plan.get("main_question"), "signal_families": plan.get("signal_families"), "matched_records": len(rows), "lookback_hours": lookback, "marketplace_writes": 0})

    async def _investigate(self, mission: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        stored = await self.repo.get_plan(mission["mission_id"])
        if not stored: raise RuntimeError("cognitive_mission_plan_missing")
        plan = stored["plan_json"]; existing_iterations = await self.repo.iterations(mission["mission_id"]); start_iteration = len(existing_iterations) + 1
        seen_ids: set[str] = set(); previous_confidence = 0.0
        if existing_iterations:
            last_payload = existing_iterations[-1].get("iteration_json") or {}; seen_ids.update(str(item) for item in last_payload.get("seen_finding_ids") or []); previous_confidence = float(existing_iterations[-1].get("confidence_after") or 0.0)
            if existing_iterations[-1].get("stop_reason"):
                checkpoint["iteration_count"] = len(existing_iterations); checkpoint["stop_reason"] = existing_iterations[-1]["stop_reason"]; return
        max_iterations = 3; mode = str(mission.get("mode") or "standard")
        for iteration in range(start_iteration, max_iterations + 1):
            findings = await self.repo.findings(mission["mission_id"])
            current_ids = {str(item["id"]) for item in findings if item["finding_type"] == "objective_directed_sovereign_intelligence"}
            evidence_gain = len(current_ids - seen_ids); seen_ids.update(current_ids)
            directed = [item for item in findings if item["finding_type"] == "objective_directed_sovereign_intelligence"]
            confidence_after = _average_confidence(directed)
            correlations: list[Any] = []; hypotheses: list[Any] = []; predictions: list[Any] = []; contradictions: list[Any] = []; gaps = list(plan.get("missing_data") or [])
            for item in findings[:80]:
                data = item.get("finding_json") or {}; report = data.get("report") or {}
                if report.get("correlation"): correlations.append(report["correlation"])
                hypotheses.extend(report.get("hypotheses") or [])
                if report.get("prediction"): predictions.append(report["prediction"])
                audit = report.get("audit") or {}
                if audit.get("contradiction_detected"): contradictions.append(audit)
                validation = report.get("validation") or {}
                if validation.get("state") in {"hypothesis", "observed", "correlated", "quarantined", "rejected"}: gaps.append(str(validation.get("reason") or validation.get("state")))
            evidence = await self.repo.evidence(mission["mission_id"])
            counter_objections = self.counterintelligence.challenge(findings=findings[:40], evidence=evidence, mode=mode)
            feedback_questions = self.instigator.feedback(findings=findings[:40], correlations=correlations[:30], hypotheses=hypotheses[:40], evidence=evidence[-40:], contradictions=contradictions[:20], counterintelligence_objections=list(counter_objections), predictions=predictions[:30], gaps=gaps[:30])
            open_questions = list(dict.fromkeys([*(plan.get("secondary_questions") or []), *feedback_questions, *counter_objections]))[:30]
            investigation_results = await self._advance_progressive(findings=findings, questions=open_questions)
            evidence_gain += sum(1 for result in investigation_results if result and (result.get("evidence_summary") or {}).get("event_inserted"))
            for result in investigation_results:
                if result:
                    await self.repo.add_evidence(mission["mission_id"], "progressive_investigator_feedback", "progressive-investigation@1.0.0", {"iteration": iteration, "result": result, "marketplace_writes": 0})
            await self.repo.add_evidence(mission["mission_id"], "instigator_feedback", "sovereign-instigator@1.0.0", {"iteration": iteration, "questions": list(feedback_questions), "counterintelligence_objections": list(counter_objections), "marketplace_writes": 0})
            confidence_change = confidence_after - previous_confidence; stop_reason: str | None = None
            if not findings: stop_reason = "legitimate_evidence_exhausted"
            elif iteration >= 2 and evidence_gain == 0 and abs(confidence_change) < 0.01: stop_reason = "evidence_saturation"
            elif iteration >= max_iterations: stop_reason = "max_safe_iterations"
            payload = {"iteration": iteration, "objective": mission["objective"], "mode": mode, "phases": ["collect", "correlate", "instigate", "investigate", "experiment_read_only", "intelligence", "counterintelligence", "validate", "learn_if_validated", "predict", "evaluate_gaps"], "instigator_questions": list(feedback_questions), "counterintelligence_objections": list(counter_objections), "progressive_investigation_results": investigation_results, "seen_finding_ids": sorted(seen_ids), "open_questions": open_questions, "validation_before_learning": True, "learning_eligible_findings": sum(1 for item in findings if item.get("knowledge_state") == "validated"), "marketplace_writes": 0}
            await self.repo.save_iteration(mission["mission_id"], iteration_count=iteration, status="COMPLETED" if stop_reason else "CONTINUE", evidence_gain=evidence_gain, confidence_before=previous_confidence, confidence_after=confidence_after, open_questions=open_questions, stop_reason=stop_reason, payload=payload)
            checkpoint.update({"iteration_count": iteration, "evidence_gain": evidence_gain, "confidence_change": confidence_change, "open_questions": open_questions, "stop_reason": stop_reason}); previous_confidence = confidence_after
            if stop_reason: break

    async def _advance_progressive(self, *, findings: list[dict[str, Any]], questions: list[str]) -> list[dict[str, Any]]:
        engine = create_database_engine(self.database_url); sessions = create_session_factory(engine); bridge = SovereignInvestigationBridge(sessions); results: list[dict[str, Any]] = []
        try:
            for item in findings[:12]:
                data = item.get("finding_json") or {}; report = data.get("report") or {}; raw_signal = report.get("signal")
                if not isinstance(raw_signal, dict): continue
                try: signal = SignalEnvelope.model_validate(raw_signal)
                except Exception: continue
                raw_hypotheses = report.get("hypotheses") or []; hypotheses = [str(h.get("statement")) for h in raw_hypotheses if isinstance(h, dict) and h.get("statement")]
                result = await bridge.advance(signal=signal, history=(), hypotheses=hypotheses, questions=questions)
                if result: results.append(result)
        finally:
            await engine.dispose()
        return results

    async def _validate(self, mission: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        findings = await self.repo.findings(mission["mission_id"]); iterations = await self.repo.iterations(mission["mission_id"])
        validated = [item for item in findings if item["knowledge_state"] == "validated"]
        inconclusive = [item for item in findings if item["knowledge_state"] in {"hypothesis", "observed", "correlated", "tested", "quarantined"}]
        rejected = [item for item in findings if item["knowledge_state"] == "rejected"]
        checkpoint["validation"] = {"total": len(findings), "validated": len(validated), "inconclusive": len(inconclusive), "rejected": len(rejected), "iterations": len(iterations), "validation_before_learning": True, "learning_eligible": len(validated), "causal_claim_without_evidence": False, "marketplace_writes": 0}

    async def build_report(self, mission: dict[str, Any]) -> tuple[dict[str, Any], str, float]:
        mission_id = mission["mission_id"]; findings = await self.repo.findings(mission_id); evidence = await self.repo.evidence(mission_id); exposures = await self.repo.exposures(50)
        plan_row = await self.repo.get_plan(mission_id); plan = (plan_row or {}).get("plan_json") or {}; iterations = await self.repo.iterations(mission_id)
        validated = [item for item in findings if item["knowledge_state"] == "validated"]; hypotheses = [item for item in findings if item["knowledge_state"] in {"hypothesis", "observed", "correlated", "tested", "quarantined"}]
        predictions: list[Any] = []; opportunities: list[Any] = []; threats: list[Any] = []; correlations: list[Any] = []; recommendations: list[Any] = []; counter_challenges: list[Any] = []
        for item in findings:
            data = item.get("finding_json") or {}; core_report = data.get("report") or {}; prediction = core_report.get("prediction") or {}; intelligence = core_report.get("intelligence") or {}; correlation = core_report.get("correlation") or {}; action_intent = core_report.get("action_intent") or {}
            if prediction: predictions.append({"statement": prediction.get("statement"), "confidence": prediction.get("confidence"), "state": prediction.get("state")})
            if intelligence.get("opportunity") and intelligence.get("summary"): opportunities.append({"summary": intelligence.get("summary"), "confidence": intelligence.get("confidence"), "severity": intelligence.get("severity")})
            if (intelligence.get("threat") or str(item.get("severity")).lower() in {"high", "critical"}) and (intelligence.get("summary") or data.get("summary")): threats.append({"summary": intelligence.get("summary") or data.get("summary"), "confidence": intelligence.get("confidence") or item.get("confidence"), "severity": intelligence.get("severity") or item.get("severity")})
            if correlation.get("related_signal_ids"): correlations.append({"reason": correlation.get("reason"), "strength": correlation.get("strength"), "related_signal_ids": correlation.get("related_signal_ids")})
            if action_intent.get("recommendation"): recommendations.append({"recommendation": action_intent.get("recommendation"), "reason": action_intent.get("rationale"), "evidence": intelligence.get("evidence") or [], "expected_impact": None, "confidence": intelligence.get("confidence"), "risk": action_intent.get("risk"), "unknowns": [h.get("statement") for h in core_report.get("hypotheses") or [] if isinstance(h, dict)][:5], "executed": False})
        for iteration in iterations:
            counter_challenges.extend((iteration.get("iteration_json") or {}).get("counterintelligence_objections") or [])
        confidence = _average_confidence(findings); stop_reason = iterations[-1].get("stop_reason") if iterations else "no_iteration"
        report = {
            "mission": {"mission_id": mission_id, "objective": mission["objective"], "origin": mission["origin"], "mission_type": mission["mission_type"], "thread_id": mission.get("thread_id") or mission_id, "root_mission_id": mission.get("root_mission_id") or mission_id, "parent_mission_id": mission.get("parent_mission_id"), "source_report_id": str(mission.get("source_report_id")) if mission.get("source_report_id") else None, "source_finding_id": str(mission.get("source_finding_id")) if mission.get("source_finding_id") else None, "follow_up_question": mission.get("follow_up_question"), "mode": mission.get("mode") or "standard"},
            "period": {"created_at": mission["created_at"].isoformat(), "reported_at": datetime.now(UTC).isoformat()}, "investigation_plan": plan,
            "cognitive_iterations": [{"iteration_count": item["iteration_count"], "evidence_gain": item["evidence_gain"], "confidence_change": item["confidence_change"], "open_questions": item["open_questions"], "stop_reason": item["stop_reason"]} for item in iterations],
            "conclusion": f"Objective-directed investigation considered {len(findings)} findings and {len(evidence)} persisted evidence records across {len(iterations)} cognitive iterations. Stop reason: {stop_reason}. Claims remain limited to observable and validated evidence.",
            "evidence": [{"id": str(item["id"]), "type": item["evidence_type"], "source": item["source"], "observed_at": item["observed_at"].isoformat(), "data": item["evidence_json"]} for item in evidence],
            "findings": [{"id": str(item["id"]), "type": item["finding_type"], "state": item["knowledge_state"], "severity": item["severity"], "confidence": item["confidence"], "data": item["finding_json"]} for item in findings],
            "correlations": correlations[:50], "hypotheses": [item["finding_json"] for item in hypotheses[:50]], "validated": [item["finding_json"] for item in validated[:50]], "not_proven": [item["finding_json"] for item in hypotheses[:50]],
            "counterintelligence": {"exposure_assessments": [{"data_point": item["data_point"], "platform_observes": item["platform_observes"], "possible_inferences": item["possible_inferences"], "risk_level": item["risk_level"], "mitigation": item["mitigation"]} for item in exposures], "challenge_objections": list(dict.fromkeys(str(x) for x in counter_challenges))[:30]},
            "predictions": predictions[:50], "opportunities": opportunities[:30], "threats": threats[:30],
            "recommendations": recommendations[:30] or [{"recommendation": "Continue sovereign read-only observation.", "reason": "No safe external action is authorized in this phase.", "evidence": [], "expected_impact": None, "confidence": confidence, "risk": "low", "unknowns": plan.get("missing_data") or [], "executed": False}],
            "confidence": confidence, "limitations": ["Only legitimately available data were considered.", "Correlation was not treated as causality.", "No external action was authorized in this mission."], "marketplace_action": "NENHUMA", "marketplace_actions_executed": 0, "marketplace_writes": 0,
        }
        return report, self.to_markdown(report), confidence

    @staticmethod
    def _report_severity(report: dict[str, Any]) -> str:
        levels = [str(item.get("severity") or "").lower() for item in report.get("findings") or []]
        if "critical" in levels: return "critical"
        if "high" in levels: return "high"
        if "medium" in levels: return "medium"
        return "info"

    @staticmethod
    def to_markdown(report: dict[str, Any]) -> str:
        def u(*points: int) -> str: return "".join(chr(value) for value in points)
        a_tilde = u(0x00C3); c_ced = u(0x00C7); e_circ = u(0x00CA); i_acute = u(0x00CD); o_acute = u(0x00D3); o_tilde = u(0x00D5)
        def block(title: str, value: Any) -> str:
            if isinstance(value, list): body = "\n".join("- " + json.dumps(item, ensure_ascii=False, default=str) for item in value) or "- Nenhum registro."
            elif isinstance(value, dict): body = json.dumps(value, ensure_ascii=False, default=str, indent=2)
            else: body = str(value)
            return "## " + title + "\n" + body + "\n"
        sections = [("MISS" + a_tilde + "O", report["mission"]), ("PER" + i_acute + "ODO", report["period"]), ("CONCLUS" + a_tilde + "O", report["conclusion"]), ("EVID" + e_circ + "NCIAS", report["evidence"]), ("DESCOBERTAS", report["findings"]), ("CORRELA" + c_ced + o_tilde + "ES", report["correlations"]), ("HIP" + o_acute + "TESES", report["hypotheses"]), ("O QUE FOI VALIDADO", report["validated"]), ("O QUE N" + a_tilde + "O FOI PROVADO", report["not_proven"]), ("CONTRAINTELIG" + e_circ + "NCIA", report["counterintelligence"]), ("PREVIS" + o_tilde + "ES", report["predictions"]), ("OPORTUNIDADES", report["opportunities"]), ("AMEA" + c_ced + "AS", report["threats"]), ("RECOMENDA" + c_ced + o_tilde + "ES", report["recommendations"]), ("CONFIAN" + c_ced + "A", report["confidence"]), ("LIMITA" + c_ced + o_tilde + "ES", report["limitations"]), ("A" + c_ced + a_tilde + "O EXECUTADA NO MARKETPLACE", "NENHUMA")]
        return "# RELAT" + o_acute + "RIO SOBERANO OPERACIONAL\n\n" + "\n".join(block(title, value) for title, value in sections)

    async def write_projection(self, mission: dict[str, Any], report: dict[str, Any], markdown: str) -> None:
        root = self.runtime_root / "missions" / mission["mission_id"]; root.mkdir(parents=True, exist_ok=True)
        current = await self.repo.get(mission["mission_id"]); evidence = await self.repo.evidence(mission["mission_id"]); findings = await self.repo.findings(mission["mission_id"]); plan = await self.repo.get_plan(mission["mission_id"]); iterations = await self.repo.iterations(mission["mission_id"])
        for name, payload in {"mission.json": mission, "status.json": current, "plan.json": plan, "iterations.json": iterations, "evidence.json": evidence, "findings.json": findings, "REPORT.json": report}.items():
            (root / name).write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        (root / "REPORT.md").write_text(markdown, encoding="utf-8")

    async def open_autonomous_from_radar(self, *, max_active: int = 4) -> None:
        if await self.repo.active_autonomous_count() >= max(1, int(max_active)): return
        for alert in await self.repo.autonomous_candidates(20):
            if await self.repo.radar_alert_already_missioned(str(alert["id"])): continue
            key = self.repo.autonomous_dedupe(alert, 6)
            request = MissionCreate(objective="Investigue autonomamente o sinal relevante detectado pelo Radar em " + str(alert["marketplace"]) + "/" + str(alert["entity_type"]) + ":" + str(alert["entity_id"]) + ": " + str(alert["observed_change"]) + ". Nao atribua causalidade sem evidencia.", origin=MissionOrigin.RADAR, mission_type=MissionType.AUTONOMOUS, marketplace_scope=(alert["marketplace"],), authority="radar_read_only", priority=80 if str(alert["severity"]).lower() == "critical" else 70)
            mission, created = await self.repo.create(request, dedupe_key=key)
            if created:
                await self.repo.add_evidence(mission["mission_id"], "radar_trigger", "radar", {"alert_id": str(alert["id"]), "severity": alert["severity"], "confidence": alert["confidence"], "detector_version": alert.get("detector_version"), "marketplace_writes": 0}, alert.get("created_at")); break
