from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.missions.evolution import ContinuousEvolutionEngine
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory


@pytest.mark.postgres
def test_continuous_evolution_cycle_feedback_cooldown_and_utf8(tmp_path, monkeypatch) -> None:
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
        evolution = ContinuousEvolutionEngine(sessions, repo, tmp_path, interval_seconds=60)
        evolution.version = "continuous-evolution-test-" + uuid4().hex
        try:
            human = await evolution.record_human_hypothesis(
                "Esse sinal de competi\u00e7\u00e3o pode anteceder perda de vendas.",
                "PRICE_TO_WIN",
                0.65,
            )
            assert human["requires_validation"] is True
            assert human["promoted_to_fact"] is False

            first = await evolution.run_due(force=False)
            assert first["status"] == "COMPLETED"
            assert first["marketplace_writes"] == 0
            second = await evolution.run_due(force=False)
            assert second == {"status": "SKIPPED_COOLDOWN", "marketplace_writes": 0}

            snapshot = await evolution.executive_snapshot()
            assert snapshot["marketplace_writes"] == 0
            assert int(snapshot["metrics"]["marketplace_writes"]) == 0
            assert int(snapshot["metrics"]["open_questions"]) >= 1
            assert snapshot["next_question"] is not None

            report_path = await evolution.write_report(first)
            report = report_path.read_text(encoding="utf-8")
            for required in (
                "RELAT\u00d3RIO SOBERANO DE EVOLU\u00c7\u00c3O",
                "O QUE APRENDEMOS",
                "O QUE DESAPRENDEMOS",
                "PREVIS\u00d5ES ERRARAM",
                "CONTRAINTELIG\u00caNCIA",
                "PR\u00d3XIMA PERGUNTA DE MAIOR VALOR",
                "MARKETPLACE_WRITES=0",
            ):
                assert required in report
            assert "\ufffd" not in report
            assert "\u00c3\u0083" not in report
            assert "\u00c3\u0082" not in report

            async with sessions() as session:
                promoted = int((await session.execute(text("""
                    SELECT count(*) FROM human_domain_hypotheses
                    WHERE hypothesis_id=CAST(:id AS uuid) AND status='VALIDATED'
                """), {"id": human["hypothesis_id"]})).scalar_one())
                writes = int((await session.execute(text("SELECT coalesce(sum(marketplace_writes),0) FROM evolution_cycles"))).scalar_one())
            assert promoted == 0
            assert writes == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=psycopg_compatible_loop)



def test_continuous_evolution_rejects_marketplace_write_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "false")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    monkeypatch.setenv("MARKETPLACE_WRITES", "0")
    with pytest.raises(RuntimeError, match="continuous_evolution_requires_read_only"):
        ContinuousEvolutionEngine.assert_security()
