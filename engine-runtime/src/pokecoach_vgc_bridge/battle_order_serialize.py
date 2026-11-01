"""Serialize poke-env BattleOrder objects for turn-1 extraction."""

from __future__ import annotations

from typing import Any


def serialize_battle_order(order: Any) -> dict[str, Any]:
    from poke_env.battle.move import Move
    from poke_env.battle.pokemon import Pokemon
    from poke_env.player.battle_order import (
        BattleOrder,
        DefaultBattleOrder,
        DoubleBattleOrder,
        ForfeitBattleOrder,
        PassBattleOrder,
        SingleBattleOrder,
    )

    if isinstance(order, DefaultBattleOrder):
        return {"kind": "default", "message": order.message}
    if isinstance(order, ForfeitBattleOrder):
        return {"kind": "forfeit", "message": order.message}
    if isinstance(order, DoubleBattleOrder):
        return {
            "kind": "double",
            "first": _serialize_single(order.first_order),
            "second": _serialize_single(order.second_order),
        }
    if isinstance(order, SingleBattleOrder):
        return {"kind": "single", **_serialize_single(order)}
    if isinstance(order, BattleOrder):
        return {"kind": "unknown", "message": order.message}
    return {"kind": "unknown", "repr": repr(order)}


def _serialize_single(order: SingleBattleOrder) -> dict[str, Any]:
    from poke_env.battle.move import Move
    from poke_env.battle.pokemon import Pokemon
    from poke_env.player.battle_order import PassBattleOrder

    if isinstance(order, PassBattleOrder):
        return {"orderKind": "pass", "message": order.message}
    base = {
        "mega": bool(order.mega),
        "z_move": bool(order.z_move),
        "dynamax": bool(order.dynamax),
        "terastallize": bool(order.terastallize),
        "move_target": int(order.move_target),
        "message": order.message,
    }
    payload = order.order
    if isinstance(payload, Move):
        return {
            **base,
            "orderKind": "move",
            "moveId": str(payload.id),
            "moveName": str(getattr(payload, "name", payload.id) or payload.id),
        }
    if isinstance(payload, Pokemon):
        return {
            **base,
            "orderKind": "switch",
            "pokemonName": str(payload.name),
            "species": str(getattr(payload, "species", payload.name) or payload.name),
        }
    if isinstance(payload, str):
        return {**base, "orderKind": "string", "text": payload}
    return {**base, "orderKind": "unknown", "repr": repr(payload)}


def parse_doubles_choose_message(message: str) -> tuple[str, str] | None:
    """Parse poke-env DoubleBattleOrder.message into two /choose fragments."""
    text = message.strip()
    if not text.startswith("/choose ") or ", " not in text:
        return None
    left, right = text.split(", ", 1)
    left_cmd = left.removeprefix("/choose ").strip()
    right_cmd = right.strip()
    if not left_cmd or not right_cmd:
        return None
    if left_cmd.startswith("/choose "):
        left_cmd = left_cmd.removeprefix("/choose ").strip()
    if text.startswith("/choose default") or left_cmd == "default":
        return None
    return left_cmd, right_cmd


def turn1_parsed_order_from_capture(capture: Any) -> dict[str, Any] | None:
    orders = getattr(capture, "orders", None)
    if not isinstance(orders, list):
        return None
    for entry in reversed(orders):
        if not isinstance(entry, dict):
            continue
        turn = int(entry.get("turn") or 0)
        if turn > 1:
            continue
        parsed = entry.get("parsed")
        if not isinstance(parsed, dict) or parsed.get("kind") != "double":
            continue
        if _double_order_has_evidence(parsed):
            return parsed
    return None


def _double_order_has_evidence(parsed: dict[str, Any]) -> bool:
    first = parsed.get("first")
    second = parsed.get("second")
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    return _single_has_evidence(first) and _single_has_evidence(second)


def _single_has_evidence(single: dict[str, Any]) -> bool:
    kind = single.get("orderKind")
    if kind in {"move", "switch"}:
        return True
    if kind == "string":
        text = str(single.get("text") or "")
        if text.startswith("/choose"):
            return True
        if text.startswith("move ") or text.startswith("switch "):
            return True
    return False
