from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.missions.models import (
    FollowUpCreate,
    MissionCreate,
    MissionOrigin,
    MissionType,
)
from market_intelligence.missions.planner import InvestigationPlan

ACTIVE_STATES = (
    "RECEIVED", "PLANNING", "COLLECTING", "CORRELATING", "INVESTIGATING",
    "VALIDATING", "REPORTING", "DEGRADED",
)


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _uuid(value: str | UUID | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(str(value))


class PostgresMissionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create(self, request: MissionCreate, *, dedupe_key: str | None = None, lineage: dict[str, Any] | None = None, mode: str = "standard") -> tuple[dict[str, Any], bool]:
        if request.authority not in {"owner_read_only", "system_read_only", "radar_read_only"}:
            raise PermissionError("mission_authority_rejected")
        if request.idempotency_key and not dedupe_key:
            dedupe_key = stable_hash({"directed": request.idempotency_key})
        mid = "MI-" + uuid4().hex[:20].upper()
        lineage = dict(lineage or {})
        thread_id = str(lineage.get("thread_id") or mid)
        root_mission_id = str(lineage.get("root_mission_id") or mid)
        parent_mission_id = lineage.get("parent_mission_id")
        source_report_id = _uuid(lineage.get("source_report_id"))
        source_finding_id = _uuid(lineage.get("source_finding_id"))
        follow_up_question = lineage.get("follow_up_question")
        async with self.sessions() as session:
            if dedupe_key:
                existing = (await session.execute(text("SELECT * FROM sovereign_missions WHERE dedupe_key=:k"), {"k": dedupe_key})).mappings().first()
                if existing:
                    return dict(existing), False
            result = await session.execute(text("""
                INSERT INTO sovereign_missions(
                    mission_id,dedupe_key,origin,objective,mission_type,marketplace_scope,
                    authority,priority,status,deadline_at,checkpoint,marketplace_writes,
                    thread_id,root_mission_id,parent_mission_id,source_report_id,
                    source_finding_id,follow_up_question,mode
                ) VALUES(
                    :id,:dk,:origin,:objective,:mtype,CAST(:scope AS jsonb),
                    :authority,:priority,'RECEIVED',:deadline,CAST(:cp AS jsonb),0,
                    :thread_id,:root_id,:parent_id,:report_id,:finding_id,:follow_up,:mode
                ) RETURNING *
            """), {
                "id": mid, "dk": dedupe_key, "origin": request.origin.value,
                "objective": request.objective, "mtype": request.mission_type.value,
                "scope": json.dumps(list(request.marketplace_scope)), "authority": request.authority,
                "priority": request.priority, "deadline": request.deadline_at,
                "cp": json.dumps({"last_safe_state": "RECEIVED", "marketplace_writes": 0}),
                "thread_id": thread_id, "root_id": root_mission_id, "parent_id": parent_mission_id,
                "report_id": source_report_id, "finding_id": source_finding_id,
                "follow_up": follow_up_question, "mode": mode,
            })
            row = dict(result.mappings().one())
            if parent_mission_id is None:
                await session.execute(text("""
                    INSERT INTO intelligence_threads(thread_id,root_mission_id,title,status)
                    VALUES(:tid,:root,:title,'ACTIVE') ON CONFLICT(thread_id) DO NOTHING
                """), {"tid": thread_id, "root": root_mission_id, "title": request.objective[:500]})
            else:
                await session.execute(text("UPDATE intelligence_threads SET updated_at=now() WHERE thread_id=:tid"), {"tid": thread_id})
            await session.commit()
            return row, True

    async def create_follow_up(self, parent_mission_id: str, follow_up: FollowUpCreate) -> tuple[dict[str, Any], bool]:
        parent = await self.get(parent_mission_id)
        if parent is None:
            raise KeyError("parent_mission_not_found")
        source_report = await self.get_report(parent_mission_id)
        dedupe_key = stable_hash({
            "parent": parent_mission_id, "question": follow_up.question.strip(),
            "mode": follow_up.mode.value, "source_finding_id": follow_up.source_finding_id,
        })
        request = MissionCreate(
            objective=follow_up.question, origin=MissionOrigin.GPT, mission_type=MissionType.DIRECTED,
            marketplace_scope=tuple(parent["marketplace_scope"]), authority="owner_read_only",
            priority=follow_up.priority,
        )
        lineage = {
            "thread_id": parent.get("thread_id") or parent_mission_id,
            "root_mission_id": parent.get("root_mission_id") or parent_mission_id,
            "parent_mission_id": parent_mission_id,
            "source_report_id": source_report.get("report_id") if source_report else None,
            "source_finding_id": follow_up.source_finding_id,
            "follow_up_question": follow_up.question,
        }
        mission, created = await self.create(request, dedupe_key=dedupe_key, lineage=lineage, mode=follow_up.mode.value)
        if created:
            await self.add_evidence(mission["mission_id"], "lineage_context", "mission_protocol", {
                "thread_id": lineage["thread_id"], "root_mission_id": lineage["root_mission_id"],
                "parent_mission_id": parent_mission_id,
                "source_report_id": str(lineage["source_report_id"]) if lineage["source_report_id"] else None,
                "source_finding_id": follow_up.source_finding_id, "follow_up_question": follow_up.question,
                "mode": follow_up.mode.value, "marketplace_writes": 0,
            })
        return mission, created

    async def get(self, mission_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("SELECT * FROM sovereign_missions WHERE mission_id=:id"), {"id": mission_id})).mappings().first()
            return dict(row) if row else None

    async def list(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.execute(text("SELECT * FROM sovereign_missions ORDER BY created_at DESC LIMIT :n"), {"n": limit})).mappings().all()
            return [dict(row) for row in rows]

    async def latest(self) -> dict[str, Any] | None:
        rows = await self.list(1)
        return rows[0] if rows else None

    async def claim_next(self) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("""
                SELECT * FROM sovereign_missions WHERE status=ANY(CAST(:states AS text[]))
                ORDER BY priority DESC,created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1
            """), {"states": list(ACTIVE_STATES)})).mappings().first()
            if not row:
                await session.rollback(); return None
            if row["started_at"] is None:
                await session.execute(text("UPDATE sovereign_missions SET started_at=now(),updated_at=now() WHERE mission_id=:id"), {"id": row["mission_id"]})
            await session.commit(); return dict(row)

    async def transition(self, mission_id: str, from_state: str, to_state: str, checkpoint: dict[str, Any]) -> bool:
        if int(checkpoint.get("marketplace_writes", 0)) != 0:
            raise RuntimeError("mission_checkpoint_write_boundary")
        async with self.sessions() as session:
            current = (await session.execute(text("SELECT status FROM sovereign_missions WHERE mission_id=:id FOR UPDATE"), {"id": mission_id})).scalar_one()
            if current != from_state:
                await session.rollback(); return False
            await session.execute(text("""
                INSERT INTO mission_steps(id,mission_id,step_key,state,status,attempt,checkpoint,completed_at)
                VALUES(:sid,:mid,:key,:state,'COMPLETED',1,CAST(:cp AS jsonb),now())
                ON CONFLICT(mission_id,step_key) DO NOTHING
            """), {"sid": uuid4(), "mid": mission_id, "key": from_state.lower(), "state": from_state, "cp": json.dumps(checkpoint, default=str)})
            completed = "now()" if to_state == "COMPLETED" else "NULL"
            await session.execute(text(f"""
                UPDATE sovereign_missions SET status=:to_state,checkpoint=CAST(:cp AS jsonb),updated_at=now(),
                    completed_at={completed},marketplace_writes=0 WHERE mission_id=:mid
            """), {"to_state": to_state, "cp": json.dumps(checkpoint, default=str), "mid": mission_id})
            await session.execute(text("UPDATE intelligence_threads SET updated_at=now() WHERE thread_id=(SELECT thread_id FROM sovereign_missions WHERE mission_id=:mid)"), {"mid": mission_id})
            await session.commit(); return True

    async def fail(self, mission_id: str, error_code: str) -> None:
        async with self.sessions() as session:
            await session.execute(text("""
                UPDATE sovereign_missions SET status=CASE WHEN retry_count<3 THEN 'DEGRADED' ELSE 'FAILED' END,
                    error_code=:err,retry_count=retry_count+1,updated_at=now(),marketplace_writes=0 WHERE mission_id=:mid
            """), {"err": error_code[:160], "mid": mission_id}); await session.commit()

    async def save_plan(self, mission_id: str, plan: InvestigationPlan) -> None:
        payload = plan.model_dump(mode="json")
        async with self.sessions() as session:
            await session.execute(text("""
                INSERT INTO mission_plans(id,mission_id,plan_version,objective_original,main_question,plan_json)
                VALUES(:id,:mid,:version,:objective,:question,CAST(:plan AS jsonb))
                ON CONFLICT(mission_id) DO UPDATE SET plan_version=EXCLUDED.plan_version,
                    objective_original=EXCLUDED.objective_original,main_question=EXCLUDED.main_question,
                    plan_json=EXCLUDED.plan_json,updated_at=now()
            """), {"id": uuid4(), "mid": mission_id, "version": plan.plan_version,
                    "objective": plan.objective_original, "question": plan.main_question,
                    "plan": json.dumps(payload, ensure_ascii=False)})
            await session.commit()

    async def get_plan(self, mission_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("SELECT plan_version,objective_original,main_question,plan_json,created_at,updated_at FROM mission_plans WHERE mission_id=:mid"), {"mid": mission_id})).mappings().first()
            return dict(row) if row else None

    async def add_evidence(self, mission_id: str, evidence_type: str, source: str, payload: dict[str, Any], observed_at: datetime | None = None) -> bool:
        observed_at = observed_at or datetime.now(UTC); dedupe_key = stable_hash({"t": evidence_type, "s": source, "p": payload})
        async with self.sessions() as session:
            result = await session.execute(text("""
                INSERT INTO mission_evidence(id,mission_id,dedupe_key,evidence_type,source,observed_at,evidence_json)
                VALUES(:id,:mid,:dk,:t,:src,:obs,CAST(:p AS jsonb))
                ON CONFLICT(mission_id,dedupe_key) DO NOTHING RETURNING id
            """), {"id": uuid4(), "mid": mission_id, "dk": dedupe_key, "t": evidence_type,
                    "src": source, "obs": observed_at, "p": json.dumps(payload, default=str, ensure_ascii=False)})
            inserted = result.scalar_one_or_none() is not None; await session.commit(); return inserted

    async def add_finding(self, mission_id: str, finding_type: str, knowledge_state: str, severity: str, confidence: float, payload: dict[str, Any]) -> bool:
        dedupe_key = stable_hash({"t": finding_type, "p": payload})
        async with self.sessions() as session:
            result = await session.execute(text("""
                INSERT INTO mission_findings(id,mission_id,dedupe_key,finding_type,knowledge_state,severity,confidence,finding_json)
                VALUES(:id,:mid,:dk,:t,:ks,:sev,:c,CAST(:p AS jsonb))
                ON CONFLICT(mission_id,dedupe_key) DO NOTHING RETURNING id
            """), {"id": uuid4(), "mid": mission_id, "dk": dedupe_key, "t": finding_type,
                    "ks": knowledge_state, "sev": severity, "c": max(0, min(1, float(confidence))),
                    "p": json.dumps(payload, default=str, ensure_ascii=False)})
            inserted = result.scalar_one_or_none() is not None; await session.commit(); return inserted

    async def findings(self, mission_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.execute(text("""
                SELECT id,dedupe_key,finding_type,knowledge_state,severity,confidence,finding_json,created_at
                FROM mission_findings WHERE mission_id=:mid ORDER BY created_at,id
            """), {"mid": mission_id})).mappings().all(); return [dict(row) for row in rows]

    async def evidence(self, mission_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.execute(text("""
                SELECT id,dedupe_key,evidence_type,source,observed_at,evidence_json,created_at
                FROM mission_evidence WHERE mission_id=:mid ORDER BY observed_at,id
            """), {"mid": mission_id})).mappings().all(); return [dict(row) for row in rows]

    async def data_inventory(self) -> dict[str, int]:
        names = ("snapshots", "channel_events", "raw_events", "sovereign_intelligence", "exposure_map", "learning_episodes", "investigation_cases", "investigation_events")
        async with self.sessions() as session:
            result: dict[str, int] = {}
            for name in names:
                result[name] = int((await session.execute(text(f"SELECT count(*) FROM {name}"))).scalar_one())
            return result

    async def targeted_sovereign(self, plan: dict[str, Any], *, since: datetime | None, limit: int = 500) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = "SELECT * FROM sovereign_intelligence"; params: dict[str, Any] = {"n": max(limit * 4, 1000)}
            if since is not None:
                query += " WHERE observed_at>=:since"; params["since"] = since
            query += " ORDER BY observed_at DESC LIMIT :n"
            rows = [dict(row) for row in (await session.execute(text(query), params)).mappings().all()]
        families = set(plan.get("signal_families") or [])
        if len(families) >= 12:
            return rows[:limit]
        terms = [str(term).lower() for term in plan.get("signal_terms") or []]
        selected: list[dict[str, Any]] = []
        for row in rows:
            haystack = " ".join((str(row.get("signal_kind") or ""), str(row.get("entity_type") or ""), str(row.get("summary") or ""), json.dumps(row.get("report_json") or {}, ensure_ascii=False, default=str))).lower()
            if any(term in haystack for term in terms):
                selected.append(row)
                if len(selected) >= limit: break
        return selected

    async def recent_sovereign(self, since: datetime | None, limit: int = 200) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = "SELECT * FROM sovereign_intelligence"; params: dict[str, Any] = {"n": limit}
            if since is not None:
                query += " WHERE observed_at>=:since"; params["since"] = since
            query += " ORDER BY observed_at DESC LIMIT :n"
            return [dict(row) for row in (await session.execute(text(query), params)).mappings().all()]

    async def exposures(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [dict(row) for row in (await session.execute(text("SELECT * FROM exposure_map ORDER BY last_observed_at DESC LIMIT :n"), {"n": limit})).mappings().all()]

    async def save_iteration(self, mission_id: str, *, iteration_count: int, status: str, evidence_gain: int, confidence_before: float, confidence_after: float, open_questions: list[str], stop_reason: str | None, payload: dict[str, Any]) -> None:
        if int(payload.get("marketplace_writes", 0)) != 0:
            raise RuntimeError("mission_iteration_write_boundary")
        confidence_change = float(confidence_after) - float(confidence_before)
        async with self.sessions() as session:
            await session.execute(text("""
                INSERT INTO mission_iterations(id,mission_id,iteration_count,status,evidence_gain,confidence_before,
                    confidence_after,confidence_change,open_questions,stop_reason,iteration_json,marketplace_writes)
                VALUES(:id,:mid,:iteration,:status,:gain,:before,:after,:change,CAST(:questions AS jsonb),:stop,CAST(:payload AS jsonb),0)
                ON CONFLICT(mission_id,iteration_count) DO UPDATE SET status=EXCLUDED.status,evidence_gain=EXCLUDED.evidence_gain,
                    confidence_before=EXCLUDED.confidence_before,confidence_after=EXCLUDED.confidence_after,
                    confidence_change=EXCLUDED.confidence_change,open_questions=EXCLUDED.open_questions,
                    stop_reason=EXCLUDED.stop_reason,iteration_json=EXCLUDED.iteration_json,marketplace_writes=0,completed_at=now()
            """), {"id": uuid4(), "mid": mission_id, "iteration": iteration_count, "status": status,
                    "gain": max(0, int(evidence_gain)), "before": max(0.0, min(1.0, float(confidence_before))),
                    "after": max(0.0, min(1.0, float(confidence_after))), "change": confidence_change,
                    "questions": json.dumps(open_questions, ensure_ascii=False), "stop": stop_reason,
                    "payload": json.dumps(payload, default=str, ensure_ascii=False)})
            await session.commit()

    async def iterations(self, mission_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (await session.execute(text("""
                SELECT iteration_count,status,evidence_gain,confidence_before,confidence_after,confidence_change,
                    open_questions,stop_reason,iteration_json,marketplace_writes,started_at,completed_at
                FROM mission_iterations WHERE mission_id=:mid ORDER BY iteration_count
            """), {"mid": mission_id})).mappings().all(); return [dict(row) for row in rows]

    async def latest_learning(self) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("""
                SELECT id,marketplace,entity_type,entity_id,state,confidence,observation_count,
                    official_resource_fetched,causal_claim,reason,created_at,updated_at
                FROM learning_episodes WHERE state='validated_fact' ORDER BY updated_at DESC LIMIT 1
            """))).mappings().first(); return dict(row) if row else None

    async def save_report(self, mission_id: str, report: dict[str, Any], markdown: str, confidence: float) -> UUID:
        async with self.sessions() as session:
            report_id = (await session.execute(text("""
                INSERT INTO mission_reports(id,mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes)
                VALUES(:id,:mid,'mission-report@1.1.0',CAST(:r AS jsonb),:md,:c,0)
                ON CONFLICT(mission_id) DO UPDATE SET report_version='mission-report@1.1.0',report_json=EXCLUDED.report_json,
                    report_markdown=EXCLUDED.report_markdown,confidence=EXCLUDED.confidence,marketplace_writes=0,created_at=now()
                RETURNING id
            """), {"id": uuid4(), "mid": mission_id, "r": json.dumps(report, default=str, ensure_ascii=False),
                    "md": markdown, "c": max(0, min(1, float(confidence))) })).scalar_one()
            await session.commit(); return report_id

    async def get_report(self, mission_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("""
                SELECT id AS report_id,mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes,created_at
                FROM mission_reports WHERE mission_id=:mid
            """), {"mid": mission_id})).mappings().first(); return dict(row) if row else None

    async def latest_report(self) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("""
                SELECT id AS report_id,mission_id,report_version,report_json,report_markdown,confidence,marketplace_writes,created_at
                FROM mission_reports ORDER BY created_at DESC LIMIT 1
            """))).mappings().first(); return dict(row) if row else None

    async def upsert_inbox(self, *, mission: dict[str, Any], report_id: UUID, severity: str, title: str, summary: str, confidence: float) -> UUID:
        async with self.sessions() as session:
            inbox_id = (await session.execute(text("""
                INSERT INTO intelligence_inbox(id,mission_id,report_id,thread_id,status,severity,title,summary,confidence,marketplace_writes)
                VALUES(:id,:mid,:rid,:tid,'UNREAD',:severity,:title,:summary,:confidence,0)
                ON CONFLICT(report_id) DO UPDATE SET severity=EXCLUDED.severity,title=EXCLUDED.title,
                    summary=EXCLUDED.summary,confidence=EXCLUDED.confidence,marketplace_writes=0 RETURNING id
            """), {"id": uuid4(), "mid": mission["mission_id"], "rid": report_id,
                    "tid": mission.get("thread_id") or mission["mission_id"], "severity": severity,
                    "title": title, "summary": summary, "confidence": max(0.0, min(1.0, float(confidence))) })).scalar_one()
            await session.commit(); return inbox_id

    async def inbox(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = "SELECT id,mission_id,report_id,thread_id,status,severity,title,summary,confidence,marketplace_writes,created_at,read_at,acknowledged_at FROM intelligence_inbox"
            params: dict[str, Any] = {"n": limit}
            if status:
                query += " WHERE status=:status"; params["status"] = status
            query += " ORDER BY created_at DESC LIMIT :n"
            return [dict(row) for row in (await session.execute(text(query), params)).mappings().all()]

    async def mark_inbox_read(self, inbox_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (await session.execute(text("""
                UPDATE intelligence_inbox SET status=CASE WHEN status='ACKNOWLEDGED' THEN status ELSE 'READ' END,
                    read_at=COALESCE(read_at,now()),marketplace_writes=0 WHERE id=:id
                RETURNING id,mission_id,report_id,thread_id,status,severity,title,summary,confidence,marketplace_writes,created_at,read_at,acknowledged_at
            """), {"id": _uuid(inbox_id)})).mappings().first(); await session.commit(); return dict(row) if row else None

    async def thread(self, thread_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            thread = (await session.execute(text("SELECT * FROM intelligence_threads WHERE thread_id=:tid"), {"tid": thread_id})).mappings().first()
            if not thread: return None
            missions = [dict(row) for row in (await session.execute(text("SELECT * FROM sovereign_missions WHERE thread_id=:tid ORDER BY created_at"), {"tid": thread_id})).mappings().all()]
            reports = [dict(row) for row in (await session.execute(text("""
                SELECT r.id AS report_id,r.mission_id,r.report_version,r.confidence,r.marketplace_writes,r.created_at
                FROM mission_reports r JOIN sovereign_missions m ON m.mission_id=r.mission_id
                WHERE m.thread_id=:tid ORDER BY r.created_at
            """), {"tid": thread_id})).mappings().all()]
            return {"thread": dict(thread), "missions": missions, "reports": reports}

    async def timeline(self, mission_id: str) -> dict[str, Any]:
        mission = await self.get(mission_id)
        if mission is None: raise KeyError("mission_not_found")
        return {"mission": mission, "steps": await self.steps(mission_id), "iterations": await self.iterations(mission_id), "report": await self.get_report(mission_id)}

    async def executive_brief(self, *, unread_only: bool = False) -> dict[str, Any]:
        items = await self.inbox(status="UNREAD" if unread_only else None, limit=20)
        report_rows: list[dict[str, Any]] = []
        for item in items[:8]:
            report = await self.get_report(item["mission_id"])
            if report: report_rows.append(report)
        if not report_rows:
            latest = await self.latest_report()
            if latest: report_rows = [latest]
        threats: list[Any] = []; opportunities: list[Any] = []; hypotheses: list[Any] = []; predictions: list[Any] = []
        validated: list[Any] = []; evidence: list[Any] = []; unknowns: list[Any] = []; recommended_questions: list[str] = []; recommendations: list[Any] = []
        for report_row in report_rows:
            report = report_row.get("report_json") or {}
            threats.extend(report.get("threats") or []); opportunities.extend(report.get("opportunities") or [])
            hypotheses.extend(report.get("hypotheses") or []); predictions.extend(report.get("predictions") or [])
            validated.extend(report.get("validated") or []); evidence.extend(report.get("evidence") or [])
            unknowns.extend(report.get("not_proven") or []); recommendations.extend(report.get("recommendations") or [])
            recommended_questions.extend((report.get("investigation_plan") or {}).get("possible_deepenings") or [])
        health = await self.health()
        return {
            "version": "executive-brief@1.0.0",
            "what_changed_since_last_read": [{"inbox_id": str(item["id"]), "mission_id": item["mission_id"], "thread_id": item["thread_id"], "severity": item["severity"], "title": item["title"], "summary": item["summary"], "confidence": item["confidence"], "created_at": item["created_at"]} for item in items],
            "top_threats": threats[:10], "top_opportunities": opportunities[:10], "investigations_in_progress": health["missions_running"],
            "validated_findings": validated[:20], "relevant_hypotheses": hypotheses[:20], "predictions": predictions[:20],
            "confidence": max((float(row.get("confidence") or 0) for row in report_rows), default=0.0),
            "key_evidence": evidence[:20], "what_we_do_not_know": unknowns[:20],
            "recommended_questions": list(dict.fromkeys(recommended_questions))[:12], "recommended_actions": recommendations[:12],
            "marketplace_actions_executed": 0, "marketplace_writes": 0,
        }

    async def intelligence_context(self) -> dict[str, Any]:
        health = await self.health(); recent = await self.list(10); unread = await self.inbox(status="UNREAD", limit=20)
        latest_report = await self.latest_report(); brief = await self.executive_brief(unread_only=True)
        async with self.sessions() as session:
            open_investigations = [dict(row) for row in (await session.execute(text("""
                SELECT id,marketplace,entity_type,entity_id,status,confidence,hypotheses,recommended_action,updated_at
                FROM investigation_cases WHERE status IN ('open','monitoring','confirmed') ORDER BY updated_at DESC LIMIT 20
            """))).mappings().all()]
            missions_in_progress = [dict(row) for row in (await session.execute(text("""
                SELECT * FROM sovereign_missions WHERE status=ANY(CAST(:states AS text[]))
                ORDER BY priority DESC,created_at ASC LIMIT 20
            """), {"states": list(ACTIVE_STATES)})).mappings().all()]
            recent_completed_missions = [dict(row) for row in (await session.execute(text("""
                SELECT * FROM sovereign_missions WHERE status='COMPLETED'
                ORDER BY completed_at DESC NULLS LAST LIMIT 10
            """))).mappings().all()]
        active_threads = []; seen: set[str] = set()
        for mission in recent:
            tid = str(mission.get("thread_id") or mission["mission_id"])
            if tid not in seen:
                seen.add(tid); active_threads.append({"thread_id": tid, "root_mission_id": mission.get("root_mission_id") or mission["mission_id"], "latest_mission_id": mission["mission_id"], "objective": mission["objective"], "status": mission["status"]})
        next_questions = brief.get("recommended_questions") or ["Quais sinais relevantes ainda estao sem explicacao?", "Que evidencia nova pode aumentar ou reduzir a confianca das conclusoes atuais?"]
        return {
            "version": "intelligence-context@1.0.0",
            "last_version": {"context": "intelligence-context@1.0.0", "schema": health.get("alembic_head")},
            "health": {**health, "marketplace_writes": 0},
            "missions_in_progress": missions_in_progress, "recent_completed_missions": recent_completed_missions,
            "recent_missions": recent, "open_investigations": open_investigations, "unread_items": unread, "unread_count": len(unread),
            "latest_report": latest_report, "active_threads": active_threads, "top_threats": brief.get("top_threats") or [],
            "top_opportunities": brief.get("top_opportunities") or [], "important_unresolved_hypotheses": brief.get("relevant_hypotheses") or [],
            "latest_validated_learning": await self.latest_learning(), "recommended_questions": next_questions,
            "suggested_next_step": next_questions[0], "marketplace_writes": 0,
        }

    async def health(self) -> dict[str, Any]:
        async with self.sessions() as session:
            rows = (await session.execute(text("SELECT status,count(*) n FROM sovereign_missions GROUP BY status"))).mappings().all(); counts = {row["status"]: int(row["n"]) for row in rows}
            last = (await session.execute(text("SELECT mission_id FROM sovereign_missions WHERE status='COMPLETED' ORDER BY completed_at DESC NULLS LAST LIMIT 1"))).scalar_one_or_none()
            report_at = (await session.execute(text("SELECT created_at FROM mission_reports ORDER BY created_at DESC LIMIT 1"))).scalar_one_or_none()
            unread = int((await session.execute(text("SELECT count(*) FROM intelligence_inbox WHERE status='UNREAD'"))).scalar_one())
            alembic_head = str((await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one())
            running = sum(counts.get(state, 0) for state in ACTIVE_STATES if state != "RECEIVED")
            return {"counts": counts, "missions_running": running, "missions_pending": counts.get("RECEIVED", 0), "last_completed_mission": last, "last_report_at": report_at, "intelligence_inbox_unread": unread, "alembic_head": alembic_head}

    async def steps(self, mission_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [dict(row) for row in (await session.execute(text("SELECT step_key,state,status,attempt,checkpoint,started_at,completed_at,error_code FROM mission_steps WHERE mission_id=:mid ORDER BY started_at"), {"mid": mission_id})).mappings().all()]

    async def autonomous_candidates(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [dict(row) for row in (await session.execute(text("SELECT id,marketplace,entity_type,entity_id,observed_change,severity,confidence,detector_version,created_at FROM alerts WHERE severity IN ('high','critical') ORDER BY created_at DESC LIMIT :n"), {"n": limit})).mappings().all()]

    async def radar_alert_already_missioned(self, alert_id: str) -> bool:
        async with self.sessions() as session:
            count = int((await session.execute(text("SELECT count(*) FROM mission_evidence WHERE evidence_type='radar_trigger' AND evidence_json->>'alert_id'=:alert_id"), {"alert_id": alert_id})).scalar_one()); return count > 0

    async def active_autonomous_count(self) -> int:
        async with self.sessions() as session:
            return int((await session.execute(text("SELECT count(*) FROM sovereign_missions WHERE mission_type='AUTONOMOUS' AND status=ANY(CAST(:states AS text[]))"), {"states": list(ACTIVE_STATES)})).scalar_one())

    @staticmethod
    def autonomous_dedupe(alert: dict[str, Any], cooldown_hours: int = 6) -> str:
        dt = alert.get("created_at") or datetime.now(UTC)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=UTC)
        bucket = int(dt.timestamp() // (cooldown_hours * 3600))
        return stable_hash({"m": alert.get("marketplace"), "et": alert.get("entity_type"), "eid": alert.get("entity_id"), "d": alert.get("detector_version"), "b": bucket})
