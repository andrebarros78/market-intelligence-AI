from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_OAUTH = ROOT / "src/market_intelligence/marketplaces/mercadolivre/oauth/real_read.py"
SECURITY = ROOT / "src/market_intelligence/core/security.py"


def test_real_oauth_is_fail_closed_and_business_security_stays_get_only() -> None:
    real_source = REAL_OAUTH.read_text(encoding="utf-8")
    security_source = SECURITY.read_text(encoding="utf-8")

    assert 'real_read_enabled: bool = False' in real_source
    assert 'os.getenv("MI_ML_REAL_READ_ENABLED", "false")' in real_source
    assert '"/oauth/token"' in real_source
    assert 'client.post(' in real_source
    assert 'read_user_me()' in real_source
    assert 'operation="/users/me"' in real_source
    assert 'request.method.upper() != "GET"' in security_source
    assert "PUT" not in real_source
    assert "DELETE" not in real_source
    assert ".patch(" not in real_source.lower()


def test_real_oauth_never_exposes_client_secret_in_authorization_url() -> None:
    source = REAL_OAUTH.read_text(encoding="utf-8")
    authorization_block = source.split("def authorization_url", 1)[1].split(
        "async def exchange", 1
    )[0]
    assert "client_secret" not in authorization_block
    assert '"client_id": self.settings.app_id' in authorization_block
    assert '"code_challenge_method": "S256"' in authorization_block
