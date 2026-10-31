"""Simulation budgets per profile (workflow spec §2)."""

from __future__ import annotations

from typing import Literal

Profile = Literal["standard", "smoke"]

_PHASE_A_BUDGET: dict[Profile, int] = {
    "standard": 1000,
    "smoke": 20,
}


def phase_a_valid_budget(profile: str) -> int:
    if profile not in _PHASE_A_BUDGET:
        raise ValueError(f"unknown profile: {profile}")
    return _PHASE_A_BUDGET[profile]  # type: ignore[index]


def max_attempts(valid_budget: int, *, multiplier: int = 5) -> int:
    return valid_budget * multiplier
