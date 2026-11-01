"""Detect forbidden Pokémon names in strategy prose (our side outside bring-4)."""

from __future__ import annotations

import re
from typing import Any

from pokecoach_python.graphs.matchup_gameplan.models import StrategyOutput

_REF_TOKEN = re.compile(r"\{\{(ours|opponent):([0-5])\}\}")


def _species_at(snapshots: tuple[dict[str, Any], dict[str, Any]], side: str, slot: int) -> str:
    snap = snapshots[0] if side == "ours" else snapshots[1]
    mons = snap.get("pokemon") or []
    if slot >= len(mons) or not isinstance(mons[slot], dict):
        raise ValueError(f"unknown token reference {side}:{slot}")
    name = str(mons[slot].get("species") or mons[slot].get("name") or "").strip()
    if not name:
        raise ValueError(f"empty species for token {side}:{slot}")
    return name


def _iter_prose_fields(strategy: StrategyOutput) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("gameplan.opening", strategy.gameplan.opening),
        ("gameplan.midgame", strategy.gameplan.midgame),
        ("gameplan.endgame", strategy.gameplan.endgame),
        ("winCondition.description", strategy.winCondition.description),
        ("winCondition.rationale", strategy.winCondition.rationale),
    ]
    for idx, highlight in enumerate(strategy.gameplan.threats):
        rows.append((f"gameplan.threats[{idx}].explanation", highlight.explanation))
    for idx, highlight in enumerate(strategy.gameplan.strengths):
        rows.append((f"gameplan.strengths[{idx}].explanation", highlight.explanation))
    return rows


def validate_strategy_reference_tokens(
    strategy: StrategyOutput,
    *,
    our_four: tuple[int, int, int, int],
) -> None:
    for field, text in _iter_prose_fields(strategy):
        for match in _REF_TOKEN.finditer(text):
            side, slot_s = match.group(1), int(match.group(2))
            if side == "ours" and slot_s not in our_four:
                raise ValueError(
                    f"{field} references our slot {slot_s} outside bring-4 via token"
                )
        if _REF_TOKEN.search(text) is None and "{{" in text:
            raise ValueError(f"{field} contains malformed reference token")


def render_strategy_references(
    strategy: StrategyOutput,
    *,
    snapshots: tuple[dict[str, Any], dict[str, Any]],
) -> StrategyOutput:
    def render_text(text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            side, slot_s = match.group(1), int(match.group(2))
            return _species_at(snapshots, side, slot_s)

        return _REF_TOKEN.sub(repl, text)

    gameplan = strategy.gameplan.model_copy(
        update={
            "opening": render_text(strategy.gameplan.opening),
            "midgame": render_text(strategy.gameplan.midgame),
            "endgame": render_text(strategy.gameplan.endgame),
            "threats": [
                item.model_copy(update={"explanation": render_text(item.explanation)})
                for item in strategy.gameplan.threats
            ],
            "strengths": [
                item.model_copy(update={"explanation": render_text(item.explanation)})
                for item in strategy.gameplan.strengths
            ],
        }
    )
    win = strategy.winCondition.model_copy(
        update={
            "description": render_text(strategy.winCondition.description),
            "rationale": render_text(strategy.winCondition.rationale),
        }
    )
    return strategy.model_copy(update={"gameplan": gameplan, "winCondition": win})


def forbidden_our_species_in_text(
    text: str,
    *,
    allowed_species: set[str],
    full_roster_species: set[str],
) -> str | None:
    stripped = _REF_TOKEN.sub(" ", text)
    for species in full_roster_species:
        if species in allowed_species:
            continue
        if re.search(rf"\b{re.escape(species)}\b", stripped, flags=re.IGNORECASE):
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
    for _field, text in _iter_prose_fields(strategy):
        offender = forbidden_our_species_in_text(
            text,
            allowed_species=allowed,
            full_roster_species=full,
        )
        if offender is not None:
            raise ValueError(
                f"strategy references our roster Pokémon outside bring-4: {offender}"
            )
