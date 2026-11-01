"""Accesseurs de budget — valeurs dans `pokecoach_python.simulation_budgets`."""

from __future__ import annotations

from pokecoach_python.simulation_budgets import (
    ATTEMPT_MULTIPLIER,
    BUDGETS,
    STUDIED_OPPONENT_LEAD_ALLOWED,
    STUDIED_OPPONENT_LEAD_COUNT_DEFAULT,
    Profile,
)

__all__ = [
    "Profile",
    "phase_a_valid_budget",
    "phase_b_valid_budget",
    "phase_c_valid_budget",
    "phase_d_valid_budget",
    "studied_opponent_lead_count",
    "max_attempts",
]


def _budget(profile: str, phase: str) -> int:
    if profile not in BUDGETS:
        raise ValueError(f"unknown profile: {profile}")
    return BUDGETS[profile][phase]  # type: ignore[index]


def phase_a_valid_budget(profile: str) -> int:
    return _budget(profile, "A")


def phase_b_valid_budget(profile: str) -> int:
    return _budget(profile, "B")


def phase_c_valid_budget(profile: str) -> int:
    return _budget(profile, "C")


def phase_d_valid_budget(profile: str) -> int:
    return _budget(profile, "D")


def studied_opponent_lead_count(
    parameters: dict,
    *,
    default: int = STUDIED_OPPONENT_LEAD_COUNT_DEFAULT,
) -> int:
    raw = parameters.get("studiedOpponentLeadCount", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value in STUDIED_OPPONENT_LEAD_ALLOWED:
        return value
    return default


def max_attempts(valid_budget: int, *, multiplier: int = ATTEMPT_MULTIPLIER) -> int:
    return valid_budget * multiplier
