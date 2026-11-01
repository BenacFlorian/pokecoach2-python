"""Passive capture and normalization of complete full-battle traces for Phase E."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pokecoach_vgc_bridge.normalization import NORMALIZER_VERSION, TRACE_VERSION


@dataclass
class FullBattleTrace:
    trace_version: int = 1
    requests: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceVersion": self.trace_version,
            "requests": self.requests,
            "choices": self.choices,
            "events": self.events,
        }


Outcome = Literal["win", "loss", "draw"]


def normalize_complete_battle(
    *,
    opponent_lead: tuple[int, int],
    our_lead: tuple[int, int],
    our_four: tuple[int, int, int, int],
    opponent_selected: tuple[int, int, int, int],
    our_actions_turn1: list[dict[str, Any]],
    opponent_actions_turn1: list[dict[str, Any]],
    outcome: Outcome,
    seed: int,
    engine: str,
    turns: list[dict[str, Any]],
    terminal_state: dict[str, Any],
    terminal_evidence: dict[str, Any],
    opponent_back_pair: tuple[int, int] | None = None,
    damage_events: list[dict[str, Any]] | None = None,
    capture_quality: dict[str, Any] | None = None,
    trace: FullBattleTrace | None = None,
    engine_fingerprint: str | None = None,
) -> dict[str, Any]:
    turn_count = int(terminal_evidence.get("turnCount") or len(turns))
    if turn_count != len(turns):
        raise ValueError("turnCount must match number of stored turns")
    if turn_count < 1:
        raise ValueError("complete battle requires at least one turn")
    participants: dict[str, Any] = {
        "ourFourSlots": list(our_four),
        "ourLeadSlots": list(our_lead),
        "opponentSelectedSlots": list(opponent_selected),
    }
    if opponent_back_pair is not None:
        participants["opponentBackPair"] = list(opponent_back_pair)
    meta: dict[str, Any] = {
        "engine": engine,
        "engineFingerprint": engine_fingerprint or engine,
        "traceVersion": TRACE_VERSION,
        "normalizerVersion": NORMALIZER_VERSION,
        "terminalEvidence": terminal_evidence,
        "terminalState": terminal_state,
        "seed": seed,
        "captureQuality": capture_quality or {"exactHp": False, "roundedHp": True},
    }
    if damage_events:
        meta["damageEvents"] = list(damage_events)
    if trace is not None:
        meta["trace"] = trace.to_dict()
    if turns and turns[0].get("turn") == 1:
        first = dict(turns[0])
        first.setdefault("ourActions", our_actions_turn1)
        first.setdefault("opponentActions", opponent_actions_turn1)
        turns = [first, *turns[1:]]
    return {
        "formatVersion": 1,
        "preview": {
            "opponentLeadSlots": list(opponent_lead),
            "ourLeadSlots": list(our_lead),
            "meta": {"engine": engine},
        },
        "turns": turns,
        "outcome": outcome,
        "participants": participants,
        "meta": meta,
    }


def build_fixture_complete_trace(
    *,
    seed: int,
    outcome: Outcome,
    opponent_lead: tuple[int, int],
    our_four: tuple[int, int, int, int],
    our_lead: tuple[int, int],
    opponent_selected: tuple[int, int, int, int],
    our_actions_turn1: list[dict[str, Any]],
    opponent_actions_turn1: list[dict[str, Any]],
    digest_byte: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Deterministic multi-turn trace for fixture/stub engines (no hidden information)."""
    _ = seed
    turn_count = 1 + (digest_byte % 3)
    our_survivors, opp_survivors = _fixture_survivors(
        outcome,
        our_lead,
        opponent_lead,
        opponent_selected,
        turn_count,
        digest_byte,
    )
    damage_events: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for turn_index in range(1, turn_count + 1):
        events: list[dict[str, Any]] = []
        if turn_index == 1 and outcome == "loss":
            events.append(
                {
                    "kind": "damage",
                    "turn": 1,
                    "source": {"side": "opponent", "slot": opponent_lead[0]},
                    "target": {"side": "ours", "slot": our_lead[0]},
                    "hpPercentLoss": 42.0,
                    "direct": True,
                    "attributed": True,
                }
            )
            damage_events.append(events[-1])
        if turn_index == turn_count and outcome == "win":
            events.append(
                {
                    "kind": "damage",
                    "turn": turn_count,
                    "source": {"side": "ours", "slot": our_lead[1]},
                    "target": {"side": "opponent", "slot": opponent_lead[1]},
                    "hpPercentLoss": 100.0,
                    "direct": True,
                    "attributed": True,
                    "causedKo": True,
                }
            )
            damage_events.append(events[-1])
        turns.append(
            {
                "turn": turn_index,
                "ourActions": our_actions_turn1 if turn_index == 1 else [],
                "opponentActions": opponent_actions_turn1 if turn_index == 1 else [],
                "events": events,
            }
        )
    terminal_state = {
        "ours": {
            "selectedSlots": list(our_four),
            "enteredSlots": list(_entered_slots(our_four, our_survivors, digest_byte, side="ours")),
            "survivorSlots": list(our_survivors),
        },
        "opponent": {
            "selectedSlots": list(opponent_selected),
            "enteredSlots": list(
                _entered_slots(opponent_selected, opp_survivors, digest_byte, side="opponent")
            ),
            "survivorSlots": list(opp_survivors),
        },
    }
    terminal_evidence = {
        "kind": "simulator",
        "turnCount": turn_count,
        "finished": True,
        "captureMethod": "fixture-synthetic",
    }
    return turns, terminal_state, damage_events


