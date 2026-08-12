from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OAuthRuntimeSettings:
    marketplace: str = "mercadolivre"
    synthetic_only: bool = True
    network_blocked: bool = True
    writes_blocked: bool = True
    transaction_ttl_seconds: int = 600
    refresh_margin_seconds: int = 300
    refresh_claim_ttl_seconds: int = 120
    refresh_dedup_seconds: int = 30
    synthetic_refresh_enabled: bool = True
    expected_schema_revision: str = "0002_r11_oauth"

    def validate_for_r11(self) -> None:
        if not self.synthetic_only:
            raise PermissionError("R1.1 requires synthetic-only OAuth")
        if not self.network_blocked:
            raise PermissionError("R1.1 requires real OAuth network to remain blocked")
        if not self.writes_blocked:
            raise PermissionError("R1.1 requires marketplace writes to remain blocked")
        if self.transaction_ttl_seconds <= 0:
            raise ValueError("transaction_ttl_seconds must be positive")
        if self.refresh_margin_seconds < 0:
            raise ValueError("refresh_margin_seconds cannot be negative")
        if self.refresh_claim_ttl_seconds <= 0:
            raise ValueError("refresh_claim_ttl_seconds must be positive")
        if self.refresh_dedup_seconds < 0:
            raise ValueError("refresh_dedup_seconds cannot be negative")

    def assert_real_network_allowed(self) -> None:
        if self.synthetic_only or self.network_blocked:
            raise PermissionError("Real OAuth network is blocked by policy")

    def assert_marketplace_write_allowed(self) -> None:
        if self.writes_blocked:
            raise PermissionError("Marketplace writes are blocked by policy")
