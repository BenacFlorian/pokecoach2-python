"""Extract normalized turn-1 actions from a finished poke-env doubles battle."""

from __future__ import annotations

import re
from typing import Any

from pokecoach_vgc_bridge.move_targets import (
    enrich_move_action,
    load_move_catalog,
    resolve_move_target,
)

# Showdown move ids without separators (replay / poke-env ids).
_MOVE_ID_ALIASES: dict[str, str] = {
    "dualwingbeat": "Dual Wingbeat",
    "closecombat": "Close Combat",
    "bravebird": "Brave Bird",
    "fakeout": "Fake Out",
    "partingshot": "Parting Shot",
    "throatchop": "Throat Chop",
    "knockoff": "Knock Off",
    "highhorsepower": "High Horsepower",
    "rockslide": "Rock Slide",
    "ironhead": "Iron Head",
    "moonblast": "Moonblast",
    "dazzlinggleam": "Dazzling Gleam",
    "hypervoice": "Hyper Voice",
    "electroweb": "Electroweb",
    "helpinghand": "Helping Hand",
    "followme": "Follow Me",
    "ragepowder": "Rage Powder",
    "trickroom": "Trick Room",
    "tailwind": "Tailwind",
    "protect": "Protect",
    "wideguard": "Wide Guard",
    "quickguard": "Quick Guard",
}

_DEFAULT_BATTLE_FORMAT = "gen9championsvgc2026regma"


def extract_turn_one_payload(
    battle: Any,
    *,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
    opponent_back_pair: tuple[int, int] | None = None,
    opponent_lead_order: tuple[int, int] | None = None,
    opponent_active_roster: tuple[int, int, int, int] | None = None,
    our_active_roster: tuple[int, int, int, int] | None = None,
    battle_format: str = _DEFAULT_BATTLE_FORMAT,
) -> dict[str, Any]:
    """Build turn-1 payload from battle state after turn 1 resolved."""
    _ = our_snapshot, opponent_snapshot
    lead_order = opponent_lead_order or opponent_lead
    opp_actions = _actions_for_side(
        battle,
        side="opponent",
        lead_order=lead_order,
        active_roster=opponent_active_roster,
        our_active_roster=our_active_roster,
        opp_active_roster=opponent_active_roster,
        battle_format=battle_format,
    )
    if opponent_back_pair is not None:
        back_pair = opponent_back_pair
    else:
        back_pair = _back_pair_from_team(battle, lead=opponent_lead)
    return {
        "actions": opp_actions,
        "backPair": list(back_pair),
        "ourLeadSlots": list(our_lead),
        "endStateNotes": [f"turn={getattr(battle, 'turn', '?')}"],
    }


def _mon_for_roster_slot(
    team: list[Any],
    roster_slot: int,
    active_roster: tuple[int, ...] | None,
) -> Any | None:
    if roster_slot < 0 or roster_slot >= 6:
        raise RuntimeError(
            f"TURN1_EXTRACT: lead slot {roster_slot} out of roster range"
        )
    if len(team) >= 6:
        if roster_slot >= len(team):
            raise RuntimeError(
                f"TURN1_EXTRACT: lead slot {roster_slot} out of team range (size={len(team)})"
            )
        return team[roster_slot]
    if active_roster is None:
        raise RuntimeError(
            f"TURN1_EXTRACT: lead slot {roster_slot} out of team range (size={len(team)})"
        )
    if roster_slot not in active_roster:
        raise RuntimeError(
            f"TURN1_EXTRACT: roster slot {roster_slot} not in active bring-4 {active_roster}"
        )
    team_idx = active_roster.index(roster_slot)
    if team_idx >= len(team):
        return None
    return team[team_idx]


