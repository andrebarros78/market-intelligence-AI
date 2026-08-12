from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .types import SyntheticTokenSet


class SyntheticOAuthError(RuntimeError):
    pass


class SyntheticOAuthClient:
    """No-network OAuth simulator used only by R1.1."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        fail_exchange: bool = False,
        fail_refresh: bool = False,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.fail_exchange = fail_exchange
        self.fail_refresh = fail_refresh
        self.exchange_calls = 0
        self.refresh_calls = 0

    async def exchange(self, *, code: str, verifier: str) -> SyntheticTokenSet:
        self.exchange_calls += 1
        if self.fail_exchange or not code or not verifier:
            raise SyntheticOAuthError("synthetic_exchange_rejected")
        return self._issue()

    async def refresh(self, *, refresh_token: str) -> SyntheticTokenSet:
        self.refresh_calls += 1
        if self.fail_refresh or not refresh_token:
            raise SyntheticOAuthError("synthetic_refresh_rejected")
        return self._issue()

    def _issue(self) -> SyntheticTokenSet:
        return SyntheticTokenSet(
            access_token="syn_at_" + secrets.token_urlsafe(32),
            refresh_token="syn_rt_" + secrets.token_urlsafe(32),
            expires_at=self._clock() + timedelta(hours=1),
            scopes=("read",),
        )
