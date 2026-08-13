from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ObservableFactorCandidate(BaseModel):
    name: str = Field(min_length=1)
    current: float
    history: list[float]
    source: str | None = None
    eligible: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)


class FactorAttributionRequest(BaseModel):
    metric: str = Field(min_length=1)
    expected: float | None = None
    factors: list[ObservableFactorCandidate] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class AttributedFactor(BaseModel):
    name: str
    source: str | None = None
    association: float
    slope: float
    current_delta: float
    raw_contribution: float
    contribution: float
    historical_points: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class FactorAttribution(BaseModel):
    metric: str
    expected: float
    observed: float
    observed_delta: float
    factors: list[AttributedFactor] = Field(default_factory=list)
    explained_delta: float
    unexplained_residual: float
    explained_fraction: float
    reference_source: str
    excluded: dict[str, int] = Field(default_factory=dict)
    causal_claim: bool = False
    fit_uses_current_target: bool = False
    version: str
    attributes: dict[str, Any] = Field(default_factory=dict)
