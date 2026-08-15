from pathlib import Path

def test_universal_collector_contains_no_marketplace_mutation_call():
    source=(Path(__file__).resolve().parents[2]/"src"/"market_intelligence"/"marketplaces"/"mercadolivre"/"full_read_collector.py").read_text(encoding="utf-8").lower()
    forbidden=(".put(",".patch(",".delete(",".post(","requests.post", "requests.put")
    assert all(token not in source for token in forbidden)

def test_oauth_refresh_post_is_restricted_to_token_endpoint():
    source=(Path(__file__).resolve().parents[2]/"src"/"market_intelligence"/"marketplaces"/"mercadolivre"/"vault_token.py").read_text(encoding="utf-8")
    assert 'TOKEN_URL="https://api.mercadolibre.com/oauth/token"' in source or 'TOKEN_URL = "https://api.mercadolibre.com/oauth/token"' in source
    assert source.lower().count("client.post(")==1
