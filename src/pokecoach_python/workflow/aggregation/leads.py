"""Deterministic lead aggregation for phase A."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pokecoach_python.engine.contracts import PreviewRecord
from pokecoach_python.schemas.analysis_result import OpponentLeadEntry, OpponentLeadsSection


def canonical_lead(slots: tuple[int, int]) -> tuple[int, int]:
    a, b = slots
    if a == b:
        raise ValueError("lead slots must be distinct")
    if a < 0 or a > 5 or b < 0 or b > 5:
        raise ValueError("lead slots out of range")
    return (a, b) if a < b else (b, a)


def lead_id(slots: tuple[int, int]) -> str:
    c = canonical_lead(slots)
    return f"lead-{c[0]}-{c[1]}"


def aggregate_leads(records: Sequence[PreviewRecord]) -> OpponentLeadsSection:
    counter: Counter[tuple[int, int]] = Counter()
    for record in records:
        key = canonical_lead(record.opponent_lead_slots)
        counter[key] += 1
    sample_size = sum(counter.values())
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if len(ordered) > 15:
        raise ValueError("at most fifteen lead pairs")
    leads: list[OpponentLeadEntry] = []
    for slots, count in ordered:
        leads.append(
            OpponentLeadEntry(
                id=lead_id(slots),
                slots=slots,
                count=count,
                turn1=None,
            )
        )
    return OpponentLeadsSection(sampleSize=sample_size, leads=leads)
