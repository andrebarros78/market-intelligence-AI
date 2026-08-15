from __future__ import annotations

from market_intelligence.persistence.models import Base
from market_intelligence.persistence import learning_models as _learning_models  # noqa: F401


def test_sovereign_learning_tables_are_registered_in_metadata():
    assert "learning_episodes" in Base.metadata.tables
    assert "learning_promotions" in Base.metadata.tables
    assert "learning_checkpoints" in Base.metadata.tables

    episodes = Base.metadata.tables["learning_episodes"]
    promotions = Base.metadata.tables["learning_promotions"]
    checkpoints = Base.metadata.tables["learning_checkpoints"]

    assert episodes.c.dedupe_key.unique is None  # uniqueness is table-level and named
    assert {"marketplace", "entity_type", "entity_id", "state", "watchdogs"}.issubset(episodes.c.keys())
    assert {"episode_id", "target", "status", "candidate_payload"}.issubset(promotions.c.keys())
    assert {"mission_id", "checkpoint_json", "processed_count", "marketplace_writes"}.issubset(checkpoints.c.keys())
