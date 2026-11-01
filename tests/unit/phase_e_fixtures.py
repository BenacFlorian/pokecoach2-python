from __future__ import annotations

from typing import Iterable

from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.llm.battle_sources import StoredDBattle


def make_snapshots() -> tuple[dict, dict]:
    our = {
        "pokemon": [
            {"species": "Flutter Mane", "moves": ["Moonblast", "Protect"]},
            {"species": "Incineroar", "moves": ["Fake Out", "Parting Shot"]},
            {"species": "Rillaboom", "moves": ["Grassy Glide", "Fake Out"]},
            {"species": "Urshifu", "moves": ["Surging Strikes"]},
            {"species": "Miraidon", "moves": ["Electro Drift"]},
            {"species": "Amoonguss", "moves": ["Spore", "Rage Powder"]},
        ]
    }
    opponent = {
        "pokemon": [
            {"species": "Calyrex-Shadow", "moves": ["Astral Barrage"]},
            {"species": "Urshifu-Rapid-Strike", "moves": ["Surging Strikes"]},
            {"species": "Raging Bolt", "moves": ["Thunderclap"]},
            {"species": "Incineroar", "moves": ["Fake Out"]},
            {"species": "Amoonguss", "moves": ["Spore"]},
            {"species": "Farigiraf", "moves": ["Helping Hand"]},
        ]
    }
    return our, opponent


def make_stored_battle(
    battle_id: str,
    sample_key: str,
    *,
    outcome: str,
    our_survivors: tuple[int, ...],
    opponent_survivors: tuple[int, ...],
    opponent_lead: tuple[int, int] = (0, 1),
    opponent_selected: tuple[int, int, int, int] = (0, 1, 2, 3),
    our_four: tuple[int, int, int, int] = (0, 1, 4, 5),
    our_lead: tuple[int, int] = (0, 1),
    damage_events: Iterable[dict] = (),
    turn_count: int = 2,
    entered_ours: tuple[int, ...] | None = None,
    entered_opponent: tuple[int, ...] | None = None,
    declared_turn_count: int | None = None,
) -> StoredDBattle:
    turns_list: list[dict] = []
    for index in range(1, turn_count + 1):
        events = [
            dict(event, turn=event.get("turn", index))
            for event in damage_events
            if int(event.get("turn", 1)) == index
        ]
        if index > 1 and not events:
            events.append({"kind": "state", "turn": index, "note": "fixture-synthetic-turn"})
        turns_list.append({"turn": index, "ourActions": [], "events": events})
    turns = tuple(turns_list)
    record = BattleRecord(
        preview=PreviewRecord(
            opponent_lead_slots=opponent_lead,
            our_lead_slots=our_lead,
            meta={"engine": "vgc-bench"},
        ),
        turns=turns,
        outcome=outcome,  # type: ignore[arg-type]
        participants={
            "ourFourSlots": list(our_four),
            "ourLeadSlots": list(our_lead),
            "opponentSelectedSlots": list(opponent_selected),
        },
        meta={
            "engine": "vgc-bench",
            "terminalEvidence": {"kind": "simulator", "turnCount": declared_turn_count or turn_count},
            "terminalState": {
                "ours": {
                    "selectedSlots": list(our_four),
                    "enteredSlots": list(entered_ours or our_four),
                    "survivorSlots": list(our_survivors),
                },
                "opponent": {
                    "selectedSlots": list(opponent_selected),
                    "enteredSlots": list(entered_opponent or opponent_selected),
                    "survivorSlots": list(opponent_survivors),
                },
            },
            "captureQuality": {"exactHp": True, "roundedHp": False},
        },
    )
    return StoredDBattle(
        id=battle_id,
        sample_key=sample_key,
        sha256=f"sha-{battle_id}",
        record=record,
    )


def damage_event(
    *,
    turn: int,
    source_side: str | None,
    source_slot: int | None,
    target_side: str,
    target_slot: int,
    hp_percent_loss: float,
    direct: bool = True,
    attributed: bool = True,
    caused_ko: bool = False,
    target_substitute: bool = False,
) -> dict:
    event = {
        "kind": "damage",
        "turn": turn,
        "target": {"side": target_side, "slot": target_slot},
        "hpPercentLoss": hp_percent_loss,
        "direct": direct,
        "attributed": attributed,
        "causedKo": caused_ko,
        "targetSubstitute": target_substitute,
    }
    if source_side is not None and source_slot is not None:
        event["source"] = {"side": source_side, "slot": source_slot}
    return event
