"""Extract normalized turn-1 actions from a finished poke-env doubles battle."""

from __future__ import annotations

from typing import Any


def extract_turn_one_payload(
    battle: Any,
    *,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
) -> dict[str, Any]:
    """Build turn-1 payload from battle state after turn 1 resolved."""
    _ = our_snapshot, opponent_snapshot
    opp_actions = _actions_for_side(battle, side="opponent", lead=opponent_lead)
    back_pair = _back_pair_from_team(battle, lead=opponent_lead)
    return {
        "actions": opp_actions,
        "backPair": list(back_pair),
        "ourLeadSlots": list(our_lead),
        "endStateNotes": [f"turn={getattr(battle, 'turn', '?')}"],
    }


def _actions_for_side(
    battle: Any,
    *,
    side: str,
    lead: tuple[int, int],
) -> list[dict[str, Any]]:
    if side == "opponent":
        active = getattr(battle, "opponent_active_pokemon", None) or []
        team = list(getattr(battle, "opponent_team", {}).values())
    else:
        active = getattr(battle, "active_pokemon", None) or []
        team = list(getattr(battle, "team", {}).values())
    actions: list[dict[str, Any]] = []
    for mon in active[:2]:
        slot = _slot_index(team, mon)
        if slot is None:
            slot = lead[len(actions)] if len(actions) < 2 else 0
        move = _move_label(mon)
        actions.append(
            {
                "kind": "move",
                "actor": {"side": side, "slot": slot},
                "move": move,
                "targets": [
                    {
                        "kind": "pokemon",
                        "ref": {
                            "side": "ours" if side == "opponent" else "opponent",
                            "slot": 0,
                        },
                    }
                ],
            }
        )
    if len(actions) < 2:
        raise RuntimeError("TURN1_EXTRACT: fewer than two actions recorded")
    return actions


def _slot_index(team: list[Any], mon: Any) -> int | None:
    for idx, candidate in enumerate(team):
        if candidate is mon:
            return idx
    return None


def _move_label(mon: Any) -> str:
    for attr in ("last_move", "prepared_move", "move"):
        val = getattr(mon, attr, None)
        if val is not None:
            if hasattr(val, "id"):
                return str(val.id).replace("_", " ").title()
            return str(val)
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
