"""Validation and normalization helpers for Phase E battle sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.graphs.matchup_gameplan.models import (
    BattleCaptureQuality,
    BattleDamageEvent,
    NormalizedDBattle,
    PokemonRef,
)
from pokecoach_python.workflow.battle_records import canonical_four, validate_terminal_battle
from pokecoach_python.workflow.aggregation.leads import canonical_lead


@dataclass(frozen=True)
class StoredDBattle:
    id: str
    sample_key: str
    sha256: str
    record: BattleRecord


def validate_d_synthesis_source(record: BattleRecord) -> None:
    validate_terminal_battle(
        record,
        expected_opponent_lead=record.preview.opponent_lead_slots,
    )
    meta = record.meta or {}
    terminal_evidence = meta.get("terminalEvidence")
    if not isinstance(terminal_evidence, dict):
        raise ValueError("synthesis source requires terminalEvidence")
    turn_count = terminal_evidence.get("turnCount")
    if isinstance(turn_count, int) and turn_count > len(record.turns):
        raise ValueError("synthesis source trace is incomplete for declared turnCount")
    terminal_state = meta.get("terminalState")
    if not isinstance(terminal_state, dict):
        raise ValueError("synthesis source requires terminalState")
    for side in ("ours", "opponent"):
        side_state = terminal_state.get(side)
        if not isinstance(side_state, dict):
            raise ValueError(f"synthesis source terminalState.{side} missing")
        for field in ("selectedSlots", "enteredSlots", "survivorSlots"):
            if not isinstance(side_state.get(field), list):
                raise ValueError(f"synthesis source terminalState.{side}.{field} missing")


def normalize_stored_d_battle(stored: StoredDBattle) -> NormalizedDBattle:
    record = stored.record
    validate_d_synthesis_source(record)
    meta = record.meta or {}
    terminal_state = meta["terminalState"]
    terminal_evidence = meta["terminalEvidence"]
    our_four = canonical_four(tuple(int(slot) for slot in record.participants["ourFourSlots"]))
    our_lead = canonical_lead(tuple(int(slot) for slot in record.participants["ourLeadSlots"]))
    opponent_selected = _slots(
        terminal_state["opponent"]["selectedSlots"],
        count=4,
        label="terminalState.opponent.selectedSlots",
    )
    entered_slots = {
        "ours": _slots(
            terminal_state["ours"]["enteredSlots"],
            count=None,
            label="terminalState.ours.enteredSlots",
        ),
        "opponent": _slots(
            terminal_state["opponent"]["enteredSlots"],
            count=None,
            label="terminalState.opponent.enteredSlots",
        ),
    }
    survivor_slots = {
        "ours": _slots(
            terminal_state["ours"]["survivorSlots"],
            count=None,
            label="terminalState.ours.survivorSlots",
        ),
        "opponent": _slots(
            terminal_state["opponent"]["survivorSlots"],
            count=None,
            label="terminalState.opponent.survivorSlots",
        ),
    }
    damage_events = _extract_damage_events(record)
    capture_quality = BattleCaptureQuality(
        exactHp=bool((meta.get("captureQuality") or {}).get("exactHp", False)),
        roundedHp=bool((meta.get("captureQuality") or {}).get("roundedHp", False)),
        unattributedDamageEvents=sum(1 for event in damage_events if not event.attributed),
    )
    return NormalizedDBattle(
        battleId=stored.id,
        sampleKey=stored.sample_key,
        sha256=stored.sha256,
        outcome=record.outcome,
        opponentLeadSlots=canonical_lead(record.preview.opponent_lead_slots),
        ourFourSlots=our_four,
        ourLeadSlots=our_lead,
        opponentSelectedSlots=opponent_selected,
        enteredSlots=entered_slots,
        survivorSlots=survivor_slots,
        turnCount=int(terminal_evidence.get("turnCount") or len(record.turns)),
        turns=[dict(turn) for turn in record.turns],
        damageEvents=damage_events,
        captureQuality=capture_quality,
    )


def _slots(raw: Any, *, count: int | None, label: str) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be a list")
    values = tuple(int(slot) for slot in raw)
    if count is not None and len(values) != count:
        raise ValueError(f"{label} must contain {count} slots")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")
    if any(slot < 0 or slot > 5 for slot in values):
        raise ValueError(f"{label} must only contain slots 0-5")
    return values


def _extract_damage_events(record: BattleRecord) -> list[BattleDamageEvent]:
    events: list[BattleDamageEvent] = []
    meta_events = record.meta.get("damageEvents") if isinstance(record.meta, dict) else None
    if isinstance(meta_events, list):
        for raw in meta_events:
            events.append(_normalize_damage_event(raw, turn_hint=None))
    for turn in record.turns:
        turn_number = int(turn.get("turn") or 0)
        for raw in turn.get("damageEvents") or []:
            events.append(_normalize_damage_event(raw, turn_hint=turn_number))
        for raw in turn.get("events") or []:
            if isinstance(raw, dict) and raw.get("kind") == "damage":
                events.append(_normalize_damage_event(raw, turn_hint=turn_number))
    return events


def _normalize_damage_event(raw: Any, *, turn_hint: int | None) -> BattleDamageEvent:
    if not isinstance(raw, dict):
        raise ValueError("damage event must be an object")
    source_raw = raw.get("source")
    target_raw = raw.get("target")
    if not isinstance(target_raw, dict):
        raise ValueError("damage event target missing")
    source = _pokemon_ref(source_raw) if isinstance(source_raw, dict) else None
    target = _pokemon_ref(target_raw)
    hp_percent_loss = raw.get("hpPercentLoss")
    if hp_percent_loss is None:
        damage = raw.get("hpDamage")
        max_hp = raw.get("targetMaxHp")
        if isinstance(damage, (int, float)) and isinstance(max_hp, (int, float)) and max_hp > 0:
            hp_percent_loss = (float(damage) / float(max_hp)) * 100.0
        else:
            raise ValueError("damage event requires hpPercentLoss or hpDamage/targetMaxHp")
    turn = int(raw.get("turn") or turn_hint or 0)
    if turn < 1:
        raise ValueError("damage event turn must be >= 1")
    return BattleDamageEvent(
        turn=turn,
        source=source,
        target=target,
        direct=bool(raw.get("direct", True)),
        attributed=bool(raw.get("attributed", source is not None)),
        causedKo=bool(raw.get("causedKo", False)),
        targetSubstitute=bool(raw.get("targetSubstitute", False)),
        hpPercentLoss=float(hp_percent_loss),
        cause=str(raw.get("cause")) if raw.get("cause") is not None else None,
    )


def _pokemon_ref(raw: dict[str, Any]) -> PokemonRef:
    return PokemonRef(
        side=str(raw["side"]),
        slot=int(raw["slot"]),
    )