def _actions_for_side(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    active_roster: tuple[int, ...] | None = None,
    our_active_roster: tuple[int, ...] | None = None,
    opp_active_roster: tuple[int, ...] | None = None,
    battle_format: str = _DEFAULT_BATTLE_FORMAT,
) -> list[dict[str, Any]]:
    target_side = "ours" if side == "opponent" else "opponent"
    from_orders = _turn1_actions_from_player_captures(
        battle,
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        active_roster=active_roster,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )
    if from_orders is not None:
        return from_orders

    from_replay = _turn1_actions_from_replay(
        battle,
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )
    if from_replay is not None:
        return from_replay

    from_trace = _turn1_actions_from_traced_events(
        battle,
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )
    if from_trace is not None:
        return from_trace

    from_active = _turn1_actions_from_active_positions(
        battle,
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        active_roster=active_roster,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )
    if from_active is not None:
        return from_active

    from_team = _turn1_actions_from_team_state(
        battle,
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        active_roster=active_roster,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )
    if from_team is not None:
        return from_team

    raise ValueError("TURN1_EXTRACT: move evidence missing for active lead")


def _turn1_actions_from_player_captures(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    active_roster: tuple[int, ...] | None,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str,
) -> list[dict[str, Any]] | None:
    captures = getattr(battle, "pokecoach_player_captures", None)
    if not isinstance(captures, dict):
        return None
    capture = captures.get(side)
    if capture is None:
        return None
    from pokecoach_vgc_bridge.battle_order_serialize import (
        parse_doubles_choose_message,
        turn1_parsed_order_from_capture,
    )

    parsed = turn1_parsed_order_from_capture(capture)
    if parsed is None:
        for entry in reversed(getattr(capture, "orders", []) or []):
            if not isinstance(entry, dict):
                continue
            if int(entry.get("turn") or 0) > 1:
                continue
            msg = entry.get("message")
            if isinstance(msg, str):
                fragments = parse_doubles_choose_message(msg)
                if fragments is not None:
                    parsed = {
                        "kind": "message",
                        "first": {"orderKind": "string", "text": fragments[0]},
                        "second": {"orderKind": "string", "text": fragments[1]},
                    }
                    break
    if parsed is None:
        return None
    catalog = load_move_catalog(battle_format)
    slot_a, slot_b = int(lead_order[0]), int(lead_order[1])
    roster = our_active_roster if side == "ours" else opp_active_roster
    out: list[dict[str, Any]] = []
    for role, slot, single_key in (("a", slot_a, "first"), ("b", slot_b, "second")):
        single = parsed.get(single_key)
        if not isinstance(single, dict):
            return None
        action = _action_from_parsed_single(
            battle,
            side=side,
            slot=slot,
            single=single,
            active_roster=roster,
            our_active_roster=our_active_roster,
            opp_active_roster=opp_active_roster,
        )
        if action is None:
            return None
        if action.get("kind") == "move":
            move = str(action.get("move") or "")
            target_roster = action.pop("_target_roster_slot", None)
            info = resolve_move_target(move, catalog)
            out.append(
                enrich_move_action(
                    action,
                    info,
                    actor_side=side,
                    actor_slot=slot,
                    target_side=target_side,
                    target_roster_slot=target_roster,
                )
            )
        else:
            out.append(action)
        _ = role
    return out if len(out) == 2 else None


