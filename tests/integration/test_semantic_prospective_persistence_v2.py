from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.missions.evolution import ContinuousEvolutionEngine
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory


@pytest.mark.postgres
def test_forecast_persists_but_abstention_never_enters_prediction_accounting(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        forecast_id=uuid4(); abstain_id=uuid4(); now=datetime.now(UTC); observed=now-timedelta(minutes=1)
        contract={"prediction_type":"FORECAST","statement":"visits deve aumentar prospectivamente","confidence":0.7,"horizon":"15m_prospective","leading_indicators":["trend"],"falsifier":"visits nao aumenta na janela","state":"tested","abstention_reason":None,"target_entity":"MLB-V2-INTEGRATION","target_metric":"visits","operator":"INCREASE","expected_value":None,"expected_direction":"UP","baseline_value":100,"baseline_source":"universal_sensor_snapshot:visits","baseline_observed_at":observed.isoformat(),"tolerance":1.0,"evaluation_window":{"start_at":now.isoformat(),"end_at":(now+timedelta(minutes=15)).isoformat()},"evidence_source":"snapshots:visits","created_at":now.isoformat()}
        abstain={"prediction_type":"ABSTAIN","statement":"ABSTAIN: evidencia insuficiente","confidence":0.2,"horizon":"none","leading_indicators":[],"falsifier":"not_applicable_abstention","state":"observed","abstention_reason":"insufficient_evidence","target_entity":None,"target_metric":None,"operator":None,"expected_value":None,"expected_direction":None,"baseline_value":None,"baseline_source":None,"baseline_observed_at":None,"tolerance":None,"evaluation_window":None,"evidence_source":None,"created_at":now.isoformat()}
        try:
            async with sessions() as session:
                for sid,pred,entity in ((forecast_id,contract,"MLB-V2-INTEGRATION"),(abstain_id,abstain,"MLB-V2-ABSTAIN")):
                    report={"signal":{"source":"universal_sensor_snapshot"},"prediction":pred}
                    await session.execute(text("""INSERT INTO sovereign_intelligence(id,dedupe_key,marketplace,entity_type,entity_id,signal_kind,knowledge_state,severity,confidence,summary,report_json,observed_at) VALUES(:id,:key,'mercadolivre','visits',:entity,'snapshot_visits','observed','info',0.7,'v2 integration',CAST(:report AS jsonb),:observed)"""),{"id":sid,"key":uuid4().hex,"entity":entity,"report":json.dumps(report),"observed":observed})
                await session.commit()
            result=await evo.refresh_predictions()
            async with sessions() as session:
                forecast_rows=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations WHERE source_intelligence_id=:id"),{"id":forecast_id})).scalar_one())
                abstain_rows=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations WHERE source_intelligence_id=:id"),{"id":abstain_id})).scalar_one())
                row=(await session.execute(text("SELECT status,target_metric,operator,calibration_error,marketplace_writes FROM prediction_evaluations WHERE source_intelligence_id=:id"),{"id":forecast_id})).mappings().one()
            metrics=await evo.persist_metrics()
            assert forecast_rows==1 and abstain_rows==0
            assert row["status"]=="PENDING" and row["target_metric"]=="visits" and row["operator"]=="INCREASE"
            assert row["calibration_error"] is None and row["marketplace_writes"]==0
            assert result["not_evaluable_new_generation"]==0
            assert metrics["FORECASTS_TOTAL"]>=1 and metrics["ABSTENTIONS_TOTAL"]>=1
            assert metrics["NOT_EVALUABLE_NEW_GENERATION"]==0 and metrics["MARKETPLACE_WRITES"]==0
        finally:
            async with sessions() as session:
                await session.execute(text("DELETE FROM prediction_evaluations WHERE source_intelligence_id IN (:f,:a)"),{"f":forecast_id,"a":abstain_id})
                await session.execute(text("DELETE FROM sovereign_intelligence WHERE id IN (:f,:a)"),{"f":forecast_id,"a":abstain_id})
                await session.commit()
            await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)
