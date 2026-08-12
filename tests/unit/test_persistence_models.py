from sqlalchemy import create_engine, inspect

from market_intelligence.persistence.models import Base


def test_base02_schema_can_be_materialized_in_memory() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert tables == {"raw_events", "entities", "snapshots", "alerts", "evidence", "oauth_states"}


def test_oauth_state_schema_never_persists_plaintext_state_or_tokens() -> None:
    columns = set(Base.metadata.tables["oauth_states"].columns.keys())
    assert "state_hash" in columns
    assert "verifier_envelope" in columns
    assert "state" not in columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "client_secret" not in columns


def test_raw_events_have_a_database_idempotency_key() -> None:
    table = Base.metadata.tables["raw_events"]
    assert "dedupe_key" in table.c
    unique_names = {constraint.name for constraint in table.constraints if constraint.name}
    assert "uq_raw_events_dedupe_key" in unique_names
