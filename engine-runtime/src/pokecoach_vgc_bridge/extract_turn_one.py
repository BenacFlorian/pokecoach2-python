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
) -> Any:
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
        raise RuntimeError(
            f"TURN1_EXTRACT: mapped index {team_idx} out of team range (size={len(team)})"
        )
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

    if side == "opponent":
        team = list(getattr(battle, "opponent_team", {}).values())
    else:
        team = list(getattr(battle, "team", {}).values())

    catalog = load_move_catalog(battle_format)

    actions: list[dict[str, Any]] = []
    for slot in lead_order:
        mon = _mon_for_roster_slot(team, int(slot), active_roster)
        move = _move_label(mon)
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
    if len(actions) != 2:
        raise RuntimeError("TURN1_EXTRACT: expected two lead actions")
    return actions


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
    prefix = "p2" if side == "opponent" else "p1"
    target_prefix = "p1" if side == "opponent" else "p2"
    turn = 0
    moves: dict[str, tuple[str, str | None]] = {}

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
        if kind != "move":
            continue
        effective_turn = turn if turn >= 1 else 1
        if effective_turn > 1:
            continue
        ident = split[2]
        if not ident.startswith(f"{prefix}a:") and not ident.startswith(f"{prefix}b:"):
            continue
        role = "a" if ident.startswith(f"{prefix}a:") else "b"
        if role in moves:
            continue
        move_raw = split[3] if len(split) > 3 else ""
        move = _normalize_showdown_move_name(move_raw)
        target_token = split[4] if len(split) > 4 else None
        moves[role] = (move, target_token)

    if "a" not in moves or "b" not in moves:
        return None

    slot_a, slot_b = int(lead_order[0]), int(lead_order[1])
    catalog = load_move_catalog(battle_format)
    out: list[dict[str, Any]] = []
    for role, slot in (("a", slot_a), ("b", slot_b)):
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
    return out


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
    try:
        mon = battle.get_pokemon(token)
    except Exception:
        return None
    if target_side == "ours":
        team = list(getattr(battle, "team", {}).values())
        active = our_active_roster
    else:
        team = list(getattr(battle, "opponent_team", {}).values())
        active = opp_active_roster
    for idx, candidate in enumerate(team):
        if candidate is mon:
            if len(team) >= 6:
                return idx
            if active and idx < len(active):
                return int(active[idx])
            return idx
    return None


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


def _move_label(mon: Any) -> str:
    for move in getattr(mon, "moves", {}).values():
        if getattr(move, "is_last_used", False):
            label = getattr(move, "name", None) or getattr(move, "id", None) or move
            return _normalize_showdown_move_name(str(label))
    for attr in ("last_move", "prepared_move"):
        val = getattr(mon, attr, None)
        if val is not None:
            label = getattr(val, "name", None) or getattr(val, "id", None) or val
            return _normalize_showdown_move_name(str(label))
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
