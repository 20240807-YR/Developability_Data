from typing import List
from .types import FallbackEvent


def check_fallback(
    state,
    hazard: float,
    fallback_pool: List[str],
    threshold: float,
):
    if hazard < threshold:
        return None

    if state.current_allocation not in fallback_pool:
        return None

    idx = fallback_pool.index(state.current_allocation)
    if idx + 1 >= len(fallback_pool):
        return None

    return fallback_pool[idx + 1]


def build_fallback_event(step, prev, new):
    return FallbackEvent(
        step=step,
        trigger="HAZARD_THRESHOLD_EXCEEDED",
        previous_allocation=prev,
        fallback_allocation=new,
    )