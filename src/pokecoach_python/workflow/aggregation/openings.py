"""Conditional turn-1 openings aggregation for phase B."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from pokecoach_python.engine.contracts import TurnOneRecord
from pokecoach_python.schemas.analysis_result import (
    LeadSelection,
    OpeningStudyEntry,
    OpeningsSection,
    OpponentLeadEntry,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.turn_one import (
    canonical_back_pair,
    canonical_joint_key,
    _frequency_rows,
    _sort_actions,
)
from pokecoach_python.workflow.aggregation.action_resolutions import attach_resolutions_to_frequency_rows


def _actions_from_payload(payload: dict[str, Any], *, side: str) -> list[dict[str, Any]]:
    if side == "opponent":
        raw = payload.get("opponentActions")
        if raw is None:
            raw = payload.get("actions")
    else:
        raw = payload.get("ourActions")
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError(f"turn-one payload requires two {side} actions")
    actions = [a for a in raw if isinstance(a, dict)]
    if len(actions) != 2:
        raise ValueError(f"invalid {side} action objects")
    return actions


def aggregate_opening_study(
    records: Sequence[TurnOneRecord],
    *,
    opponent_lead: OpponentLeadEntry,
) -> OpeningStudyEntry:
    lead_slots = canonical_lead(opponent_lead.slots)
    opp_counter: Counter[str] = Counter()
    our_counter: Counter[str] = Counter()
    back_counter: Counter[tuple[int, int]] = Counter()
    slot_counter: Counter[int] = Counter()
    notes: list[str] = []
    seen_notes: set[str] = set()

    for record in records:
        if canonical_lead(record.opponent_lead_slots) != lead_slots:
            raise ValueError("turn-one record lead mismatch")
        payload = record.payload
        opp_actions = _actions_from_payload(payload, side="opponent")
        our_actions = _actions_from_payload(payload, side="ours")
        back_raw = payload.get("backPair")
        if not isinstance(back_raw, list) or len(back_raw) != 2:
            raise ValueError("turn-one payload requires backPair")
        opp_counter[canonical_joint_key(opp_actions)] += 1
        our_counter[canonical_joint_key(our_actions)] += 1
        back = canonical_back_pair((int(back_raw[0]), int(back_raw[1])))
        back_counter[back] += 1
        slot_counter[back[0]] += 1
        slot_counter[back[1]] += 1
        for note in payload.get("endStateNotes") or []:
            if isinstance(note, str) and note not in seen_notes:
                seen_notes.add(note)
                notes.append(note)

    sample_size = len(records)
    if sample_size == 0:
        raise ValueError("opening study requires at least one record")
    if sum(opp_counter.values()) != sample_size or sum(our_counter.values()) != sample_size:
        raise ValueError("action sample mismatch")

    opp_rows = _frequency_rows(opp_counter, sample_size)
    for row in opp_rows:
        row["value"] = _sort_actions(row["value"])
    opp_rows = attach_resolutions_to_frequency_rows(
        opp_rows,
        records=list(records),
        side="opponent",
        joint_key_fn=canonical_joint_key,
        actions_from_payload=_actions_from_payload,
    )

    our_rows = _frequency_rows(our_counter, sample_size)
    for row in our_rows:
        row["value"] = _sort_actions(row["value"])
    our_rows = attach_resolutions_to_frequency_rows(
        our_rows,
        records=list(records),
        side="ours",
        joint_key_fn=canonical_joint_key,
        actions_from_payload=_actions_from_payload,
    )

    if not our_rows:
        raise ValueError("ourActions distribution empty")
    recommendation = dict(our_rows[0])

    back_rows = _frequency_rows(back_counter, sample_size)
    for row in back_rows:
        pair = row["value"]
        row["value"] = list(canonical_back_pair((pair[0], pair[1])))

    slot_rows = _frequency_rows(slot_counter, sample_size)
    for row in slot_rows:
        row["value"] = int(row["value"])
        row["marginalBasis"] = "per-slot-in-back-pair"

    return OpeningStudyEntry(
        opponentLeadId=opponent_lead.id,
        opponentLeadSlots=lead_slots,
        sampleSize=sample_size,
        opponentActions=opp_rows,
        ourActions=our_rows,
        recommendation=recommendation,
        backPairs=back_rows,
        backSlotMarginals=slot_rows,
        endStateNotes=notes,
    )


def aggregate_openings(
    by_lead: dict[str, Sequence[TurnOneRecord]],
    section_leads: Sequence[OpponentLeadEntry],
    selection: LeadSelection,
    *,
    sampling_policy: str,
) -> OpeningsSection:
    studies: list[OpeningStudyEntry] = []
    for entry in section_leads:
        records = by_lead.get(entry.id)
        if not records:
            raise RuntimeError(f"missing opening samples for lead {entry.id}")
        studies.append(aggregate_opening_study(records, opponent_lead=entry))
    return OpeningsSection(
        selection=selection,
        recommendationRule="model-frequency-v1",
        samplingPolicy=sampling_policy,
        byOpponentLead=studies,
    )
