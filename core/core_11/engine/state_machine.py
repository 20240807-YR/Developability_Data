from .types import SystemState


def init_state(initial_allocation: str) -> SystemState:
    return SystemState(
        step=0,
        SoMS=0.0,
        toggle_rate=0.0,
        drift=0.0,
        current_allocation=initial_allocation,
    )