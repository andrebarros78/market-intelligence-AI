from datetime import datetime, timezone

import pytest

from market_intelligence.ai.rate_control import InProcessProviderTrafficGate, RetryPolicy


def test_retry_policy_uses_retry_after_seconds_and_caps_it() -> None:
    policy = RetryPolicy(
        base_delay_seconds=1.0,
        max_delay_seconds=30.0,
        max_retry_after_seconds=60.0,
    )

    assert policy.delay_seconds(attempt=0, retry_after="12") == 12.0
    assert policy.delay_seconds(attempt=0, retry_after="120") == 60.0
    assert policy.delay_seconds(attempt=2, retry_after=None) == 4.0


def test_retry_policy_accepts_http_date_and_never_returns_negative_delay() -> None:
    policy = RetryPolicy(max_retry_after_seconds=60.0)
    now = datetime(2026, 8, 14, 16, 0, 0, tzinfo=timezone.utc)

    assert (
        policy.delay_seconds(
            attempt=0,
            retry_after="Fri, 14 Aug 2026 16:00:10 GMT",
            now=now,
        )
        == 10.0
    )
    assert (
        policy.delay_seconds(
            attempt=0,
            retry_after="Fri, 14 Aug 2026 15:59:00 GMT",
            now=now,
        )
        == 0.0
    )


def test_traffic_gate_limits_concurrency_and_preserves_cooldown() -> None:
    clock_value = [100.0]
    gate = InProcessProviderTrafficGate(
        concurrency_limit=1,
        clock=lambda: clock_value[0],
    )

    assert gate.try_acquire() is True
    assert gate.in_flight == 1
    assert gate.try_acquire() is False

    gate.release()
    gate.defer(5.0)
    assert gate.try_acquire() is False

    clock_value[0] = 105.0
    assert gate.try_acquire() is True
    gate.release()


def test_traffic_gate_rejects_invalid_configuration_and_unbalanced_release() -> None:
    with pytest.raises(ValueError, match="concurrency_limit_must_be_positive"):
        InProcessProviderTrafficGate(concurrency_limit=0)

    gate = InProcessProviderTrafficGate(concurrency_limit=1)
    with pytest.raises(RuntimeError, match="traffic_gate_release_without_acquire"):
        gate.release()
