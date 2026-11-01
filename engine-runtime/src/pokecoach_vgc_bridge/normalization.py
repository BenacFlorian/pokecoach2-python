"""Map bridge payloads to normalized battle records."""

from __future__ import annotations

from typing import Any

TRACE_VERSION = 1
NORMALIZER_VERSION = 1


def build_preview(
    *,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
    engine: str,
) -> dict[str, Any]:
    return {
        "opponentLeadSlots": list(opponent_lead),
        "ourLeadSlots": list(our_lead),
        "meta": {
            "engine": engine,
            "traceVersion": TRACE_VERSION,
            "normalizerVersion": NORMALIZER_VERSION,
        },
    }


def build_turn_one(
    *,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
    actions: list[dict[str, Any]],
    back_pair: tuple[int, int],
    engine: str,
    our_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    opp_actions = actions
    ours = our_actions if our_actions is not None else []
    return {
        "opponentLeadSlots": list(opponent_lead),
        "payload": {
            "opponentActions": opp_actions,
            "actions": opp_actions,
            "ourActions": ours,
            "backPair": list(back_pair),
            "ourLeadSlots": list(our_lead),
            "endStateNotes": [],
        },
        "meta": {
            "engine": engine,
            "traceVersion": TRACE_VERSION,
            "normalizerVersion": NORMALIZER_VERSION,
        },
    }


def build_battle_record(
    *,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
    our_four: tuple[int, int, int, int],
    our_actions: list[dict[str, Any]],
    opponent_actions: list[dict[str, Any]],
    outcome: str,
    seed: int,
    engine: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    participants: dict[str, Any] = {
        "ourFourSlots": list(our_four),
        "ourLeadSlots": list(our_lead),
    }
    opp_back = payload.get("opponentBackPair")
    if opp_back and len(opp_back) == 2:
        participants["opponentBackPair"] = [int(opp_back[0]), int(opp_back[1])]
    return {
        "formatVersion": 1,
        "preview": {
            "opponentLeadSlots": list(opponent_lead),
            "ourLeadSlots": list(our_lead),
            "meta": {"engine": engine},
        },
        "turns": [
            {
                "turn": 1,
                "ourActions": our_actions,
                "opponentActions": opponent_actions,
            }
        ],
        "outcome": outcome,
        "participants": participants,
        "meta": {
            "engine": engine,
            "engineFingerprint": "fixture",
            "traceVersion": TRACE_VERSION,
            "normalizerVersion": NORMALIZER_VERSION,
            "terminalEvidence": {"kind": "simulator", "turnCount": 1},
            "seed": seed,
        },
    }


def normalize_choice(
    choice: dict[str, Any],
    request_state: dict[str, Any],
    roster_map: dict[str, Any],
) -> dict[str, Any]:
    """Map a raw engine choice into a BattleAction-shaped dict."""
    _ = request_state, roster_map
    return dict(choice)
