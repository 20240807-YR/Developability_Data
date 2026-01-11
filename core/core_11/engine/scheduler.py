from .types import Decision


def decide_allocation(step, current, candidate, allow_switch):
    if not allow_switch or current == candidate:
        return Decision(
            step=step,
            allocation_id=current,
            switched=False,
            reason="NO_SWITCH",
        )

    return Decision(
        step=step,
        allocation_id=candidate,
        switched=True,
        reason="POLICY_SWITCH",
    )