def _action_from_parsed_single(
    battle: Any,
    *,
    side: str,
    slot: int,
    single: dict[str, Any],
    active_roster: tuple[int, ...] | None,
    our_active_roster: tuple[int, ...] | None = None,
    opp_active_roster: tuple[int, ...] | None = None,
) -> dict[str, Any] | None:
    kind = single.get("orderKind")
    if kind == "move":
        move_id = str(single.get("moveId") or single.get("moveName") or "")
        move = _normalize_showdown_move_name(move_id)
        if move == "Unknown":
            return None
        target_roster = _target_roster_from_move_target(
            battle,
            side=side,
            move_target=int(single.get("move_target") or 0),
            target_side="ours" if side == "opponent" else "opponent",
            our_active_roster=our_active_roster,
            opp_active_roster=opp_active_roster,
        )
        action = _move_action(side=side, slot=slot, move=move, targets=[])
        if target_roster is not None:
            action["_target_roster_slot"] = target_roster
        return action
    if kind == "switch":
        switch_to = _roster_slot_from_parsed_switch(
            battle,
            side=side,
            single=single,
            active_roster=active_roster,
        )
        if switch_to is None:
            return None
        return {
            "kind": "switch",
            "actor": {"side": side, "slot": slot},
            "switchTo": {"side": side, "slot": switch_to},
        }
    if kind == "string":
        text = str(single.get("text") or single.get("message") or "").strip()
        if text.startswith("/choose "):
            text = text.removeprefix("/choose ").strip()
        if text.startswith("switch "):
            name = text.removeprefix("switch ").strip()
            switch_to = _roster_slot_from_species_hint(
                battle,
                side=side,
                species_hint=name,
                active_roster=active_roster,
            )
            if switch_to is None:
                return None
            return {
                "kind": "switch",
                "actor": {"side": side, "slot": slot},
                "switchTo": {"side": side, "slot": switch_to},
            }
        if text.startswith("move "):
            tokens = text.split()
            move = _normalize_showdown_move_name(tokens[1] if len(tokens) > 1 else "")
            if move == "Unknown":
                return None
            action = _move_action(side=side, slot=slot, move=move, targets=[])
            if len(tokens) > 2 and tokens[2].lstrip("-").isdigit():
                action["_target_roster_slot"] = _target_roster_from_move_target(
                    battle,
                    side=side,
                    move_target=int(tokens[2]),
                    target_side="ours" if side == "opponent" else "opponent",
                    our_active_roster=our_active_roster,
                    opp_active_roster=opp_active_roster,
                )
            return action
    return None


def _roster_slot_from_parsed_switch(
    battle: Any,
    *,
    side: str,
    single: dict[str, Any],
    active_roster: tuple[int, ...] | None,
) -> int | None:
    for key in ("pokemonName", "species"):
        hint = single.get(key)
        if isinstance(hint, str) and hint.strip():
            slot = _roster_slot_from_species_hint(
                battle,
                side=side,
                species_hint=hint.strip(),
                active_roster=active_roster,
            )
            if slot is not None:
                return slot
    return None


def _roster_slot_from_species_hint(
    battle: Any,
    *,
    side: str,
    species_hint: str,
    active_roster: tuple[int, ...] | None,
) -> int | None:
    hint = species_hint.lower().replace("-", "").replace(" ", "")
    team = (
        list(getattr(battle, "team", {}).values())
        if side == "ours"
        else list(getattr(battle, "opponent_team", {}).values())
    )
    for idx, candidate in enumerate(team):
        names = [
            str(getattr(candidate, "species", "") or ""),
            str(getattr(candidate, "name", "") or ""),
        ]
        for name in names:
            norm = name.lower().replace("-", "").replace(" ", "")
            if norm and norm == hint:
                if active_roster and len(team) < 6 and idx < len(active_roster):
                    return int(active_roster[idx])
                return idx
    return None


def _field_lead_roster_pair(
    target_side: str,
    *,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
) -> tuple[int, int] | None:
    roster = our_active_roster if target_side == "ours" else opp_active_roster
    if roster and len(roster) >= 2:
        return (int(roster[0]), int(roster[1]))
    return None


def _showdown_target_active_index(move_target: int, *, foe: bool) -> int | None:
    """Map poke-env Showdown target (-2..2) to active slot index 0 or 1."""
    if foe:
        if move_target == 1:
            return 0
        if move_target == 2:
            return 1
        return None
    if move_target == -1:
        return 0
    if move_target == -2:
        return 1
    return None


