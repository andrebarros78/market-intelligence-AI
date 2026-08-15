from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from market_intelligence.marketplaces.canonical import EvidenceKind
class SensorSignalKind(StrEnum):
    BUSINESS_EVENT="business_event"
    CHANNEL_TELEMETRY="channel_telemetry"
    SCHEMA_CHANGE="schema_change"
    ABSENCE_SILENCE="absence_silence"
    DERIVED="derived"
    CROSS_MARKET_CORRELATION="cross_market_correlation"
class SensorEntity(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    entity_type:str=Field(min_length=1,max_length=64)
    entity_id:str=Field(min_length=1,max_length=160)
class SensorSignal(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    marketplace:str=Field(min_length=1,max_length=64)
    kind:SensorSignalKind
    evidence_kind:EvidenceKind
    source:str=Field(min_length=1,max_length=160)
    observed_at:datetime
    declared:bool=True
    entity:SensorEntity|None=None
    payload:dict[str,Any]=Field(default_factory=dict)
    confidence:float=Field(default=1.0,ge=0.0,le=1.0)
    validated:bool=False
    @property
    def permanent_fact_eligible(self)->bool:
        return self.evidence_kind is EvidenceKind.FACT and self.validated
