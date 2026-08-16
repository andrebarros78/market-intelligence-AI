from __future__ import annotations

from market_intelligence.intelligence.sovereign.organs import (
    SovereignCounterIntelligence,
    SovereignInstigator,
)
from market_intelligence.missions.models import MissionCreate
from market_intelligence.missions.planner import CognitiveMissionPlanner

INVENTORY = {
    "snapshots": 100,
    "channel_events": 200,
    "raw_events": 50,
    "sovereign_intelligence": 300,
    "exposure_map": 20,
    "learning_episodes": 40,
    "investigation_cases": 5,
    "investigation_events": 12,
}


def test_sales_objective_materially_directs_plan() -> None:
    planner = CognitiveMissionPlanner()
    plan = planner.compile(
        MissionCreate(objective="Investigue por que minhas vendas caíram hoje"),
        data_inventory=INVENTORY,
    )
    expected = {"sales", "demand", "visits", "price", "competition", "exposure", "stock", "questions", "orders", "logistics", "channel"}
    assert expected.issubset(set(plan.signal_families))
    assert plan.temporal_window["lookback_hours"] == 24
    joined = " ".join(plan.secondary_questions).lower()
    assert "vendas realmente" in joined
    assert "visitas" in joined
    assert "competitividade" in joined
    assert "estoque" in joined
    assert plan.minimum_evidence["minimum_distinct_observations"] == 2
    assert "marketplace_writes_zero" in plan.safety_limits


def test_schema_objective_does_not_become_generic_sales_search() -> None:
    planner = CognitiveMissionPlanner()
    plan = planner.compile(
        MissionCreate(objective="Investigue mudanças de schema, campos e latência do canal nas últimas 6 horas"),
        data_inventory=INVENTORY,
    )
    assert "schema" in plan.signal_families
    assert "channel" in plan.signal_families
    assert "sales" not in plan.signal_families
    assert plan.temporal_window["lookback_hours"] == 6


def test_baseline_uses_all_history_and_broad_signal_families() -> None:
    planner = CognitiveMissionPlanner()
    plan = planner.compile(
        MissionCreate(objective="Estabeleça o baseline soberano inicial usando todo o histórico legítimo disponível"),
        data_inventory=INVENTORY,
    )
    assert plan.temporal_window["lookback_hours"] is None
    assert len(plan.signal_families) >= 15
    assert "schema" in plan.signal_families and "sales" in plan.signal_families


def test_instigator_feedback_consumes_loop_returns() -> None:
    questions = SovereignInstigator().feedback(
        findings=[{"knowledge_state": "correlated"}],
        correlations=[{"strength": 0.8}],
        hypotheses=[{"statement": "possible exposure change"}],
        evidence=[{"source": "radar"}],
        contradictions=[{"contradiction_detected": True}],
        counterintelligence_objections=["A mudança de coleta pode explicar o efeito?"],
        predictions=[{"statement": "next window may repeat"}],
        gaps=["missing independent evidence"],
    )
    text = " ".join(questions).lower()
    assert "ainda nao foi explicado" in text
    assert "derrubar" in text
    assert "contrad" in text
    assert "coleta" in text
    assert len(questions) <= 16


def test_counterintelligence_challenge_is_falsification_first() -> None:
    questions = SovereignCounterIntelligence().challenge(
        findings=[{"knowledge_state": "validated"}],
        evidence=[{"source": "official"}],
        mode="challenge",
    )
    text = " ".join(questions).lower()
    assert "derrubar" in text
    assert "correlacao" in text
    assert "evidencia contraria" in text
    assert "coleta" in text and "schema" in text
    assert "validado" in text


def test_autonomous_production_default_keeps_concurrency_limit() -> None:
    import inspect

    from market_intelligence.missions.orchestrator import SovereignMissionOrchestrator
    signature = inspect.signature(SovereignMissionOrchestrator.open_autonomous_from_radar)
    assert signature.parameters["max_active"].default == 4


def test_mission_text_rejects_secret_material() -> None:
    import pytest
    from pydantic import ValidationError

    from market_intelligence.missions.models import FollowUpCreate, MissionCreate
    with pytest.raises(ValidationError, match="secret_material"):
        MissionCreate(objective="Investigate bearer secret-value-without-persisting-it")
    with pytest.raises(ValidationError, match="secret_material"):
        FollowUpCreate(question="Check access_token=secret-value in the investigation")
