"""Capture Showdown replay and player orders into structured battle traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pokecoach_vgc_bridge.full_battle_trace import FullBattleTrace
from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap, Side


@dataclass
class BattleCapture:
    side: Side
    teampreview_command: str | None = None
    teampreview_slots: tuple[int, ...] = ()
    orders: list[dict[str, Any]] = field(default_factory=list)

    def record_teampreview(self, choice: str, slots: tuple[int, ...] | None) -> None:
        self.teampreview_command = choice
        if slots is not None:
            self.teampreview_slots = slots

    def record_order(self, *, turn: int, order: Any) -> None:
        from pokecoach_vgc_bridge.battle_order_serialize import serialize_battle_order

        message = getattr(order, "message", None)
        self.orders.append(
            {
                "turn": int(turn),
                "order": repr(order),
                "message": str(message) if message is not None else repr(order),
                "parsed": serialize_battle_order(order),
            }
        )


def attach_player_captures_to_battle(battle: Any, p1: Any, p2: Any) -> None:
    battle.pokecoach_player_captures = {
        "ours": getattr(p1, "pokecoach_capture", None),
        "opponent": getattr(p2, "pokecoach_capture", None),
    }


def merge_player_captures(p1: BattleCapture, p2: BattleCapture) -> FullBattleTrace:
    trace = FullBattleTrace()
    for cap, side in ((p1, "ours"), (p2, "opponent")):
        if cap.teampreview_command:
            trace.choices.append(
                {
                    "kind": "teampreview",
                    "side": side,
                    "command": cap.teampreview_command,
                    "slots": list(cap.teampreview_slots),
                }
            )
        for order in cap.orders:
            trace.choices.append({"kind": "order", "side": side, **order})
    return trace


def capture_events_from_replay(
    battle: Any,
    *,
    identity: PokemonIdentityMap,
    our_is_p1: bool = True,
) -> list[dict[str, Any]]:
    replay = getattr(battle, "_replay_data", None) or []
    events: list[dict[str, Any]] = []
    hp_by_ident: dict[str, float] = {}
    turn = 0
    for split in replay:
        if len(split) < 2:
            continue
        kind = split[1]
        if kind == "turn":
            try:
                turn = int(split[2])
            except (IndexError, ValueError):
                turn += 1
            continue
        effective_turn = turn if turn >= 1 else 1
        if kind == "move":
            events.append(_parse_move_event(split, turn=effective_turn, identity=identity, our_is_p1=our_is_p1))
        elif kind == "switch":
            ident = split[2] if len(split) > 2 else ""
            if ident:
                hp_by_ident[ident] = 100.0
            events.append(_parse_switch_event(split, turn=effective_turn, identity=identity, our_is_p1=our_is_p1))
        elif kind == "-damage":
            parsed = _parse_damage_event(
                split,
                turn=effective_turn,
                identity=identity,
                our_is_p1=our_is_p1,
                hp_by_ident=hp_by_ident,
            )
            if parsed is not None:
                events.append(parsed)
        elif kind in {"-heal", "-sethp"}:
            events.append(
                {
                    "kind": "heal" if kind == "-heal" else "sethp",
                    "turn": effective_turn,
                    "raw": split[2:],
                    "provenance": "replay",
                }
            )
    return events


def attach_replay_to_trace(
    trace: FullBattleTrace,
    battle: Any,
    *,
    identity: PokemonIdentityMap,
    our_is_p1: bool = True,
) -> FullBattleTrace:
    trace.events = capture_events_from_replay(
        battle,
        identity=identity,
        our_is_p1=our_is_p1,
    )
    trace.requests.append(
        {
            "kind": "terminal",
            "turnCount": int(getattr(battle, "turn", 0) or 0),
            "finished": bool(getattr(battle, "finished", False)),
        }
    )
    return trace


def normalize_turn(
    *,
    turn: int,
    initial_our: list[dict[str, Any]],
    initial_opponent: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    turn_events = [event for event in events if int(event.get("turn") or 0) == turn]
    return {
        "turn": turn,
        "ourInitialActions": initial_our,
        "opponentInitialActions": initial_opponent,
        "events": turn_events,
    }


def _parse_move_event(
    split: list[str],
    *,
    turn: int,
    identity: PokemonIdentityMap,
    our_is_p1: bool,
) -> dict[str, Any]:
    ident = split[2] if len(split) > 2 else ""
    prefix, role = _protocol_actor(ident)
    side = identity.resolve_side_from_protocol(prefix, our_is_p1=our_is_p1)
    move = split[3] if len(split) > 3 else ""
    target_token = split[4] if len(split) > 4 else None
    return {
        "kind": "move",
        "turn": turn,
        "side": side,
        "role": role,
        "move": move,
        "targetToken": target_token,
        "provenance": "replay",
    }


def _parse_switch_event(
    split: list[str],
    *,
    turn: int,
    identity: PokemonIdentityMap,
    our_is_p1: bool,
) -> dict[str, Any]:
    ident = split[2] if len(split) > 2 else ""
    prefix, role = _protocol_actor(ident)
    side = identity.resolve_side_from_protocol(prefix, our_is_p1=our_is_p1)
    species_hint = ident.split(":")[-1].strip() if ":" in ident else ident
    return {
        "kind": "switch",
        "turn": turn,
        "side": side,
        "role": role,
        "speciesHint": species_hint,
        "provenance": "replay",
    }


def _parse_damage_event(
    split: list[str],
    *,
    turn: int,
    identity: PokemonIdentityMap,
    our_is_p1: bool,
    hp_by_ident: dict[str, float],
) -> dict[str, Any] | None:
    ident = split[2] if len(split) > 2 else ""
    if not ident:
        return None
    prefix, role = _protocol_actor(ident)
    side = identity.resolve_side_from_protocol(prefix, our_is_p1=our_is_p1)
    slot = _roster_slot_from_ident(ident, side, identity)
    if slot is None:
        return None
    hp_token = split[3] if len(split) > 3 else ""
    parsed_hp = _parse_showdown_hp_token(hp_token)
    if parsed_hp is None:
        return None
    new_pct, fainted = parsed_hp
    prev_pct = hp_by_ident.get(ident, 100.0)
    hp_by_ident[ident] = new_pct
    hp_percent_loss = max(0.0, prev_pct - new_pct)
    if hp_percent_loss <= 0.0 and not fainted:
        hp_percent_loss = 0.0
    return {
        "kind": "damage",
        "turn": turn,
        "target": identity.pokemon_ref(side, slot),
        "targetSide": side,
        "role": role,
        "hpPercentLoss": hp_percent_loss,
        "direct": True,
        "attributed": False,
        "causedKo": fainted,
        "raw": split[3:],
        "provenance": "replay",
    }


def _normalize_species_label(name: str) -> str:
    return name.strip().lower().replace("-", "").replace(" ", "")


def _roster_slot_from_ident(ident: str, side: Side, identity: PokemonIdentityMap) -> int | None:
    hint = ident.split(":")[-1].strip() if ":" in ident else ident.strip()
    if not hint:
        return None
    norm_hint = _normalize_species_label(hint)
    row = identity.our_species if side == "ours" else identity.opponent_species
    matches = [
        idx
        for idx, name in enumerate(row)
        if name and _normalize_species_label(name) == norm_hint
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return matches[0]
    for idx, name in enumerate(row):
        if name and norm_hint in _normalize_species_label(name):
            return idx
    return None


def _parse_showdown_hp_token(token: str) -> tuple[float, bool] | None:
    text = token.strip()
    if not text:
        return None
    parts = text.split()
    frac = parts[0]
    if "/" not in frac:
        return None
    cur_raw, max_raw = frac.split("/", 1)
    try:
        cur_f = float(cur_raw)
        max_f = float(max_raw)
    except ValueError:
        return None
    if max_f <= 0:
        return None
    fainted = cur_f <= 0 or any(part == "fnt" for part in parts[1:])
    pct = max(0.0, min(100.0, (cur_f / max_f) * 100.0))
    return pct, fainted


def _protocol_actor(ident: str) -> tuple[str, str]:
    token = ident.split(":")[0].strip()
    if len(token) < 3:
        raise ValueError(f"invalid protocol ident {ident}")
    return token[:2], token[2:]
