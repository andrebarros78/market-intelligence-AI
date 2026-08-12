from market_intelligence.marketplaces.mercadolivre.channel_sensor import build_channel_telemetry


def test_channel_sensor_never_persists_authorization() -> None:
    telemetry = build_channel_telemetry(
        direction="meli->us",
        endpoint="/notifications",
        status_code=206,
        headers={
            "Authorization": "Bearer SHOULD-NOT-LEAK",
            "X-Request-Id": "req-123",
            "X-Content-Missing": "orders",
            "Retry-After": "2",
            "X-Unknown": "discard-me",
        },
    )
    assert "authorization" not in telemetry.operational_headers
    assert telemetry.request_id == "req-123"
    assert telemetry.partial_content is True
    assert "x-unknown" not in telemetry.operational_headers
