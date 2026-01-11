import numpy as np
from .types import SystemState


def update_dynamics(
    state: SystemState,
    hazard: float,
    op_risk: float,
    drift_step: float,
) -> SystemState:
    new_drift = state.drift + drift_step

    soms_inc = 0.3 * op_risk + 0.4 * new_drift
    toggle_inc = 0.25 * hazard + 0.2 * new_drift

    return SystemState(
        step=state.step + 1,
        SoMS=state.SoMS + soms_inc,
        toggle_rate=min(1.5, state.toggle_rate + toggle_inc),
        drift=new_drift,
        current_allocation=state.current_allocation,
    )