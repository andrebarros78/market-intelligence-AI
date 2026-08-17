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
from market_intelligence.missions.prediction_semantics import compare
from market_intelligence.persistence.database import create_database_engine, create_session_factory


def test_down_prediction_with_up_observation_is_incorrect() -> None:
    assert compare(operator="DECREASE", observed=120, expected=None, baseline=100, tolerance=0) == ("EVALUATED_INCORRECT", 0.0)


def test_down_prediction_with_down_observation_is_correct() -> None:
    assert compare(operator="DECREASE", observed=80, expected=None, baseline=100, tolerance=0) == ("EVALUATED_CORRECT", 1.0)


def test_unknown_operator_is_not_evaluable() -> None:
    assert compare(operator="FREE_TEXT", observed=80, expected=None, baseline=100, tolerance=0) == ("NOT_EVALUABLE", None)


async def _insert_prediction(sessions, *, entity: str, baseline: float | None, operator: str | None, due: datetime, confidence: float = 0.8):
    pid=uuid4(); now=datetime.now(UTC)
    async with sessions() as session:
        await session.execute(text("""
            INSERT INTO prediction_evaluations(
                prediction_id,dedupe_key,statement,target,time_horizon,confidence_before,expected_observation,
                evaluation_due_at,observed_result,correct_or_incorrect,confidence_after,status,marketplace_writes,
                target_entity,target_metric,operator,expected_value,expected_direction,baseline_value,tolerance,evaluation_window,evidence_source)
            VALUES(:id,:key,'visitas vao cair',:target,'1h',:conf,CAST(:expected AS jsonb),:due,'{}'::jsonb,'PENDING',:conf,'PENDING',0,
                :entity,'visits',:operator,NULL,'DOWN',CAST(:baseline AS jsonb),0,CAST(:window AS jsonb),'official_read_snapshots')
        """),{"id":pid,"key":uuid4().hex,"target":f"item:{entity}:visits","conf":confidence,"expected":json.dumps({"after":(now-timedelta(hours=2)).isoformat()}),
               "due":due,"entity":entity,"operator":operator,"baseline":json.dumps(baseline),"window":json.dumps({"start_at":(now-timedelta(hours=2)).isoformat()})})
        await session.commit()
    return pid


async def _insert_visit(sessions, *, entity: str, value: int):
    now=datetime.now(UTC)
    async with sessions() as session:
        await session.execute(text("""
            INSERT INTO snapshots(id,marketplace,entity_type,entity_id,captured_at,payload_hash,payload)
            VALUES(:id,'mercadolivre','visits',:entity,:at,:hash,CAST(:payload AS jsonb))
        """),{"id":uuid4(),"entity":entity,"at":now-timedelta(minutes=20),"hash":uuid4().hex,"payload":json.dumps({entity:value})})
        await session.commit()


@pytest.mark.postgres
def test_same_signal_presence_with_contrary_content_is_not_correct(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        entity="SEM-UP-"+uuid4().hex
        try:
            pid=await _insert_prediction(sessions,entity=entity,baseline=100,operator="DECREASE",due=datetime.now(UTC)-timedelta(minutes=1))
            await _insert_visit(sessions,entity=entity,value=120)
            await evo.evaluate_due_predictions()
            async with sessions() as session:
                row=(await session.execute(text("SELECT status,observed_value,observed_outcome,marketplace_writes FROM prediction_evaluations WHERE prediction_id=:id"),{"id":pid})).mappings().one()
            assert row["status"]=="EVALUATED_INCORRECT"
            assert row["observed_value"]==120
            assert row["observed_outcome"]==0.0
            assert row["marketplace_writes"]==0
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)


@pytest.mark.postgres
def test_no_observation_after_due_is_expired_no_data(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        try:
            pid=await _insert_prediction(sessions,entity="SEM-NODATA-"+uuid4().hex,baseline=100,operator="DECREASE",due=datetime.now(UTC)-timedelta(minutes=1))
            await evo.evaluate_due_predictions()
            async with sessions() as session:
                row=(await session.execute(text("SELECT status,calibration_error FROM prediction_evaluations WHERE prediction_id=:id"),{"id":pid})).mappings().one()
            assert row["status"]=="EXPIRED_NO_DATA"; assert row["calibration_error"] is None
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)