def _roster_slot_for_team_mon(
    mon: Any,
    *,
    team: list[Any],
    roster: tuple[int, ...] | None,
    field_pos: int | None,
    target_side: str,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
) -> int | None:
    pair = _field_lead_roster_pair(
        target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
    )
    if pair is not None and field_pos in (0, 1):
        return int(pair[field_pos])
    for idx, candidate in enumerate(team):
        if candidate is mon:
            if roster and len(team) < 6 and idx < len(roster):
                return int(roster[idx])
            return idx
    return None


def _target_roster_from_move_target(
    battle: Any,
    *,
    side: str,
    move_target: int,
    target_side: str,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
) -> int | None:
    if move_target == 0:
        return None
    if move_target in (1, 2):
        pos = _showdown_target_active_index(move_target, foe=True)
        if pos is None:
            return None
        if target_side == "ours":
            actives = getattr(battle, "active_pokemon", None) or []
            roster = our_active_roster
            team = list(getattr(battle, "team", {}).values())
        else:
            actives = getattr(battle, "opponent_active_pokemon", None) or []
            roster = opp_active_roster
            team = list(getattr(battle, "opponent_team", {}).values())
    elif move_target in (-1, -2):
        pos = _showdown_target_active_index(move_target, foe=False)
        if pos is None:
            return None
        if side == "ours":
            actives = getattr(battle, "active_pokemon", None) or []
            roster = our_active_roster
            team = list(getattr(battle, "team", {}).values())
            target_side = "ours"
        else:
            actives = getattr(battle, "opponent_active_pokemon", None) or []
            roster = opp_active_roster
            team = list(getattr(battle, "opponent_team", {}).values())
            target_side = "opponent"
    else:
        return None
    if pos >= len(actives) or actives[pos] is None:
        pair = _field_lead_roster_pair(
            target_side,
            our_active_roster=our_active_roster,
            opp_active_roster=opp_active_roster,
        )
        if pair is not None:
            return int(pair[pos])
        return None
    mon = actives[pos]
    return _roster_slot_for_team_mon(
        mon,
        team=team,
        roster=roster,
        field_pos=pos,
        target_side=target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
    )


def _turn1_actions_from_team_state(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    active_roster: tuple[int, ...] | None,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str,
) -> list[dict[str, Any]] | None:
    if side == "opponent":
        team = list(getattr(battle, "opponent_team", {}).values())
    else:
        team = list(getattr(battle, "team", {}).values())
    catalog = load_move_catalog(battle_format)
    actions: list[dict[str, Any]] = []
    for slot in lead_order:
        mon = _mon_for_roster_slot(team, int(slot), active_roster)
        if mon is None:
            return None
        move = _move_label(mon, strict=False)
        if move == "Unknown":
            return None
        request_target = _request_target_from_mon(mon)
        info = resolve_move_target(move, catalog, request_target=request_target)
        action = _move_action(side=side, slot=int(slot), move=move, targets=[])
        actions.append(
            enrich_move_action(
                action,
                info,
                actor_side=side,
                actor_slot=int(slot),
                target_side=target_side,
                target_roster_slot=None,
            )
        )
    return actions if len(actions) == 2 else None


