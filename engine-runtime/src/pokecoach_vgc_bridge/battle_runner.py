"""Async Showdown battles via poke-env (requires vgc-bench deps + local server)."""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from typing import Any

from pokecoach_vgc_bridge.battle_session import (
    _lead_slots_from_battle,
    create_policy_pair,
    vgc_deps_available,
)
from pokecoach_vgc_bridge.extract_turn_one import _actions_for_side, extract_turn_one_payload
from pokecoach_vgc_bridge.normalization import build_battle_record, build_preview, build_turn_one


def _canonical_lead(lead: tuple[int, int]) -> tuple[int, int]:
    return (lead[0], lead[1]) if lead[0] < lead[1] else (lead[1], lead[0])


async def _await_preview_selection(
    p1: Any,
    p2: Any,
    *,
    timeout_seconds: float,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return both selected leads and disconnect before the first battle turn."""
    battle_task = asyncio.create_task(p1.battle_against(p2, n_battles=1))
    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                our_preview = getattr(p1, "pokecoach_preview_slots", ())
                opponent_preview = getattr(p2, "pokecoach_preview_slots", ())
                if len(our_preview) == 4 and len(opponent_preview) == 4:
                    return (
                        (int(our_preview[0]), int(our_preview[1])),
                        (int(opponent_preview[0]), int(opponent_preview[1])),
                    )
                if p1.battles and p2.battles:
                    our_battle = next(iter(p1.battles.values()))
                    opponent_battle = next(iter(p2.battles.values()))
                    try:
                        return (
                            _lead_slots_from_battle(our_battle, team_attr="team"),
                            _lead_slots_from_battle(opponent_battle, team_attr="team"),
                        )
                    except (RuntimeError, ValueError):
                        pass
                await asyncio.sleep(0.05)
    except TimeoutError as exc:
        raise RuntimeError("PREVIEW_TIMEOUT: teams were not selected in time") from exc
    finally:
        battle_task.cancel()
        with suppress(asyncio.CancelledError):
            await battle_task
        for player in (p1, p2):
            stop_listening = getattr(getattr(player, "ps_client", None), "stop_listening", None)
            if callable(stop_listening):
                with suppress(Exception):
                    await asyncio.wait_for(stop_listening(), timeout=1)


def _back_pair_from_preview_four(four: tuple[int, int, int, int]) -> tuple[int, int]:
    a, b = int(four[2]), int(four[3])
    return (a, b) if a < b else (b, a)


async def _run_policy_preview_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
) -> dict[str, Any]:
    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
    )
    timeout = float(os.environ.get("POKECOACH_ENGINE_PREVIEW_LIFECYCLE_TIMEOUT", "30"))
    our_lead, opp_lead = await _await_preview_selection(
        p1,
        p2,
        timeout_seconds=timeout,
    )
    return build_preview(
        opponent_lead=opp_lead,
        our_lead=our_lead,
        engine="vgc-bench",
    )


def _lead_from_preview_slots(player: Any) -> tuple[int, int] | None:
    preview = getattr(player, "pokecoach_preview_slots", ())
    if len(preview) != 4:
        return None
    a, b = int(preview[0]), int(preview[1])
    return (a, b) if a < b else (b, a)


def _four_from_preview_slots(player: Any) -> tuple[int, int, int, int] | None:
    preview = getattr(player, "pokecoach_preview_slots", ())
    if len(preview) != 4:
        return None
    return (int(preview[0]), int(preview[1]), int(preview[2]), int(preview[3]))


async def _forfeit_player_battle(player: Any, battle: Any) -> None:
    client = getattr(player, "ps_client", None)
    tag = getattr(battle, "battle_tag", None)
    if client is None or not tag:
        return
    with suppress(Exception):
        await client.send_message("/forfeit", tag)


async def _battle_through_turn_one(
    p1: Any,
    p2: Any,
    *,
    timeout_seconds: float,
) -> None:
    """Play until turn 1 is resolved; forfeit as soon as turn > 1 (do not play out)."""
    battle_task = asyncio.create_task(p1.battle_against(p2, n_battles=1))
    forfeited = False
    try:
        async with asyncio.timeout(timeout_seconds):
            while not battle_task.done():
                if p1.battles:
                    battle = next(iter(p1.battles.values()))
                    if getattr(battle, "finished", False):
                        break
                    turn = int(getattr(battle, "turn", 0) or 0)
                    if turn > 1 and not forfeited:
                        await _forfeit_player_battle(p1, battle)
                        if p2.battles:
                            opp_battle = next(iter(p2.battles.values()))
                            await _forfeit_player_battle(p2, opp_battle)
                        forfeited = True
                await asyncio.sleep(0.05)
            await battle_task
    except TimeoutError as exc:
        battle_task.cancel()
        with suppress(asyncio.CancelledError):
            await battle_task
        raise RuntimeError(
            f"FIRST_TURN_BATTLE_TIMEOUT: battle did not finish within {timeout_seconds}s"
        ) from exc
    finally:
        if not battle_task.done():
            battle_task.cancel()
            with suppress(asyncio.CancelledError):
                await battle_task


from pokecoach_vgc_bridge.showdown_teams import pokecoach_regulation_to_vgc_reg


def _battle_format_for_regulation(regulation: str) -> str:
    from pokecoach_vgc_bridge.extract_turn_one import _DEFAULT_BATTLE_FORMAT

    try:
        from pokecoach_vgc_bridge.vgc_source import prepare_vgc_bench_source

        prepare_vgc_bench_source()
        from vgc_bench.src.utils import format_map

        return format_map[pokecoach_regulation_to_vgc_reg(regulation)]
    except Exception:
        return _DEFAULT_BATTLE_FORMAT


async def _run_first_turn_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int] | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    imposed = _canonical_lead(opponent_lead)
    request = dict(payload or {})
    our_sel_raw = request.get("ourSelection")
    our_lead_raw = request.get("ourLeadSlots")
    our_imposed_four: tuple[int, int, int, int] | None = None
    if our_lead_raw and len(our_lead_raw) == 2:
        our_lead = (int(our_lead_raw[0]), int(our_lead_raw[1]))
    if isinstance(our_sel_raw, list) and len(our_sel_raw) == 4:
        from pokecoach_vgc_bridge.battle_session import imposed_four_with_lead_order

        raw_four = tuple(int(s) for s in our_sel_raw)
        if len(set(raw_four)) != 4:
            raise ValueError("ourSelection must contain four distinct slots")
        if our_lead is None:
            raise ValueError("ourLeadSlots required with ourSelection")
        our_imposed_four = imposed_four_with_lead_order(raw_four, our_lead)
    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
        our_imposed_lead=our_lead if our_imposed_four is None else None,
        opponent_imposed_lead=imposed,
        our_imposed_four=our_imposed_four,
    )
    lifecycle_timeout = float(
        os.environ.get("POKECOACH_ENGINE_FIRST_TURN_LIFECYCLE_TIMEOUT", "120")
    )
    await _battle_through_turn_one(p1, p2, timeout_seconds=lifecycle_timeout)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    battle = next(iter(p1.battles.values()))
    if int(getattr(battle, "turn", 0) or 0) < 1:
        raise RuntimeError("TURN1_INCOMPLETE: battle ended before turn 1")
    if our_lead is None:
        our_lead = _lead_from_preview_slots(p1)
    if our_lead is None:
        our_lead = _lead_slots_from_battle(battle, team_attr="team")
    our_four = _four_from_preview_slots(p1)
    if our_four is None:
        raise RuntimeError("PREVIEW_SLOTS_MISSING: our bring-4 not recorded")
    opp_four = _four_from_preview_slots(p2)
    if opp_four is None:
        raise RuntimeError("PREVIEW_SLOTS_MISSING: opponent bring-4 not recorded")
    if _canonical_lead((opp_four[0], opp_four[1])) != imposed:
        raise ValueError("simulated lead rejection")
    back_pair = _back_pair_from_preview_four(opp_four)
    our_lead_order = (our_four[0], our_four[1])
    if our_imposed_four is not None:
        if our_four != our_imposed_four:
            raise ValueError("observed our bring-4 mismatch with imposed selection")
    battle_format = _battle_format_for_regulation(regulation)
    payload = extract_turn_one_payload(
        battle,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        opponent_lead=imposed,
        our_lead=our_lead,
        opponent_back_pair=back_pair,
        opponent_lead_order=(opp_four[0], opp_four[1]),
        opponent_active_roster=opp_four,
        our_active_roster=our_four,
        battle_format=battle_format,
    )
    our_actions = _actions_for_side(
        battle,
        side="ours",
        lead_order=our_lead_order,
        active_roster=our_four,
        our_active_roster=our_four,
        opp_active_roster=opp_four,
        battle_format=battle_format,
    )
    result = build_turn_one(
        opponent_lead=imposed,
        our_lead=our_lead,
        actions=payload["actions"],
        back_pair=(payload["backPair"][0], payload["backPair"][1]),
        engine="vgc-bench",
        our_actions=our_actions,
    )
    body = result["payload"]
    body["ourFourSlots"] = list(our_four)
    body["opponentLeadSlots"] = list(imposed)
    body["opponentBackPair"] = list(back_pair)
    body["previewAccepted"] = {
        "ourPreviewSlots": list(our_four),
        "opponentPreviewSlots": list(opp_four),
    }
    from pokecoach_vgc_bridge.battle_capture import attach_replay_to_trace, merge_player_captures
    from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap

    identity = PokemonIdentityMap.from_snapshots(our_snapshot, opponent_snapshot)
    trace = merge_player_captures(p1.pokecoach_capture, p2.pokecoach_capture)
    attach_replay_to_trace(trace, battle, identity=identity, our_is_p1=True)
    body["turnEvents"] = [event for event in trace.events if int(event.get("turn") or 0) <= 1]
    return result


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
    from pokecoach_vgc_bridge.fixture_sim import _resolve_our_lineup

    imposed = _canonical_lead(opponent_lead)
    our_lead_raw = payload.get("ourLeadSlots")
    our_sel_raw = payload.get("ourSelection")
    opp_back_raw = payload.get("opponentBackPair")

    our_imposed_four: tuple[int, int, int, int] | None = None
    our_imposed_lead: tuple[int, int] | None = None
    opponent_imposed_four: tuple[int, int, int, int] | None = None

    if isinstance(our_sel_raw, list) and len(our_sel_raw) == 4:
        from pokecoach_vgc_bridge.battle_session import imposed_four_with_lead_order

        raw_four = tuple(int(s) for s in our_sel_raw)
        if len(set(raw_four)) != 4:
            raise ValueError("ourSelection must contain four distinct slots")
        if our_lead_raw and len(our_lead_raw) == 2:
            our_imposed_lead = (int(our_lead_raw[0]), int(our_lead_raw[1]))
            our_imposed_four = imposed_four_with_lead_order(raw_four, our_imposed_lead)
        else:
            our_imposed_four = raw_four  # type: ignore[assignment]
    elif our_lead_raw and len(our_lead_raw) == 2:
        our_imposed_lead = (int(our_lead_raw[0]), int(our_lead_raw[1]))

    if isinstance(opp_back_raw, list) and len(opp_back_raw) == 2:
        back_a, back_b = int(opp_back_raw[0]), int(opp_back_raw[1])
        if back_a == back_b:
            raise ValueError("invalid opponentBackPair")
        if back_a in opponent_lead or back_b in opponent_lead:
            raise ValueError("opponentBackPair must be disjoint from opponent lead")
        opponent_imposed_four = (
            opponent_lead[0],
            opponent_lead[1],
            back_a,
            back_b,
        )

    p1, p2 = await create_policy_pair(
        checkpoint_path=checkpoint_path,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        regulation=regulation,
        seed=seed,
        our_imposed_lead=our_imposed_lead,
        opponent_imposed_lead=imposed if opponent_imposed_four is None else None,
        our_imposed_four=our_imposed_four,
        opponent_imposed_four=opponent_imposed_four,
    )
    await p1.battle_against(p2, n_battles=1)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    battle = next(iter(p1.battles.values()))
    if not getattr(battle, "finished", False):
        raise RuntimeError("BATTLE_NOT_TERMINAL: simulator did not report finished")

    our_four_obs = _four_from_preview_slots(p1)
    opp_four_obs = _four_from_preview_slots(p2)
    if our_four_obs is None or opp_four_obs is None:
        raise RuntimeError("PREVIEW_SLOTS_MISSING: bring-4 not recorded from preview")

    if our_imposed_four is not None:
        if our_four_obs != our_imposed_four:
            raise ValueError("observed our bring-4 mismatch")
        our_four = our_four_obs
        our_lead = (our_four_obs[0], our_four_obs[1])
    else:
        our_four = our_four_obs
        preview_lead = _lead_from_preview_slots(p1)
        if preview_lead is not None:
            our_lead = preview_lead
        else:
            _, our_lead = _resolve_our_lineup(payload, seed, our_snapshot)

    if opponent_imposed_four is not None:
        if opp_four_obs != opponent_imposed_four:
            raise ValueError("observed opponent bring-4 mismatch")
        if _canonical_lead((opp_four_obs[0], opp_four_obs[1])) != imposed:
            raise ValueError("simulated lead rejection")

    opp_back = _back_pair_from_preview_four(opp_four_obs)
    battle_format = _battle_format_for_regulation(regulation)
    turn1 = extract_turn_one_payload(
        battle,
        our_snapshot=our_snapshot,
        opponent_snapshot=opponent_snapshot,
        opponent_lead=imposed,
        our_lead=our_lead,
        opponent_back_pair=opp_back,
        opponent_lead_order=(opp_four_obs[0], opp_four_obs[1]),
        opponent_active_roster=opp_four_obs,
        our_active_roster=our_four,
        battle_format=battle_format,
    )
    our_lead_order = (our_four[0], our_four[1])
    our_actions = _actions_for_side(
        battle,
        side="ours",
        lead_order=our_lead_order,
        active_roster=our_four,
        our_active_roster=our_four,
        opp_active_roster=opp_four_obs,
        battle_format=battle_format,
    )
    if p1.n_won_battles > 0:
        outcome = "win"
    elif p1.n_lost_battles > 0:
        outcome = "loss"
    elif p1.n_tied_battles > 0:
        outcome = "draw"
    else:
        raise RuntimeError("BATTLE_OUTCOME_UNKNOWN: no win/loss/tie recorded")
    turn_count = int(getattr(battle, "turn", 1) or 1)
    from pokecoach_vgc_bridge.battle_capture import attach_replay_to_trace, merge_player_captures
    from pokecoach_vgc_bridge.full_battle_trace import (
        build_turns_from_battle_summary,
        capture_terminal_state_from_battle,
        normalize_complete_battle,
    )
    from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap

    identity = PokemonIdentityMap.from_snapshots(our_snapshot, opponent_snapshot)
    trace = merge_player_captures(p1.pokecoach_capture, p2.pokecoach_capture)
    attach_replay_to_trace(trace, battle, identity=identity, our_is_p1=True)
    opponent_selected = opp_four_obs
    terminal_state = capture_terminal_state_from_battle(
        battle,
        our_selected=our_four,
        opponent_selected=opponent_selected,
    )
    turns = build_turns_from_battle_summary(
        turn_count=turn_count,
        our_actions_turn1=our_actions,
        opponent_actions_turn1=turn1["actions"],
        trace=trace,
    )
    damage_events = [event for event in trace.events if event.get("kind") == "damage"]
    if turn_count > 1:
        for turn_index in range(2, turn_count + 1):
            if not any(int(event.get("turn") or 0) == turn_index for event in trace.events):
                raise RuntimeError(
                    f"BATTLE_CAPTURE_INCOMPLETE: turn {turn_index} has no captured events"
                )
    record = normalize_complete_battle(
        opponent_lead=imposed,
        our_lead=our_lead,
        our_four=our_four,
        opponent_selected=opponent_selected,
        our_actions_turn1=our_actions,
        opponent_actions_turn1=turn1["actions"],
        outcome=outcome,
        seed=seed,
        engine="vgc-bench",
        turns=turns,
        terminal_state=terminal_state,
        terminal_evidence={
            "kind": "simulator",
            "turnCount": turn_count,
            "finished": True,
            "captureMethod": "poke-env-summary",
        },
        opponent_back_pair=opp_back,
        damage_events=damage_events,
        capture_quality={"exactHp": True, "roundedHp": False},
        trace=trace,
        engine_fingerprint="vgc-bench",
    )
    return record


def run_preview_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_policy_preview_battle(**kwargs))


def run_first_turn_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_first_turn_battle(**kwargs))


def run_full_battle_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_full_battle(**kwargs))


def deps_available() -> bool:
    return vgc_deps_available()