def capture_terminal_state_from_battle(
    battle: Any,
    *,
    our_selected: tuple[int, int, int, int],
    opponent_selected: tuple[int, int, int, int],
) -> dict[str, Any]:
    """Read terminal HP/KO state from a finished poke-env doubles battle."""
    from pokecoach_vgc_bridge.extract_turn_one import _mon_for_roster_slot

    p1_team = list(battle.team.values())
    p2_team = list(battle.opponent_team.values())

    def side_state(
        team: list[Any],
        selected: tuple[int, int, int, int],
        *,
        active_roster: tuple[int, int, int, int] | None,
    ) -> dict[str, Any]:
        survivors: list[int] = []
        entered: list[int] = []
        for slot in selected:
            mon = _mon_for_roster_slot(team, int(slot), active_roster)
            if getattr(mon, "active", False) or getattr(mon, "fainted", False):
                entered.append(slot)
            elif getattr(mon, "current_hp", 0) < getattr(mon, "max_hp", 1):
                entered.append(slot)
            if not getattr(mon, "fainted", False):
                survivors.append(slot)
        if not entered:
            entered = list(selected)
        return {
            "selectedSlots": list(selected),
            "enteredSlots": entered,
            "survivorSlots": survivors,
        }

    return {
        "ours": side_state(p1_team, our_selected, active_roster=our_selected),
        "opponent": side_state(
            p2_team, opponent_selected, active_roster=opponent_selected
        ),
    }


def build_turns_from_battle_summary(
    *,
    turn_count: int,
    our_actions_turn1: list[dict[str, Any]],
    opponent_actions_turn1: list[dict[str, Any]],
    trace: FullBattleTrace | None = None,
) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    trace_events_by_turn: dict[int, list[dict[str, Any]]] = {}
    if trace is not None:
        for event in trace.events:
            turn_no = int(event.get("turn") or 0)
            if turn_no >= 1:
                trace_events_by_turn.setdefault(turn_no, []).append(event)
    for turn_index in range(1, turn_count + 1):
        turns.append(
            {
                "turn": turn_index,
                "ourActions": our_actions_turn1 if turn_index == 1 else [],
                "opponentActions": opponent_actions_turn1 if turn_index == 1 else [],
                "events": trace_events_by_turn.get(turn_index, []),
            }
        )
    return turns


def _fixture_survivors(
    outcome: Outcome,
    our_lead: tuple[int, int],
    opponent_lead: tuple[int, int],
    opponent_selected: tuple[int, int, int, int],
    turn_count: int,
    digest_byte: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    lead_a, lead_b = our_lead
    opp_a, opp_b = opponent_lead
    if outcome == "draw":
        return (lead_a,), (opp_a,)
    if outcome == "win":
        if turn_count >= 2 and digest_byte % 2 == 0:
            return (lead_a, lead_b), ()
        return (lead_a,), (opp_b,)
    if turn_count >= 2:
        return (), (opp_a, opponent_selected[2])
    return (lead_b,), (opp_a, opp_b)


def _entered_slots(
    selected: tuple[int, int, int, int],
    survivors: tuple[int, ...],
    digest_byte: int,
    *,
    side: str,
) -> tuple[int, ...]:
    entered = set(survivors)
    for slot in selected:
        if slot in survivors:
            continue
        if digest_byte % 3 == 0 and slot == selected[2]:
            continue
        entered.add(slot)
    if not entered:
        entered.add(selected[0])
    return tuple(sorted(entered))
