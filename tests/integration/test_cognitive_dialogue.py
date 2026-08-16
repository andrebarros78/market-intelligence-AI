from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from market_intelligence.missions.models import (
    FollowUpCreate,
    FollowUpMode,
    MissionCreate,
    MissionOrigin,
    MissionType,
)
from market_intelligence.missions.orchestrator import SovereignMissionOrchestrator
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory


def _assert_zero_writes(*items: dict) -> None:
    for item in items:
        assert int(item.get("marketplace_writes", 0)) == 0


@pytest.mark.postgres
def test_cognitive_dialogue_lineage_inbox_context_and_objective_direction(tmp_path, monkeypatch) -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    monkeypatch.setenv("MARKETPLACE_WRITES", "0")

    async def scenario() -> None:
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        repo = PostgresMissionRepository(sessions)
        orchestrator = SovereignMissionOrchestrator(repo, url, tmp_path, 0)
        try:
            # Seed two sanitized sovereign records so objective-directed selection is observable.
            now = datetime.now(UTC)
            async with sessions() as session:
                for signal_kind, summary in (
                    ("sales_drop", "observable sold quantity decline"),
                    ("schema_surface_change", "observable response schema field change"),
                ):
                    key = uuid4().hex + uuid4().hex
                    await session.execute(text("""
                        INSERT INTO sovereign_intelligence(
                            id,dedupe_key,marketplace,entity_type,entity_id,signal_kind,knowledge_state,
                            severity,confidence,summary,report_json,observed_at
                        ) VALUES(:id,:dk,'mercadolivre','listing',:entity,:kind,'observed','medium',0.72,:summary,CAST(:report AS jsonb),:observed)
                    """), {
                        "id": uuid4(), "dk": key[:64], "entity": "TEST-" + uuid4().hex[:12],
                        "kind": signal_kind, "summary": summary,
                        "report": '{"validation":{"state":"observed","reason":"test_observation"},"hypotheses":[],"audit":{"passed":true}}',
                        "observed": now,
                    })
                await session.commit()

            root, created = await repo.create(MissionCreate(
                objective="Investigue por que as vendas caíram hoje",
                origin=MissionOrigin.GPT,
                mission_type=MissionType.DIRECTED,
                idempotency_key="cognitive-dialogue-" + uuid4().hex,
            ))
            assert created is True
            for _ in range(30):
                mission = await repo.get(root["mission_id"]); assert mission
                if mission["status"] == "COMPLETED": break
                await orchestrator.advance(mission)
            root = await repo.get(root["mission_id"]); assert root and root["status"] == "COMPLETED"
            _assert_zero_writes(root)

            plan_row = await repo.get_plan(root["mission_id"]); assert plan_row
            plan = plan_row["plan_json"]
            assert "sales" in plan["signal_families"] and "visits" in plan["signal_families"]
            findings = await repo.findings(root["mission_id"])
            summaries = " ".join(str((f["finding_json"] or {}).get("summary") or "") for f in findings)
            assert "sold quantity decline" in summaries
            assert "response schema field change" not in summaries

            iterations = await repo.iterations(root["mission_id"])
            assert 1 <= len(iterations) <= 3
            assert iterations[-1]["stop_reason"] in {"evidence_saturation", "max_safe_iterations", "legitimate_evidence_exhausted"}
            assert all(int(row["marketplace_writes"]) == 0 for row in iterations)
            assert all((row["iteration_json"] or {}).get("validation_before_learning") is True for row in iterations)
            assert all((row["iteration_json"] or {}).get("learning_eligible_findings", 0) >= 0 for row in iterations)
            assert any((row["iteration_json"] or {}).get("instigator_questions") for row in iterations)
            assert any((row["iteration_json"] or {}).get("counterintelligence_objections") for row in iterations)

            report = await repo.get_report(root["mission_id"]); assert report
            _assert_zero_writes(report)
            assert report["report_json"]["marketplace_actions_executed"] == 0
            inbox = await repo.inbox(status="UNREAD", limit=50)
            root_inbox = [item for item in inbox if item["mission_id"] == root["mission_id"]]
            assert len(root_inbox) == 1
            marked = await repo.mark_inbox_read(str(root_inbox[0]["id"])); assert marked and marked["status"] == "READ"

            follow, follow_created = await repo.create_follow_up(root["mission_id"], FollowUpCreate(
                question="Aprofunde especificamente a queda de vendas e procure evidência contrária.",
                mode=FollowUpMode.DEEPEN,
            ))
            assert follow_created is True
            for _ in range(30):
                item = await repo.get(follow["mission_id"]); assert item
                if item["status"] == "COMPLETED": break
                await orchestrator.advance(item)
            follow = await repo.get(follow["mission_id"]); assert follow and follow["status"] == "COMPLETED"
            assert follow["parent_mission_id"] == root["mission_id"]
            assert follow["root_mission_id"] == root["mission_id"]
            assert follow["thread_id"] == root["thread_id"]
            assert follow["source_report_id"] == report["report_id"]

            challenge, challenge_created = await repo.create_follow_up(follow["mission_id"], FollowUpCreate(
                question="Tente derrubar esta conclusão. Procure explicações alternativas, evidência contrária e lacunas.",
                mode=FollowUpMode.CHALLENGE,
            ))
            assert challenge_created is True
            for _ in range(30):
                item = await repo.get(challenge["mission_id"]); assert item
                if item["status"] == "COMPLETED": break
                await orchestrator.advance(item)
            challenge = await repo.get(challenge["mission_id"]); assert challenge and challenge["status"] == "COMPLETED"
            assert challenge["parent_mission_id"] == follow["mission_id"]
            assert challenge["root_mission_id"] == root["mission_id"]
            assert challenge["thread_id"] == root["thread_id"]
            challenge_iterations = await repo.iterations(challenge["mission_id"])
            text_blob = " ".join(" ".join((row["iteration_json"] or {}).get("counterintelligence_objections") or []) for row in challenge_iterations).lower()
            assert "derrubar" in text_blob and "correlacao" in text_blob

            thread = await repo.thread(root["thread_id"]); assert thread
            assert len(thread["missions"]) == 3
            assert len(thread["reports"]) == 3
            timeline = await repo.timeline(challenge["mission_id"])
            assert timeline["mission"]["thread_id"] == root["thread_id"]
            assert len(timeline["steps"]) == 7
            assert len({row["step_key"] for row in timeline["steps"]}) == 7

            brief = await repo.executive_brief(unread_only=False)
            assert brief["marketplace_actions_executed"] == 0 and brief["marketplace_writes"] == 0
            context = await repo.intelligence_context()
            assert context["marketplace_writes"] == 0
            assert context["health"]["marketplace_writes"] == 0
            assert "missions_in_progress" in context
            assert context["recent_completed_missions"]
            assert context["last_version"]["schema"] == "0012_continuous_evolution"
            assert context["active_threads"]
            assert context["recommended_questions"]
            assert context["suggested_next_step"]
            assert any(item["thread_id"] == root["thread_id"] for item in context["active_threads"])
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cognitive_clients_are_api_only_and_export_conversational_contract() -> None:
    content = open("scripts/MIMission.psm1", encoding="utf-8-sig").read()
    for name in (
        "Invoke-MIMission", "Invoke-MIFollowUp", "Get-MIMission", "Get-MIReport", "Get-MIHealth",
        "Get-MIBrief", "Get-MIInbox", "Get-MIContext", "Get-MIEvidence", "Get-MIThread",
    ):
        assert f"function {name}" in content
    assert "Invoke-RestMethod" in content
    lowered = content.lower()
    assert "psql" not in lowered
    assert "select * from sovereign_missions" not in lowered


def test_powershell_json_post_uses_utf8_stringcontent() -> None:
    content = open("scripts/MIMission.psm1", encoding="utf-8-sig").read()
    assert "System.Net.Http.StringContent" in content
    assert "System.Text.Encoding]::UTF8" in content
    assert "UTF8.GetBytes($body)" not in content


def test_powershell_list_endpoints_explicitly_enumerate_results() -> None:
    content = open("scripts/MIMission.psm1", encoding="utf-8-sig").read()
    assert content.count("$result | ForEach-Object { Write-Output $_ }") >= 2