def _turn1_actions_from_replay(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str = _DEFAULT_BATTLE_FORMAT,
) -> list[dict[str, Any]] | None:
    replay = getattr(battle, "_replay_data", None)
    if not replay:
        return None
    side_prefix = _side_prefix(side)
    turn = 0
    moves: dict[str, tuple[str, str | None]] = {}
    switches: dict[str, str] = {}
    unassigned_moves: list[tuple[str, str | None]] = []
    unassigned_switches: list[str] = []

    for split in replay:
        if len(split) < 2:
            continue
        kind = split[1]
        if kind == "turn":
            try:
                turn = int(split[2])
            except (IndexError, ValueError):
                turn += 1
            if turn > 1:
                break
            continue
        effective_turn = turn if turn >= 1 else 1
        if effective_turn > 1:
            continue
        if kind == "switch":
            ident = split[2] if len(split) > 2 else ""
            if not _side_ident_matches(ident, side_prefix):
                continue
            role = _role_from_side_ident(ident, side_prefix)
            if role is not None and role not in switches:
                switches[role] = ident
            elif role is None:
                unassigned_switches.append(ident)
            continue
        if kind not in {"move", "-anim"}:
            continue
        ident = split[2] if len(split) > 2 else ""
        if not _side_ident_matches(ident, side_prefix):
            continue
        role = _role_from_side_ident(ident, side_prefix)
        move_raw = split[3] if len(split) > 3 else ""
        move = _normalize_showdown_move_name(move_raw)
        if move == "Unknown":
            continue
        target_token = split[4] if len(split) > 4 else None
        if role is not None and role not in moves:
            moves[role] = (move, target_token)
        elif role is None:
            unassigned_moves.append((move, target_token))

    for role in ("a", "b"):
        if role in moves or role in switches:
            continue
        if unassigned_moves:
            moves[role] = unassigned_moves.pop(0)
        elif unassigned_switches:
            switches[role] = unassigned_switches.pop(0)

    return _assemble_turn1_actions(
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        moves=moves,
        switches=switches,
        battle=battle,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )


def _side_prefix(side: str) -> str:
    return "p2" if side == "opponent" else "p1"


def _role_from_side_ident(ident: str, side_prefix: str) -> str | None:
    token = ident.split(":")[0].strip().lower()
    if token == f"{side_prefix}a":
        return "a"
    if token == f"{side_prefix}b":
        return "b"
    if token == side_prefix:
        return None
    return None


def _side_ident_matches(ident: str, side_prefix: str) -> bool:
    token = ident.split(":")[0].strip().lower()
    return token == side_prefix or token.startswith(f"{side_prefix}a") or token.startswith(
        f"{side_prefix}b"
    )


def _assemble_turn1_actions(
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    moves: dict[str, tuple[str, str | None]],
    switches: dict[str, str],
    battle: Any,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str,
) -> list[dict[str, Any]] | None:
    slot_a, slot_b = int(lead_order[0]), int(lead_order[1])
    catalog = load_move_catalog(battle_format)
    out: list[dict[str, Any]] = []
    active_roster = our_active_roster if side == "ours" else opp_active_roster
    for role, slot in (("a", slot_a), ("b", slot_b)):
        if role in moves:
            move, target_token = moves[role]
            target_roster = _target_roster_slot_from_token(
                battle,
                target_token,
                target_side=target_side,
                our_active_roster=our_active_roster,
                opp_active_roster=opp_active_roster,
            )
            info = resolve_move_target(move, catalog)
            action = _move_action(side=side, slot=slot, move=move, targets=[])
            out.append(
                enrich_move_action(
                    action,
                    info,
                    actor_side=side,
                    actor_slot=slot,
                    target_side=target_side,
                    target_roster_slot=target_roster,
                )
            )
            continue
        if role in switches:
            switch_to = _roster_slot_from_switch_ident(
                battle,
                switches[role],
                side=side,
                active_roster=active_roster,
            )
            if switch_to is None:
                return None
            out.append(
                {
                    "kind": "switch",
                    "actor": {"side": side, "slot": slot},
                    "switchTo": {"side": side, "slot": switch_to},
                }
            )
            continue
        return None
    return out if len(out) == 2 else None


