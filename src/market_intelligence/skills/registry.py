from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from market_intelligence.marketplaces.capabilities import MarketplaceCapability


class SkillLicenseStatus(StrEnum):
    INTERNAL = "internal"
    OPEN_SOURCE = "open_source"
    PROPRIETARY = "proprietary"
    QUARANTINE = "quarantine"


class SkillExecutionStatus(StrEnum):
    REFERENCE_ONLY = "reference_only"
    APPROVED_ACTIVE = "approved_active"


class SkillDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_id: str = Field(min_length=1)
    function: str = Field(min_length=1)
    supported_marketplaces: tuple[str, ...] = ("*",)
    required_capabilities: tuple[MarketplaceCapability, ...] = ()
    ai_role: Literal["agents"] = "agents"
    license_status: SkillLicenseStatus
    execution_status: SkillExecutionStatus
    source: str = Field(min_length=1)

    @property
    def executable(self) -> bool:
        return (
            self.execution_status is SkillExecutionStatus.APPROVED_ACTIVE
            and self.license_status in {SkillLicenseStatus.INTERNAL, SkillLicenseStatus.OPEN_SOURCE}
        )


class SkillRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SkillDescriptor] = {}

    def register(self, descriptor: SkillDescriptor) -> None:
        if descriptor.skill_id in self._items:
            raise ValueError("skill_already_registered")
        self._items[descriptor.skill_id] = descriptor

    def all(self) -> tuple[SkillDescriptor, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: item.skill_id))

    def get(self, skill_id: str) -> SkillDescriptor:
        try:
            return self._items[skill_id]
        except KeyError as exc:
            raise KeyError("skill_not_registered") from exc

    def resolve(
        self,
        *,
        function: str,
        marketplace: str,
        executable_only: bool = True,
    ) -> tuple[SkillDescriptor, ...]:
        marketplace_key = marketplace.strip().lower()
        result: list[SkillDescriptor] = []
        for item in self._items.values():
            if item.function != function:
                continue
            supported = {value.strip().lower() for value in item.supported_marketplaces}
            if "*" not in supported and marketplace_key not in supported:
                continue
            if executable_only and not item.executable:
                continue
            result.append(item)
        return tuple(sorted(result, key=lambda item: item.skill_id))


SKILL_REGISTRY = SkillRegistry()
