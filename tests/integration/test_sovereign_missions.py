from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from market_intelligence.core.contracts import Alert, EntityRef, Evidence, EvidenceLevel, Severity
from market_intelligence.missions.models import (
    MissionCreate,
    MissionOrigin,
    MissionState,
    MissionType,
)
from market_intelligence.missions.orchestrator import SovereignMissionOrchestrator
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_mission_protocol_persistence_idempotency_recovery_report_concurrency_and_autonomous(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")

    async def scenario() -> None:
        engine=create_database_engine(url); sessions=create_session_factory(engine); repo=PostgresMissionRepository(sessions)
        orchestrator=SovereignMissionOrchestrator(repo,url,tmp_path,0)
        try:
            run_key=uuid4().hex
            req=MissionCreate(objective="Investigate a controlled read-only marketplace signal for protocol proof.",origin=MissionOrigin.GPT,mission_type=MissionType.DIRECTED,idempotency_key=f"mission-protocol-{run_key}")
            first,created=await repo.create(req); assert created is True
            duplicate,created2=await repo.create(req); assert created2 is False and duplicate["mission_id"]==first["mission_id"]
            for _ in range(20):
                item=await repo.get(first["mission_id"]); assert item is not None
                if item["status"]=="COMPLETED": break
                await orchestrator.advance(item)
            item=await repo.get(first["mission_id"]); assert item and item["status"]=="COMPLETED" and item["marketplace_writes"]==0
            steps=await repo.steps(first["mission_id"]); assert [s["state"] for s in steps]==["RECEIVED","PLANNING","COLLECTING","CORRELATING","INVESTIGATING","VALIDATING","REPORTING"]
            assert all(s["attempt"]==1 for s in steps)
            report=await repo.get_report(first["mission_id"]); assert report and report["marketplace_writes"]==0 and report["report_json"]["marketplace_action"]=="NENHUMA"
            root=tmp_path/"missions"/first["mission_id"]
            for name in ("mission.json","status.json","evidence.json","findings.json","REPORT.json","REPORT.md"): assert (root/name).exists()
            md=(root/"REPORT.md").read_text(encoding="utf-8")
            expected_mission="MISS"+chr(0x00C3)+"O"
            expected_action="A"+chr(0x00C7)+chr(0x00C3)+"O EXECUTADA NO MARKETPLACE"
            assert expected_mission in md and expected_action in md and "NENHUMA" in md

            recovery,_=await repo.create(MissionCreate(objective="Recovery mission must resume from persisted checkpoint.",origin=MissionOrigin.SYSTEM,mission_type=MissionType.DIRECTED,idempotency_key=f"mission-recovery-{run_key}",authority="system_read_only"))
            await orchestrator.advance(recovery)
            restarted=SovereignMissionOrchestrator(repo,url,tmp_path,0)
            for _ in range(20):
                current=await repo.get(recovery["mission_id"]); assert current
                if current["status"]=="COMPLETED": break
                await restarted.advance(current)
            current=await repo.get(recovery["mission_id"]); assert current and current["status"]=="COMPLETED"
            recovery_steps=await repo.steps(recovery["mission_id"]); assert len({s["step_key"] for s in recovery_steps})==len(recovery_steps) and all(s["attempt"]==1 for s in recovery_steps)

            async def make(i:int):
                return await repo.create(MissionCreate(objective=f"Concurrent mission proof number {i} with read-only authority.",origin=MissionOrigin.SYSTEM,mission_type=MissionType.DIRECTED,idempotency_key=f"concurrency-{uuid4().hex}-{i}",authority="system_read_only"))
            many=await asyncio.gather(*(make(i) for i in range(8))); assert len({x[0]["mission_id"] for x in many})==8

            entity_id="AUTO-"+uuid4().hex
            alert=Alert(entity=EntityRef(marketplace="mercadolivre",entity_type="item",entity_id=entity_id),observed_change="synthetic sovereign autonomous anomaly",evidence=[Evidence(level=EvidenceLevel.FACT,statement="synthetic controlled radar evidence",source="test:mission-autonomous",observed_at=datetime.now(UTC))],severity=Severity.HIGH,confidence=0.96,detector_version="mission-autonomous-test@1.0.0")
            assert await PostgresAlertRepository(sessions).save_if_new(alert) is True
            await orchestrator.open_autonomous_from_radar(max_active=1000); await orchestrator.open_autonomous_from_radar(max_active=1000)
            related=Alert(entity=EntityRef(marketplace="mercadolivre",entity_type="item",entity_id=entity_id),observed_change="synthetic related autonomous signal",evidence=[Evidence(level=EvidenceLevel.FACT,statement="second controlled radar evidence",source="test:mission-autonomous",observed_at=datetime.now(UTC))],severity=Severity.HIGH,confidence=0.94,detector_version="mission-autonomous-test@1.0.0")
            assert await PostgresAlertRepository(sessions).save_if_new(related) is True
            await orchestrator.open_autonomous_from_radar(max_active=1000); await orchestrator.open_autonomous_from_radar(max_active=1000)
            missions=await repo.list(200); matching=[m for m in missions if m["mission_type"]=="AUTONOMOUS" and entity_id in m["objective"]]
            assert len(matching)==1 and matching[0]["origin"]=="RADAR" and matching[0]["marketplace_writes"]==0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_mission_state_contract_and_security(monkeypatch) -> None:
    expected={"RECEIVED","PLANNING","COLLECTING","CORRELATING","INVESTIGATING","VALIDATING","REPORTING","COMPLETED","BLOCKED","DEGRADED","FAILED","CANCELLED"}
    assert {x.value for x in MissionState}==expected
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","1")
    with pytest.raises(RuntimeError,match="marketplace_writes_nonzero"): SovereignMissionOrchestrator.assert_security()

    now=datetime.now(UTC)
    base={"marketplace":"mercadolivre","entity_type":"item","entity_id":"MLB-GROUP","detector_version":"group-test@1","created_at":now}
    related_a={**base,"observed_change":"visits dropped"}
    related_b={**base,"observed_change":"conversion changed"}
    other={**base,"entity_id":"MLB-OTHER","observed_change":"visits dropped"}
    assert PostgresMissionRepository.autonomous_dedupe(related_a)==PostgresMissionRepository.autonomous_dedupe(related_b)
    assert PostgresMissionRepository.autonomous_dedupe(related_a)!=PostgresMissionRepository.autonomous_dedupe(other)


def test_powershell_client_is_api_only() -> None:
    content=open("scripts/MIMission.psm1",encoding="utf-8-sig").read()
    for name in ("Invoke-MIMission","Get-MIMission","Get-MIReport","Get-MIHealth"): assert f"function {name}" in content
    assert "Invoke-RestMethod" in content
    assert "psql" not in content.lower() and "SELECT * FROM sovereign_missions" not in content