@pytest.mark.postgres
def test_legacy_prediction_without_contract_is_not_evaluable(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path); pid=uuid4()
        try:
            async with sessions() as session:
                await session.execute(text("""INSERT INTO prediction_evaluations(prediction_id,dedupe_key,statement,target,time_horizon,confidence_before,expected_observation,evaluation_due_at,observed_result,correct_or_incorrect,confidence_after,status,marketplace_writes) VALUES(:id,:key,'legacy free text','legacy','6h',0.9,'{}'::jsonb,:due,'{}'::jsonb,'PENDING',0.9,'PENDING',0)"""),{"id":pid,"key":uuid4().hex,"due":datetime.now(UTC)-timedelta(minutes=1)}); await session.commit()
            await evo.evaluate_due_predictions()
            async with sessions() as session: row=(await session.execute(text("SELECT status,calibration_error FROM prediction_evaluations WHERE prediction_id=:id"),{"id":pid})).mappings().one()
            assert row["status"]=="LEGACY_NOT_EVALUABLE"; assert row["calibration_error"] is None
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)


@pytest.mark.postgres
def test_calibration_ignores_not_evaluable_and_leading_signals_do_not_invent_fp(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        try:
            await evo.research_leading_signals()
            async with sessions() as session:
                fabricated=int((await session.execute(text("SELECT count(*) FROM leading_signal_research WHERE false_positives=0 OR false_negatives=0"))).scalar_one())
                measured=int((await session.execute(text("SELECT count(*) FROM leading_signal_research WHERE precision IS NOT NULL AND (false_positives IS NULL OR false_negatives IS NULL)"))).scalar_one())
                bad_cal=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations WHERE status IN ('NOT_EVALUABLE','LEGACY_NOT_EVALUABLE','EXPIRED_NO_DATA') AND calibration_error IS NOT NULL"))).scalar_one())
                writes=int((await session.execute(text("SELECT coalesce(sum(marketplace_writes),0) FROM prediction_evaluations"))).scalar_one())
            assert fabricated==0; assert measured==0; assert bad_cal==0; assert writes==0
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)


@pytest.mark.postgres
def test_future_prediction_remains_pending_until_due(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        try:
            pid=await _insert_prediction(sessions,entity="SEM-FUTURE-"+uuid4().hex,baseline=100,operator="DECREASE",due=datetime.now(UTC)+timedelta(hours=1))
            await _insert_visit(sessions,entity="SEM-FUTURE-"+uuid4().hex,value=80)
            await evo.evaluate_due_predictions()
            async with sessions() as session:
                row=(await session.execute(text("SELECT status,calibration_error FROM prediction_evaluations WHERE prediction_id=:id"),{"id":pid})).mappings().one()
            assert row["status"]=="PENDING"; assert row["calibration_error"] is None
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)


@pytest.mark.postgres
def test_semantic_prediction_evaluation_preserves_marketplace_writes_zero(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    async def scenario():
        engine=create_database_engine(url); sessions=create_session_factory(engine); evo=ContinuousEvolutionEngine(sessions,PostgresMissionRepository(sessions),tmp_path)
        try:
            entity="SEM-WRITES-"+uuid4().hex
            await _insert_prediction(sessions,entity=entity,baseline=100,operator="DECREASE",due=datetime.now(UTC)-timedelta(minutes=1))
            await _insert_visit(sessions,entity=entity,value=80)
            await evo.evaluate_due_predictions()
            async with sessions() as session:
                prediction_writes=int((await session.execute(text("SELECT coalesce(sum(marketplace_writes),0) FROM prediction_evaluations"))).scalar_one())
                cycle_writes=int((await session.execute(text("SELECT coalesce(sum(marketplace_writes),0) FROM evolution_cycles"))).scalar_one())
            assert prediction_writes==0
            assert cycle_writes==0
            assert os.getenv("MARKETPLACE_WRITES")=="0"
        finally: await engine.dispose()
    asyncio.run(scenario(),loop_factory=psycopg_compatible_loop)
