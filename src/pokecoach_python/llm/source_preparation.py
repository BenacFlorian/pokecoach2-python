"""Prepare compact, validated sources for the synthesis graph."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from pokecoach_python.graphs.matchup_gameplan.models import (
    PreparedSources,
    TeamPokemonContext,
    compute_sources_hash,
)
from pokecoach_python.llm.battle_selection import select_d_battles
from pokecoach_python.llm.battle_sources import StoredDBattle, normalize_stored_d_battle
from pokecoach_python.llm.battle_statistics import compute_d_statistics

TokenCounter = Callable[[str], int]


def prepare_sources(
    records: list[StoredDBattle],
    snapshots: tuple[dict[str, Any], dict[str, Any]],
    token_budget: int,
    token_counter: TokenCounter | None = None,
    *,
    output_token_budget: int = 0,
    model_name: str = "",
    our_four: tuple[int, int, int, int] | None = None,
) -> PreparedSources:
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    normalized = [normalize_stored_d_battle(record) for record in records]
    if not normalized:
        raise ValueError("NO_D_BATTLE")
    our_four = our_four or normalized[0].ourFourSlots
    if any(record.ourFourSlots != our_four for record in normalized):
        raise ValueError("our fixed four must remain stable across D battles")
    statistics = compute_d_statistics(normalized)
    manifest = select_d_battles(normalized)
    selected_lookup = {record.battleId: record for record in normalized}
    selected = [selected_lookup[battle_id] for battle_id in manifest.selectedBattleIds]
    limitations = list(manifest.limitations)
    limitations.append(
        "Selected logs are intentionally biased examples; global rates come from all D battles."
    )
    our_team = _team_context(snapshots[0], side="ours", only_slots=our_four)
    opponent_team = _team_context(snapshots[1], side="opponent")
    provisional = PreparedSources(
        sourceHash="",
        tokenEstimate=0,
        tokenBudget=token_budget,
        outputTokenBudget=output_token_budget,
        modelName=model_name,
        manifest=manifest,
        statistics=statistics,
        selectedBattles=selected,
        ourTeam=our_team,
        opponentTeam=opponent_team,
        limitations=limitations,
    )
    counter = token_counter or default_token_counter
    payload = provisional.model_dump(mode="json")
    token_estimate = counter(_canonical_json(payload))
    if token_estimate > token_budget:
        raise ValueError(
            f"TOKEN_BUDGET_EXCEEDED: estimated {token_estimate} tokens for budget {token_budget}"
        )
    payload["tokenEstimate"] = token_estimate
    payload["sourceHash"] = compute_sources_hash(payload)
    return PreparedSources.model_validate(payload)


def default_token_counter(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _team_context(
    snapshot: dict[str, Any],
    *,
    side: str,
    only_slots: tuple[int, int, int, int] | None = None,
) -> list[TeamPokemonContext]:
    pokemon_rows = snapshot.get("pokemon") or []
    allowed = set(only_slots) if only_slots is not None else None
    rows: list[TeamPokemonContext] = []
    for slot, row in enumerate(pokemon_rows):
        if allowed is not None and slot not in allowed:
            continue
        if not isinstance(row, dict):
            continue
        species = str(row.get("species") or row.get("name") or f"slot-{slot}")
        moves = tuple(str(move) for move in row.get("moves") or ())
        rows.append(
            TeamPokemonContext(
                side=side,  # type: ignore[arg-type]
                slot=slot,
                species=species,
                item=str(row.get("item")) if row.get("item") else None,
                ability=str(row.get("ability")) if row.get("ability") else None,
                moves=moves,
            )
        )
    return rows


def _canonical_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