def _turn1_actions_from_traced_events(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str,
) -> list[dict[str, Any]] | None:
    from pokecoach_vgc_bridge.battle_capture import capture_events_from_replay
    from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap

    identity = PokemonIdentityMap.from_snapshots(
        {"pokemon": [{}] * 6},
        {"pokemon": [{}] * 6},
    )
    events = capture_events_from_replay(battle, identity=identity, our_is_p1=True)
    moves: dict[str, tuple[str, str | None]] = {}
    switches: dict[str, str] = {}
    for event in events:
        if int(event.get("turn") or 0) != 1:
            continue
        if event.get("side") != side:
            continue
        role = event.get("role")
        if not isinstance(role, str):
            continue
        if event.get("kind") == "move" and role not in moves:
            moves[role] = (
                _normalize_showdown_move_name(str(event.get("move") or "")),
                event.get("targetToken") if isinstance(event.get("targetToken"), str) else None,
            )
        elif event.get("kind") == "switch" and role not in switches:
            species = str(event.get("speciesHint") or "")
            switches[role] = f"{_side_prefix(side)}{role}: {species}"
    return _assemble_turn1_actions(
        side=side,
        lead_order=lead_order,
        target_side=target_side,
        moves=moves,
        switches=switches,
        battle=battle,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
        battle_format=battle_format,
    )


def _turn1_actions_from_active_positions(
    battle: Any,
    *,
    side: str,
    lead_order: tuple[int, int],
    target_side: str,
    active_roster: tuple[int, ...] | None,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
    battle_format: str,
) -> list[dict[str, Any]] | None:
    if side == "opponent":
        actives = getattr(battle, "opponent_active_pokemon", None)
    else:
        actives = getattr(battle, "active_pokemon", None)
    if not isinstance(actives, list) or len(actives) < 2:
        return None
    if actives[0] is None or actives[1] is None:
        return None
    catalog = load_move_catalog(battle_format)
    actions: list[dict[str, Any]] = []
    for position, mon in enumerate(actives[:2]):
        actor_slot = int(lead_order[position])
        move = _move_label(mon, strict=False)
        if move == "Unknown":
            last = getattr(mon, "last_move", None)
            if last is not None:
                raw = getattr(last, "id", None) or getattr(last, "name", None) or last
                move = _normalize_showdown_move_name(str(raw))
        if move == "Unknown":
            return None
        request_target = _request_target_from_mon(mon)
        info = resolve_move_target(move, catalog, request_target=request_target)
        action = _move_action(side=side, slot=actor_slot, move=move, targets=[])
        actions.append(
            enrich_move_action(
                action,
                info,
                actor_side=side,
                actor_slot=actor_slot,
                target_side=target_side,
                target_roster_slot=None,
            )
        )
    return actions if len(actions) == 2 else None


def _roster_slot_from_switch_ident(
    battle: Any,
    ident: str,
    *,
    side: str,
    active_roster: tuple[int, ...] | None,
) -> int | None:
    try:
        mon = battle.get_pokemon(ident.split(":")[0].strip())
    except Exception:
        mon = None
    if mon is None:
        species_hint = ident.split(":")[-1].strip().lower()
        team = (
            list(getattr(battle, "team", {}).values())
            if side == "ours"
            else list(getattr(battle, "opponent_team", {}).values())
        )
        for idx, candidate in enumerate(team):
            name = str(getattr(candidate, "species", "") or getattr(candidate, "name", "")).lower()
            if species_hint and name == species_hint:
                if active_roster and len(team) < 6 and idx < len(active_roster):
                    return int(active_roster[idx])
                return idx
        return None
    if side == "ours":
        team = list(getattr(battle, "team", {}).values())
    else:
        team = list(getattr(battle, "opponent_team", {}).values())
    for idx, candidate in enumerate(team):
        if candidate is mon:
            if active_roster and len(team) < 6 and idx < len(active_roster):
                return int(active_roster[idx])
            return idx
    return None


def _target_side_prefix(target_side: str) -> str:
    return "p1" if target_side == "ours" else "p2"


def _active_role_from_target_token(token: str, target_side: str) -> str | None:
    prefix = _target_side_prefix(target_side)
    ident = token.split(":")[0].strip().lower()
    if ident == f"{prefix}a":
        return "a"
    if ident == f"{prefix}b":
        return "b"
    return None


