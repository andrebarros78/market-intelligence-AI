from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    read_only: bool = True
    allow_marketplace_writes: bool = False
    database_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("MI_ENVIRONMENT", "development"),
            read_only=os.getenv("MI_READ_ONLY", "true").lower() == "true",
            allow_marketplace_writes=os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").lower() == "true",
            database_url=os.getenv("MI_DATABASE_URL") or None,
        )

    def assert_marketplace_write_allowed(self) -> None:
        if self.read_only or not self.allow_marketplace_writes:
            raise PermissionError("Marketplace writes are disabled by policy")
