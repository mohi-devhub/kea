"""Scenario-only models. Ground truth stays outside the engine package."""

from typing import Literal

from pydantic import BaseModel

from app.models.engine import ReasonCode
from app.models.topology import Metric


class DeploymentSpec(BaseModel):
    offset_s: int
    service: str
    deployment_id: str
    version: str
    commit_ref: str
    summary: str


class EffectSpec(BaseModel):
    service: str
    metric: Metric
    start_s: int
    ramp_s: int
    target_multiplier: float | None = None
    target_value: float | None = None
    duration_s: int | None = None


class RootCause(BaseModel):
    kind: Literal["deployment", "service_fault"]
    service: str
    deployment_id: str | None = None


class ExpectedRejection(BaseModel):
    candidate_id: str
    reason_code: ReasonCode


class GroundTruth(BaseModel):
    expect_incident: bool
    root_cause: RootCause | None = None
    must_not_implicate: list[str]
    must_reject: list[ExpectedRejection]
    ordering_constraints: list[tuple[str, str]]


class Scenario(BaseModel):
    id: str
    title: str
    description: str
    priority: Literal["P0", "P1"]
    warmup_s: int
    duration_s: int
    deployments: list[DeploymentSpec]
    effects: list[EffectSpec]
    ground_truth: GroundTruth
