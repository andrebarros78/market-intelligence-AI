from __future__ import annotations

import os
from dataclasses import dataclass

from market_intelligence.core.security import MODULE01_SECURITY_POLICY


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    read_only: bool = True
    allow_marketplace_writes: bool = False
    database_url: str | None = None
    temporal_enabled: bool = False
    temporal_target: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "market-intelligence"
    temporal_tls: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("MI_ENVIRONMENT", "development"),
            read_only=os.getenv("MI_READ_ONLY", "true").lower() == "true",
            allow_marketplace_writes=os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").lower() == "true",
            database_url=os.getenv("MI_DATABASE_URL") or None,
            temporal_enabled=os.getenv("MI_TEMPORAL_ENABLED", "false").lower() == "true",
            temporal_target=os.getenv("MI_TEMPORAL_TARGET", "localhost:7233"),
            temporal_namespace=os.getenv("MI_TEMPORAL_NAMESPACE", "default"),
            temporal_task_queue=os.getenv("MI_TEMPORAL_TASK_QUEUE", "market-intelligence"),
            temporal_tls=os.getenv("MI_TEMPORAL_TLS", "false").lower() == "true",
        )

    def assert_module01_operational_security(self) -> None:
        MODULE01_SECURITY_POLICY.assert_runtime_settings(
            read_only=self.read_only,
            allow_marketplace_writes=self.allow_marketplace_writes,
        )

    def assert_marketplace_write_allowed(self) -> None:
        if self.read_only or not self.allow_marketplace_writes:
            raise PermissionError("Marketplace writes are disabled by policy")
