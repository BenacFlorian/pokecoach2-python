"""Normalize and serialize full battle records for phase C/D storage."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.workflow.aggregation.leads import canonical_lead

BATTLE_FORMAT_VERSION = 1


def canonical_four(slots: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    four = tuple(sorted(slots))
    if len(set(four)) != 4 or any(s < 0 or s > 5 for s in four):
        raise ValueError("ourFourSlots must be four distinct indices 0-5")
    return four  # type: ignore[return-value]


def four_slots_leads_first(
    four: tuple[int, int, int, int],
    lead: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Presentation order for leadPick: lead pair first, then back pair."""
    canonical_four(four)
    lead_a, lead_b = lead
    if lead_a not in four or lead_b not in four or lead_a == lead_b:
        raise ValueError("ourLeadSlots must be two distinct slots from ourFourSlots")
    backs = tuple(sorted(s for s in four if s not in {lead_a, lead_b}))
    return (lead_a, lead_b, backs[0], backs[1])


def battle_payload_dict(record: BattleRecord) -> dict[str, Any]:
    participants = dict(record.participants)
    preview = {
        "opponentLeadSlots": list(record.preview.opponent_lead_slots),
        "ourLeadSlots": (
            list(record.preview.our_lead_slots)
            if record.preview.our_lead_slots is not None
            else None
        ),
        "meta": dict(record.preview.meta),
    }
    return {
        "formatVersion": BATTLE_FORMAT_VERSION,
        "preview": preview,
        "turns": [dict(t) for t in record.turns],
        "outcome": record.outcome,
        "participants": participants,
        "meta": dict(record.meta),
    }


def battle_payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def battle_record_from_payload(payload: dict[str, Any]) -> BattleRecord:
    preview_raw = payload["preview"]
    opp = preview_raw["opponentLeadSlots"]
    our_lead_raw = preview_raw.get("ourLeadSlots")
    preview = PreviewRecord(
        opponent_lead_slots=(int(opp[0]), int(opp[1])),
        our_lead_slots=(
            (int(our_lead_raw[0]), int(our_lead_raw[1]))
            if our_lead_raw is not None
            else None
        ),
        meta=dict(preview_raw.get("meta") or {}),
    )
    turns = tuple(dict(t) for t in payload.get("turns") or [])
    outcome = payload["outcome"]
    if outcome not in ("win", "loss", "draw", "technical"):
        raise ValueError("invalid battle outcome in payload")
    return BattleRecord(
        preview=preview,
        turns=turns,
        outcome=outcome,  # type: ignore[arg-type]
        participants=dict(payload.get("participants") or {}),
        meta=dict(payload.get("meta") or {}),
    )


def validate_terminal_battle(
    record: BattleRecord,
    *,
    expected_opponent_lead: tuple[int, int],
) -> None:
    if record.outcome == "technical":
        raise ValueError("technical outcome is not a valid terminal battle")
    if record.outcome not in ("win", "loss", "draw"):
        raise ValueError("battle outcome must be win, loss, or draw")
    if canonical_lead(record.preview.opponent_lead_slots) != canonical_lead(
        expected_opponent_lead
    ):
        raise ValueError("opponent lead mismatch")
    four_raw = record.participants.get("ourFourSlots")
    lead_raw = record.participants.get("ourLeadSlots")
    if not isinstance(four_raw, list) or len(four_raw) != 4:
        raise ValueError("participants require ourFourSlots")
    if not isinstance(lead_raw, list) or len(lead_raw) != 2:
        raise ValueError("participants require ourLeadSlots")
    four = tuple(int(s) for s in four_raw)
    lead = (int(lead_raw[0]), int(lead_raw[1]))
    canonical_four(four)
    if lead[0] not in four or lead[1] not in four or lead[0] == lead[1]:
        raise ValueError("ourLeadSlots must lie in ourFourSlots")
    if not record.turns:
        raise ValueError("battle requires at least one turn")


def sample_key_for_lead(lead_slots: tuple[int, int], valid_index: int) -> str:
    c = canonical_lead(lead_slots)
    return f"{c[0]}-{c[1]}:{valid_index:04d}"
