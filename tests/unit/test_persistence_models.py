from sqlalchemy import create_engine, inspect

from market_intelligence.marketplaces.mercadolivre.oauth import db_models as _oauth_db_models  # noqa: F401
from market_intelligence.persistence.models import Base


def test_operational_schema_can_be_materialized_in_memory() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert tables == {
        "raw_events",
        "channel_events",
        "entities",
        "snapshots",
        "alerts",
        "evidence",
        "oauth_states",
        "oauth_credentials",
        "oauth_audit",
        "oauth_operations",
    }


def test_oauth_state_schema_never_persists_plaintext_state_or_tokens() -> None:
    columns = set(Base.metadata.tables["oauth_states"].columns.keys())
    assert "state_hash" in columns
    assert "verifier_envelope" in columns
    assert "state" not in columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "client_secret" not in columns


def test_oauth_credential_schema_persists_only_envelopes_and_refresh_control() -> None:
    columns = set(Base.metadata.tables["oauth_credentials"].columns.keys())
    assert {"access_envelope", "refresh_envelope", "refresh_claim_id", "refresh_started_at", "last_refresh_at"} <= columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "client_secret" not in columns


def test_raw_events_have_a_database_idempotency_key() -> None:
    table = Base.metadata.tables["raw_events"]
    assert "dedupe_key" in table.c
    unique_names = {constraint.name for constraint in table.constraints if constraint.name}
    assert "uq_raw_events_dedupe_key" in unique_names


def test_channel_events_and_alerts_have_database_idempotency_keys() -> None:
    channel = Base.metadata.tables["channel_events"]
    alerts = Base.metadata.tables["alerts"]
    assert "dedupe_key" in channel.c and "dedupe_key" in alerts.c
    channel_unique = {constraint.name for constraint in channel.constraints if constraint.name}
    alert_unique = {constraint.name for constraint in alerts.constraints if constraint.name}
    assert "uq_channel_events_dedupe_key" in channel_unique
    assert "uq_alerts_dedupe_key" in alert_unique
