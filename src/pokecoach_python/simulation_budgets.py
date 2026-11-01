"""Budgets d'échantillons par phase et par profil — modifier ici.

Utilisé par les phases workflow A→D (`workflow/budgets.py`).

| Clé | Signification |
| --- | --- |
| **A** | Previews valides (leads adverses) |
| **B** | Simulations tour 1 valides **par lead** listé en A |
| **C** | Parties complètes valides **par lead adverse étudié** (top 2–3 de A) |
| **D** | Parties complètes valides **total** sur le run (évaluation globale, scénarios A/B) |

Profils : `standard` (charge réelle), `smoke` (tests rapides).
Spec : `docs/specs/2026-10-31-workflow-analyse-matchup.md`.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Profile = Literal["standard", "smoke"]


class PhaseBudgets(TypedDict):
    A: int
    B: int
    C: int
    D: int


STANDARD: PhaseBudgets = {
    "A": 100,
    "B": 5,
    "C": 5,
    "D": 2,
}

SMOKE: PhaseBudgets = {
    "A": 20,
    "B": 3,
    "C": 3,
    "D": 2,
}

BUDGETS: dict[Profile, PhaseBudgets] = {
    "standard": STANDARD,
    "smoke": SMOKE,
}

# Plafond de tentatives = budget_valide × ATTEMPT_MULTIPLIER (échecs / rejets inclus).
ATTEMPT_MULTIPLIER: int = 5

# Phase C : nombre de leads adverses (top fréquence A) à étudier.
STUDIED_OPPONENT_LEAD_COUNT_DEFAULT: int = 3
STUDIED_OPPONENT_LEAD_ALLOWED: tuple[int, ...] = (2, 3)
