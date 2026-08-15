from __future__ import annotations
from collections.abc import Awaitable,Callable
from dataclasses import dataclass,field
from typing import Any
from market_intelligence.marketplaces.canonical import EvidenceKind
from market_intelligence.sensors.models import SensorSignal
SensorHandler=Callable[[SensorSignal],Awaitable[None]]
_SECRET_KEYS={"authorization","access_token","refresh_token","client_secret","partner_key","app_secret","password","cookie","set-cookie"}
def _contains_secret_key(value:Any)->bool:
    if isinstance(value,dict):
        return any(str(k).strip().lower() in _SECRET_KEYS or _contains_secret_key(v) for k,v in value.items())
    if isinstance(value,list): return any(_contains_secret_key(v) for v in value)
    return False
@dataclass(slots=True)
class UniversalSensorBus:
    handlers:list[SensorHandler]=field(default_factory=list)
    observed_count:int=0
    rejected_count:int=0
    def subscribe(self,handler:SensorHandler)->None:self.handlers.append(handler)
    async def publish(self,signal:SensorSignal)->None:
        if _contains_secret_key(signal.payload):
            self.rejected_count+=1; raise ValueError("sensor_signal_contains_secret")
        if signal.evidence_kind in {EvidenceKind.HYPOTHESIS,EvidenceKind.INFERENCE} and signal.validated:
            self.rejected_count+=1; raise ValueError("non_fact_signal_cannot_be_validated_as_fact")
        self.observed_count+=1
        for handler in tuple(self.handlers): await handler(signal)
