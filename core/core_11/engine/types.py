from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    policy_key: str
    scenario_key: str
    seed: int
    t_steps: int


@dataclass
class SystemState:
    step: int
    SoMS: float
    toggle_rate: float
    drift: float
    current_allocation: Optional[str]


@dataclass
class Decision:
    step: int
    allocation_id: str
    switched: bool
    reason: str


@dataclass
class FallbackEvent:
    step: int
    trigger: str
    previous_allocation: str
    fallback_allocation: str


@dataclass
class ChecksumResult:
    run_id: str
    checksum: str