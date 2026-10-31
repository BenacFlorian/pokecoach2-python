"""Async Showdown battles via poke-env (requires vgc-bench deps + local server)."""

from __future__ import annotations

import asyncio
from typing import Any

from pokecoach_vgc_bridge.battle_session import (
    _lead_slots_from_battle,
    create_policy_pair,
    ensure_showdown_available,
    vgc_deps_available,
)
from pokecoach_vgc_bridge.extract_turn_one import extract_turn_one_payload
from pokecoach_vgc_bridge.normalization import build_battle_record, build_preview, build_turn_one


async def _run_policy_preview_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
) -> dict[str, Any]:
    ensure_showdown_available()
    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
    )
    await p1.battle_against(p2, n_battles=1)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    our_battle = next(iter(p1.battles.values()))
    opp_battle = next(iter(p2.battles.values()))
    our_lead = _lead_slots_from_battle(our_battle, team_attr="team")
    opp_lead = _lead_slots_from_battle(opp_battle, team_attr="team")
    return build_preview(
        opponent_lead=opp_lead,
        our_lead=our_lead,
        engine="vgc-bench",
    )


async def _run_first_turn_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int] | None,
) -> dict[str, Any]:
    ensure_showdown_available()
    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
    )
    await p1.battle_against(p2, n_battles=1)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    battle = next(iter(p1.battles.values()))
    turn = int(getattr(battle, "turn", 0) or 0)
    if turn < 1:
        raise RuntimeError("TURN1_INCOMPLETE: battle ended before turn 1")
    if our_lead is None:
        our_lead = _lead_slots_from_battle(battle, team_attr="team")
    payload = extract_turn_one_payload(
        battle,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        opponent_lead=opponent_lead,
        our_lead=our_lead,
    )
    return build_turn_one(
        opponent_lead=opponent_lead,
        our_lead=our_lead,
        actions=payload["actions"],
        back_pair=(payload["backPair"][0], payload["backPair"][1]),
        engine="vgc-bench",
    )


async def _run_full_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
    opponent_lead: tuple[int, int],
    payload: dict[str, Any],
) -> dict[str, Any]:
    ensure_showdown_available()
    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
    )
    await p1.battle_against(p2, n_battles=1)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    battle = next(iter(p1.battles.values()))
    if not getattr(battle, "finished", False):
        raise RuntimeError("BATTLE_NOT_TERMINAL: simulator did not report finished")
    our_lead = _lead_slots_from_battle(battle, team_attr="team")
    turn1 = extract_turn_one_payload(
        battle,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        opponent_lead=opponent_lead,
        our_lead=our_lead,
    )
    our_four, our_lead_resolved = _resolve_lineup(payload, seed, our_snapshot)
    if p1.n_won_battles > 0:
        outcome = "win"
    elif p1.n_lost_battles > 0:
        outcome = "loss"
    elif p1.n_tied_battles > 0:
        outcome = "draw"
    else:
        raise RuntimeError("BATTLE_OUTCOME_UNKNOWN: no win/loss/tie recorded")
    our_actions = _our_actions_from_turn1(our_snapshot, our_lead_resolved, seed)
    return build_battle_record(
        opponent_lead=opponent_lead,
        our_lead=our_lead_resolved,
        our_four=our_four,
        our_actions=our_actions,
        opponent_actions=turn1["actions"],
        outcome=outcome,
        seed=seed,
        engine="vgc-bench",
        payload=payload,
    )


def _resolve_lineup(
    payload: dict[str, Any],
    seed: int,
    our: dict[str, Any],
) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    from pokecoach_vgc_bridge.fixture_sim import _resolve_our_lineup

    return _resolve_our_lineup(payload, seed, our)


def _our_actions_from_turn1(
    our_snapshot: dict[str, Any],
    our_lead: tuple[int, int],
    seed: int,
) -> list[dict[str, Any]]:
    import hashlib

    from pokecoach_vgc_bridge.fixture_sim import _our_turn1_actions

    digest = hashlib.sha256(f"our-turn1:{seed}".encode()).digest()
    return _our_turn1_actions(our_snapshot, our_lead, digest)


def run_preview_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_policy_preview_battle(**kwargs))


def run_first_turn_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_first_turn_battle(**kwargs))


def run_full_battle_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_full_battle(**kwargs))


def deps_available() -> bool:
    return vgc_deps_available()