def _target_roster_slot_from_token(
    battle: Any,
    token: str | None,
    *,
    target_side: str,
    our_active_roster: tuple[int, ...] | None,
    opp_active_roster: tuple[int, ...] | None,
) -> int | None:
    if not token or token.startswith("[") or token in {"all", "shift"}:
        return None
    if not (token.startswith("p1") or token.startswith("p2")):
        return None
    role = _active_role_from_target_token(token, target_side)
    pair = _field_lead_roster_pair(
        target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
    )
    if role is not None and pair is not None:
        return int(pair[0] if role == "a" else pair[1])
    try:
        mon = battle.get_pokemon(token)
    except Exception:
        return None
    if target_side == "ours":
        actives = getattr(battle, "active_pokemon", None) or []
        team = list(getattr(battle, "team", {}).values())
        roster = our_active_roster
    else:
        actives = getattr(battle, "opponent_active_pokemon", None) or []
        team = list(getattr(battle, "opponent_team", {}).values())
        roster = opp_active_roster
    for pos, active_mon in enumerate(actives[:2]):
        if active_mon is mon and pair is not None:
            return int(pair[pos])
    return _roster_slot_for_team_mon(
        mon,
        team=team,
        roster=roster,
        field_pos=None,
        target_side=target_side,
        our_active_roster=our_active_roster,
        opp_active_roster=opp_active_roster,
    )


def _request_target_from_mon(mon: Any) -> Any:
    for move in getattr(mon, "moves", {}).values():
        if getattr(move, "is_last_used", False):
            return getattr(move, "target", None)
    for attr in ("last_move", "prepared_move"):
        val = getattr(mon, attr, None)
        if val is not None:
            return getattr(val, "target", None)
    return None


def _move_action(
    *,
    side: str,
    slot: int,
    move: str,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    if move.lower() in {"switch", "pass"} or move.startswith("Switch"):
        switch_slot = 0
        if targets and targets[0].get("kind") == "pokemon":
            switch_slot = int(targets[0]["ref"]["slot"])
        return {
            "kind": "switch",
            "actor": {"side": side, "slot": slot},
            "switchTo": {"side": side, "slot": switch_slot},
        }
    return {
        "kind": "move",
        "actor": {"side": side, "slot": slot},
        "move": move,
        "targets": targets,
    }


def _normalize_showdown_move_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        return "Unknown"
    key = name.lower().replace("-", "").replace(" ", "")
    if key in _MOVE_ID_ALIASES:
        return _MOVE_ID_ALIASES[key]
    if name.lower() == "unknown":
        return "Unknown"
    if name.lower().startswith("hiddenpower"):
        return "Hidden Power"
    if " " in name or "-" in name:
        return name.replace("-", " ")
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    if spaced != name:
        return spaced
    return name.replace("_", " ").title()


def _move_label(mon: Any, *, strict: bool = False) -> str:
    for move in getattr(mon, "moves", {}).values():
        if getattr(move, "is_last_used", False):
            label = getattr(move, "name", None) or getattr(move, "id", None) or move
            return _normalize_showdown_move_name(str(label))
    for attr in ("last_move", "prepared_move"):
        val = getattr(mon, attr, None)
        if val is not None:
            label = getattr(val, "name", None) or getattr(val, "id", None) or val
            return _normalize_showdown_move_name(str(label))
    if strict:
        raise RuntimeError("TURN1_EXTRACT: move evidence missing for active lead")
    return "Unknown"


def _back_pair_from_team(battle: Any, *, lead: tuple[int, int]) -> tuple[int, int]:
    team = list(getattr(battle, "opponent_team", {}).values())
    if len(team) < 6:
        pool = [s for s in range(6) if s not in lead]
        return (pool[0], pool[1]) if len(pool) >= 2 else (0, 1)
    back = [idx for idx in range(6) if idx not in lead]
    if len(back) < 2:
        back = [i for i in range(6) if i not in {lead[0], lead[1]}][:2]
    return (back[0], back[1]) if back[0] < back[1] else (back[1], back[0])
