"""Deterministic turn-1 aggregation for phase B (conditional on opponent lead)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from typing import Any

from pokecoach_python.engine.contracts import TurnOneRecord
from pokecoach_python.schemas.analysis_result import Turn1Section
from pokecoach_python.workflow.aggregation.leads import canonical_lead


def canonical_back_pair(slots: tuple[int, int]) -> tuple[int, int]:
    a, b = slots
    if a == b:
        raise ValueError("back slots must be distinct")
    if a < 0 or a > 5 or b < 0 or b > 5:
        raise ValueError("back slot out of range")
    return (a, b) if a < b else (b, a)


def _sort_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        actions,
        key=lambda action: (
            str(action.get("actor", {}).get("side", "")),
            int(action.get("actor", {}).get("slot", -1)),
        ),
    )


def canonical_joint_key(actions: list[dict[str, Any]]) -> str:
    ordered = _sort_actions(actions)
    return json.dumps(ordered, sort_keys=True, separators=(",", ":"))


def _frequency_rows(
    counter: Counter[Any],
    sample_size: int,
) -> list[dict[str, Any]]:
    ordered = sorted(
        counter.items(),
        key=lambda item: (-item[1], item[0] if isinstance(item[0], (int, tuple)) else str(item[0])),
    )
    rows: list[dict[str, Any]] = []
    for key, count in ordered:
        if isinstance(key, str):
            value = json.loads(key)
        else:
            value = key
        rows.append({"value": value, "count": count, "sampleSize": sample_size})
    return rows


def aggregate_turn_one(
    records: Sequence[TurnOneRecord],
    lead_slots: tuple[int, int],
) -> Turn1Section:
    expected = canonical_lead(lead_slots)
    joint_counter: Counter[str] = Counter()
    back_counter: Counter[tuple[int, int]] = Counter()
    slot_counter: Counter[int] = Counter()
    notes: list[str] = []
    seen_notes: set[str] = set()

    for record in records:
        if canonical_lead(record.opponent_lead_slots) != expected:
            raise ValueError("turn-one record lead mismatch")
        payload = record.payload
        actions_raw = payload.get("opponentActions")
        if actions_raw is None:
            actions_raw = payload.get("actions")
        back_raw = payload.get("backPair")
        if not isinstance(actions_raw, list) or len(actions_raw) != 2:
            raise ValueError("turn-one payload requires two opponent actions")
        if not isinstance(back_raw, list) or len(back_raw) != 2:
            raise ValueError("turn-one payload requires backPair")
        actions = [a for a in actions_raw if isinstance(a, dict)]
        if len(actions) != 2:
            raise ValueError("invalid action objects")
        joint_counter[canonical_joint_key(actions)] += 1
        back = canonical_back_pair((int(back_raw[0]), int(back_raw[1])))
        back_counter[back] += 1
        slot_counter[back[0]] += 1
        slot_counter[back[1]] += 1
        for note in payload.get("endStateNotes") or []:
            if isinstance(note, str) and note not in seen_notes:
                seen_notes.add(note)
                notes.append(note)

    sample_size = sum(joint_counter.values())
    if sample_size != len(records):
        raise ValueError("joint action sample mismatch")

    joint_rows = _frequency_rows(joint_counter, sample_size)
    for row in joint_rows:
        row["value"] = _sort_actions(row["value"])

    back_rows = _frequency_rows(back_counter, sample_size)
    for row in back_rows:
        pair = row["value"]
        row["value"] = list(canonical_back_pair((pair[0], pair[1])))

    slot_rows = _frequency_rows(slot_counter, sample_size)
    for row in slot_rows:
        row["value"] = int(row["value"])
        row["marginalBasis"] = "per-slot-in-back-pair"

    return Turn1Section(
        sampleSize=sample_size,
        jointActions=joint_rows,
        backPairs=back_rows,
        backSlotMarginals=slot_rows,
        endStateNotes=notes,
    )
