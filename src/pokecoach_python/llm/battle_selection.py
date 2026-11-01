"""Deterministic sampling of D battles for synthesis prompts."""

from __future__ import annotations

from math import ceil

from pokecoach_python.graphs.matchup_gameplan.models import (
    NormalizedDBattle,
    SelectionBucket,
    SelectionManifest,
)


def select_d_battles(records: list[NormalizedDBattle]) -> SelectionManifest:
    population = len(records)
    if population == 0:
        raise ValueError("NO_D_BATTLE")
    q_win = ceil((15 * population) / 100)
    q_loss = ceil((15 * population) / 100)
    q_close = ceil((20 * population) / 100)
    selected_ids: set[str] = set()

    close_candidates = [
        record
        for record in records
        if record.outcome in ("win", "loss") and _winner_survivor_count(record) in (1, 2)
    ]
    close_candidates.sort(
        key=lambda record: (_winner_survivor_count(record), record.sampleKey, record.battleId)
    )
    close = _reserve(close_candidates, q_close, selected_ids, "close quota unavailable")

    win_candidates = [record for record in records if record.outcome == "win"]
    win_candidates.sort(
        key=lambda record: (-len(record.survivorSlots["ours"]), record.sampleKey, record.battleId)
    )
    wins = _reserve(win_candidates, q_win, selected_ids, "win quota unavailable")

    loss_candidates = [record for record in records if record.outcome == "loss"]
    loss_candidates.sort(
        key=lambda record: (-len(record.survivorSlots["opponent"]), record.sampleKey, record.battleId)
    )
    losses = _reserve(loss_candidates, q_loss, selected_ids, "loss quota unavailable")

    ordered_ids = close.retainedBattleIds + wins.retainedBattleIds + losses.retainedBattleIds
    if not ordered_ids:
        raise ValueError("NO_SELECTABLE_D_BATTLE")
    limitations = [
        message
        for message in (close.shortfallReason, wins.shortfallReason, losses.shortfallReason)
        if message
    ]
    return SelectionManifest(
        populationSize=population,
        quotas={"wins": q_win, "losses": q_loss, "close": q_close},
        close=close,
        wins=wins,
        losses=losses,
        selectedBattleIds=ordered_ids,
        limitations=limitations,
    )


def _winner_survivor_count(record: NormalizedDBattle) -> int:
    if record.outcome == "win":
        return len(record.survivorSlots["ours"])
    if record.outcome == "loss":
        return len(record.survivorSlots["opponent"])
    return 0


def _reserve(
    candidates: list[NormalizedDBattle],
    requested: int,
    selected_ids: set[str],
    shortfall_reason: str,
) -> SelectionBucket:
    retained = []
    for record in candidates:
        if record.battleId in selected_ids:
            continue
        selected_ids.add(record.battleId)
        retained.append(record)
        if len(retained) >= requested:
            break
    return SelectionBucket(
        requested=requested,
        retainedBattleIds=[record.battleId for record in retained],
        retainedBattleDigests=[record.sha256 for record in retained],
        shortfallReason=shortfall_reason if len(retained) < requested else None,
    )
