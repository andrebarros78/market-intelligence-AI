from __future__ import annotations

import base64

import pytest

from market_intelligence.api.real_read_server import (
    create_real_read_app_from_env,
    decode_oauth_key,
)


def test_decode_oauth_key_requires_exact_aes256_material() -> None:
    key = b"k" * 32
    encoded = base64.b64encode(key).decode("ascii")
    assert decode_oauth_key(encoded) == key

    with pytest.raises(RuntimeError, match="required"):
        decode_oauth_key("")
    with pytest.raises(RuntimeError, match="invalid"):
        decode_oauth_key("not-base64!!!")
    with pytest.raises(RuntimeError, match="exactly 32 bytes"):
        decode_oauth_key(base64.b64encode(b"short").decode("ascii"))


def test_real_read_bootstrap_requires_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MI_DATABASE_URL", raising=False)
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    with pytest.raises(RuntimeError, match="MI_DATABASE_URL is required"):
        create_real_read_app_from_env()


def test_real_read_bootstrap_stays_disabled_without_explicit_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MI_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/unused",
    )
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    monkeypatch.setenv("MI_ML_APP_ID", "2767330231710080")
    monkeypatch.setenv("MI_ML_CLIENT_SECRET", "secret-only-for-test")
    monkeypatch.setenv(
        "MI_ML_REDIRECT_URI",
        "https://example.test/v1/oauth/mercadolivre/callback",
    )
    monkeypatch.setenv(
        "MI_ML_OAUTH_KEY_B64",
        base64.b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.delenv("MI_ML_REAL_READ_ENABLED", raising=False)

    with pytest.raises(PermissionError, match="mercadolivre_real_read_disabled"):
        create_real_read_app_from_env()


def test_real_read_bootstrap_rejects_marketplace_write_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "false")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "true")
    with pytest.raises(PermissionError):
        create_real_read_app_from_env()
