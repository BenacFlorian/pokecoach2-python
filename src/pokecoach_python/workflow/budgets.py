"""Simulation budgets per profile (workflow spec §2)."""

from __future__ import annotations

from typing import Literal

Profile = Literal["standard", "smoke"]

_PHASE_A_BUDGET: dict[Profile, int] = {
    "standard": 1000,
    "smoke": 20,
}

_PHASE_B_BUDGET: dict[Profile, int] = {
    "standard": 50,
    "smoke": 3,
}


def phase_a_valid_budget(profile: str) -> int:
    if profile not in _PHASE_A_BUDGET:
        raise ValueError(f"unknown profile: {profile}")
    return _PHASE_A_BUDGET[profile]  # type: ignore[index]


def phase_b_valid_budget(profile: str) -> int:
    if profile not in _PHASE_B_BUDGET:
        raise ValueError(f"unknown profile: {profile}")
    return _PHASE_B_BUDGET[profile]  # type: ignore[index]


_PHASE_C_BUDGET: dict[Profile, int] = {
    "standard": 50,
    "smoke": 3,
}


def phase_c_valid_budget(profile: str) -> int:
    if profile not in _PHASE_C_BUDGET:
        raise ValueError(f"unknown profile: {profile}")
    return _PHASE_C_BUDGET[profile]  # type: ignore[index]


def studied_opponent_lead_count(parameters: dict, *, default: int = 3) -> int:
    raw = parameters.get("studiedOpponentLeadCount", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value in (2, 3):
        return value
    return default


_PHASE_D_BUDGET: dict[Profile, int] = {
    "standard": 10,
    "smoke": 2,
}


def phase_d_valid_budget(profile: str) -> int:
    if profile not in _PHASE_D_BUDGET:
        raise ValueError(f"unknown profile: {profile}")
    return _PHASE_D_BUDGET[profile]  # type: ignore[index]


def max_attempts(valid_budget: int, *, multiplier: int = 5) -> int:
    return valid_budget * multiplier
