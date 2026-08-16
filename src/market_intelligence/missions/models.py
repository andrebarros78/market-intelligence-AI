from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MissionType(StrEnum):
    DIRECTED = "DIRECTED"
    AUTONOMOUS = "AUTONOMOUS"


class MissionOrigin(StrEnum):
    USER = "USER"
    GPT = "GPT"
    RADAR = "RADAR"
    SYSTEM = "SYSTEM"


class MissionState(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    COLLECTING = "COLLECTING"
    CORRELATING = "CORRELATING"
    INVESTIGATING = "INVESTIGATING"
    VALIDATING = "VALIDATING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FollowUpMode(StrEnum):
    DEEPEN = "deepen"
    CHALLENGE = "challenge"
    CONTINUE = "continue"


RUNNING_STATES = {
    MissionState.RECEIVED,
    MissionState.PLANNING,
    MissionState.COLLECTING,
    MissionState.CORRELATING,
    MissionState.INVESTIGATING,
    MissionState.VALIDATING,
    MissionState.REPORTING,
    MissionState.DEGRADED,
}
TERMINAL_STATES = {
    MissionState.COMPLETED,
    MissionState.BLOCKED,
    MissionState.FAILED,
    MissionState.CANCELLED,
}


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=8, max_length=8000)
    origin: MissionOrigin = MissionOrigin.GPT
    mission_type: MissionType = MissionType.DIRECTED
    marketplace_scope: tuple[str, ...] = ("mercadolivre",)
    authority: str = Field(default="owner_read_only", min_length=3, max_length=64)
    priority: int = Field(default=50, ge=0, le=100)
    deadline_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)

    @field_validator("objective")
    @classmethod
    def reject_secret_material(cls, value: str) -> str:
        lowered = value.casefold()
        forbidden = ("bearer ", "access_token=", "refresh_token=", "authorization:", "client_secret=", "password=", "api_key=")
        if any(marker in lowered for marker in forbidden):
            raise ValueError("mission_objective_contains_secret_material")
        return value

    @field_validator("marketplace_scope")
    @classmethod
    def normalize_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if not cleaned:
            raise ValueError("marketplace_scope_empty")
        return cleaned


class FollowUpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=5, max_length=8000)
    mode: FollowUpMode = FollowUpMode.DEEPEN
    source_finding_id: str | None = Field(default=None, max_length=64)
    priority: int = Field(default=70, ge=0, le=100)

    @field_validator("question")
    @classmethod
    def reject_secret_material(cls, value: str) -> str:
        lowered = value.casefold()
        forbidden = ("bearer ", "access_token=", "refresh_token=", "authorization:", "client_secret=", "password=", "api_key=")
        if any(marker in lowered for marker in forbidden):
            raise ValueError("follow_up_contains_secret_material")
        return value


class MissionView(BaseModel):
    mission_id: str
    origin: str
    objective: str
    mission_type: str
    marketplace_scope: list[str]
    authority: str
    priority: int
    status: str
    created_at: datetime
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
    deadline_at: datetime | None
    checkpoint: dict[str, Any]
    error_code: str | None
    retry_count: int
    marketplace_writes: int
    thread_id: str | None = None
    root_mission_id: str | None = None
    parent_mission_id: str | None = None
    source_report_id: str | None = None
    source_finding_id: str | None = None
    follow_up_question: str | None = None
    mode: str = "standard"

class HumanDomainHypothesisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=5, max_length=8000)
    signal_family: str = Field(min_length=2, max_length=64)
    confidence_initial: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("statement")
    @classmethod
    def reject_secret_material(cls, value: str) -> str:
        lowered = value.casefold()
        forbidden = ("bearer ", "access_token=", "refresh_token=", "authorization:", "client_secret=", "password=", "api_key=")
        if any(marker in lowered for marker in forbidden):
            raise ValueError("human_hypothesis_contains_secret_material")
        return value

    @field_validator("signal_family")
    @classmethod
    def normalize_signal_family(cls, value: str) -> str:
        cleaned = value.strip().upper().replace(" ", "_")
        if not cleaned:
            raise ValueError("signal_family_empty")
        return cleaned
