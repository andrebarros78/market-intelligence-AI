from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Deterministic retry timing with bounded Retry-After support."""

    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    max_retry_after_seconds: float = 60.0

    def delay_seconds(
        self,
        *,
        attempt: int,
        retry_after: str | None = None,
        now: datetime | None = None,
    ) -> float:
        if attempt < 0:
            raise ValueError("attempt_must_be_non_negative")

        parsed_retry_after = _parse_retry_after_seconds(retry_after, now=now)
        if parsed_retry_after is not None:
            return min(parsed_retry_after, self.max_retry_after_seconds)

        exponential = self.base_delay_seconds * (2**attempt)
        return min(exponential, self.max_delay_seconds)


class InProcessProviderTrafficGate:
    """Small FIFO-like admission gate for one runtime process.

    It prevents local bursts and preserves a cooldown after a provider rate-limit.
    Cross-process durability remains the responsibility of the job/orchestration layer.
    """

    def __init__(
        self,
        *,
        concurrency_limit: int,
        clock: Callable[[], float] = monotonic,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        if concurrency_limit < 1:
            raise ValueError("concurrency_limit_must_be_positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_must_be_positive")
        self._concurrency_limit = concurrency_limit
        self._clock = clock
        self._poll_interval_seconds = poll_interval_seconds
        self._in_flight = 0
        self._cooldown_until = 0.0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def concurrency_limit(self) -> int:
        return self._concurrency_limit

    def defer(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self._cooldown_until = max(self._cooldown_until, self._clock() + seconds)

    def try_acquire(self) -> bool:
        if self._in_flight >= self._concurrency_limit:
            return False
        if self._clock() < self._cooldown_until:
            return False
        self._in_flight += 1
        return True

    async def acquire(self) -> None:
        while not self.try_acquire():
            remaining = max(0.0, self._cooldown_until - self._clock())
            delay = (
                min(remaining, self._poll_interval_seconds)
                if remaining > 0
                else self._poll_interval_seconds
            )
            await asyncio.sleep(delay)

    def release(self) -> None:
        if self._in_flight <= 0:
            raise RuntimeError("traffic_gate_release_without_acquire")
        self._in_flight -= 1


ZAI_RETRY_POLICY = RetryPolicy(
    base_delay_seconds=2.0,
    max_delay_seconds=30.0,
    max_retry_after_seconds=60.0,
)

# Conservative default while GLM-4.7-Flash is being validated against provider limits.
ZAI_TRAFFIC_GATE = InProcessProviderTrafficGate(concurrency_limit=1)


def _parse_retry_after_seconds(
    value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    try:
        seconds = float(normalized)
    except ValueError:
        seconds = None
    if seconds is not None:
        return max(0.0, seconds)

    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (parsed - reference).total_seconds())
