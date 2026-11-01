"""Detect forbidden Pokémon names in strategy prose (our side outside bring-4)."""

from __future__ import annotations

import re
from typing import Any

from pokecoach_python.graphs.matchup_gameplan.models import StrategyOutput


def forbidden_our_species_in_text(
    text: str,
    *,
    allowed_species: set[str],
    full_roster_species: set[str],
) -> str | None:
    for species in full_roster_species:
        if species in allowed_species:
            continue
        if re.search(rf"\b{re.escape(species)}\b", text, flags=re.IGNORECASE):
            return species
    return None


def validate_strategy_team_references(
    strategy: StrategyOutput,
    *,
    our_snapshot: dict[str, Any],
    our_four: tuple[int, int, int, int],
) -> None:
    mons = our_snapshot.get("pokemon") or []
    allowed: set[str] = set()
    full: set[str] = set()
    for slot, row in enumerate(mons):
        if not isinstance(row, dict):
            continue
        species = str(row.get("species") or row.get("name") or "").strip()
        if not species:
            continue
        full.add(species)
        if slot in our_four:
            allowed.add(species)
    texts: list[str] = [
        strategy.gameplan.opening,
        strategy.gameplan.midgame,
        strategy.gameplan.endgame,
        strategy.winCondition.description,
        strategy.winCondition.rationale,
    ]
    for highlight in strategy.gameplan.threats:
        texts.append(highlight.explanation)
    for highlight in strategy.gameplan.strengths:
        texts.append(highlight.explanation)
    for text in texts:
        offender = forbidden_our_species_in_text(
            text,
            allowed_species=allowed,
            full_roster_species=full,
        )
        if offender is not None:
            raise ValueError(
                f"strategy references our roster Pokémon outside bring-4: {offender}"
            )
