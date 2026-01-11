def hazard_from_score(proxy_survivability: float) -> float:
    return max(0.0, min(1.0, 1.0 - proxy_survivability))


def should_request_switch(hazard: float, threshold: float) -> bool:
    return hazard >= threshold