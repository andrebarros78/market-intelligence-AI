from market_intelligence.marketplaces.mercadolivre.read_sanitize import safe_claims,safe_order,safe_questions
def test_order_sanitizer_drops_buyer_pii():
    raw={"id":1,"status":"paid","buyer":{"id":99,"email":"x@example.com","phone":{"number":"123"}},"order_items":[{"item":{"id":"MLB1","title":"X","seller_sku":"SKU"},"quantity":2,"unit_price":10,"currency_id":"BRL"}],"shipping":{"id":7,"receiver_address":{"address_line":"secret"}}}
    safe=safe_order(raw)
    rendered=str(safe).lower()
    assert "buyer" not in safe and "email" not in rendered and "receiver_address" not in rendered
    assert safe["shipping_id"]==7
def test_question_sanitizer_drops_free_text_and_customer_identity():
    raw={"questions":[{"id":1,"item_id":"MLB1","text":"private question","from":{"id":4},"status":"ANSWERED","date_created":"x","answer":{"text":"private answer","status":"ACTIVE","date_created":"y"}}]}
    safe=safe_questions(raw); rendered=str(safe).lower()
    assert "private question" not in rendered and "private answer" not in rendered and "from" not in rendered
def test_claim_sanitizer_drops_players_and_messages():
    raw={"data":[{"id":1,"status":"opened","players":[{"user_id":3}],"messages":[{"text":"secret"}],"reason_id":"x"}]}
    rendered=str(safe_claims(raw)).lower()
    assert "players" not in rendered and "messages" not in rendered and "secret" not in rendered
