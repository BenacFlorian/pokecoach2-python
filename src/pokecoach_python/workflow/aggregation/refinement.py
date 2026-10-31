"""Deterministic refinement (phase D) configuration and aggregation."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.schemas.analysis_result import (
    LeadSelection,
    OpponentLeadEntry,
    RefinementSection,
    SimulationResultV2,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.turn_one import canonical_joint_key
from pokecoach_python.workflow.battle_records import canonical_four, four_slots_leads_first
from pokecoach_python.workflow.budgets import studied_opponent_lead_count


@dataclass(frozen=True)
class FixedBattleConfiguration:
    our_four: tuple[int, int, int, int]
    our_lead: tuple[int, int]
    opponent_lead: tuple[int, int]
    opponent_lead_id: str
    opponent_back: tuple[int, int]


def _top_back_pair(entry: OpponentLeadEntry) -> tuple[int, int]:
    if entry.turn1 is None or not entry.turn1.backPairs:
        raise ValueError(f"phase D requires turn1 back pairs for lead {entry.id}")
    lead = canonical_lead(entry.slots)
    candidates: list[tuple[tuple[int, int], int]] = []
    for row in entry.turn1.backPairs:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        count = row.get("count")
        if not isinstance(count, int) or not isinstance(value, list) or len(value) != 2:
            continue
        pair = canonical_lead((int(value[0]), int(value[1])))
        if pair[0] in lead or pair[1] in lead:
            continue
        candidates.append((pair, count))
    if not candidates:
        raise ValueError(f"no valid opponent back pair for lead {entry.id}")
    candidates.sort(key=lambda item: (-item[1], item[0]))
    return candidates[0][0]


def select_refinement_configuration(
    result: SimulationResultV2,
    *,
    studied_lead_count: int | None = None,
) -> FixedBattleConfiguration:
    if result.leadPick is None or result.opponentLeads is None:
        raise ValueError("phase D requires completed leadPick and opponentLeads")
    top_n = studied_lead_count or 3
    studied = result.opponentLeads.leads[: min(top_n, len(result.opponentLeads.leads))]
    if not studied:
        raise ValueError("no opponent leads available for refinement")
    target = studied[0]
    opponent_back = _top_back_pair(target)
    selection = result.leadPick.selection
    our_four = canonical_four(selection.ourFourSlots)
    our_lead = canonical_lead(selection.ourLeadSlots)
    return FixedBattleConfiguration(
        our_four=our_four,
        our_lead=our_lead,
        opponent_lead=canonical_lead(target.slots),
        opponent_lead_id=target.id,
        opponent_back=opponent_back,
    )


def validate_refinement_battle(
    record: BattleRecord,
    configuration: FixedBattleConfiguration,
) -> None:
    if record.outcome == "technical":
        raise ValueError("technical outcome is not a valid refinement battle")
    if record.outcome not in ("win", "loss", "draw"):
        raise ValueError("battle outcome must be win, loss, or draw")
    if canonical_lead(record.preview.opponent_lead_slots) != configuration.opponent_lead:
        raise ValueError("opponent lead mismatch in refinement battle")
    four_raw = record.participants.get("ourFourSlots")
    lead_raw = record.participants.get("ourLeadSlots")
    back_raw = record.participants.get("opponentBackPair")
    if not isinstance(four_raw, list) or len(four_raw) != 4:
        raise ValueError("participants require ourFourSlots")
    if not isinstance(lead_raw, list) or len(lead_raw) != 2:
        raise ValueError("participants require ourLeadSlots")
    if not isinstance(back_raw, list) or len(back_raw) != 2:
        raise ValueError("participants require opponentBackPair")
    four = canonical_four((int(four_raw[0]), int(four_raw[1]), int(four_raw[2]), int(four_raw[3])))
    lead = canonical_lead((int(lead_raw[0]), int(lead_raw[1])))
    back = canonical_lead((int(back_raw[0]), int(back_raw[1])))
    if four != configuration.our_four or lead != configuration.our_lead:
        raise ValueError("our selection mismatch in refinement battle")
    if back != configuration.opponent_back:
        raise ValueError("opponent back mismatch in refinement battle")
    if not record.turns:
        raise ValueError("battle requires at least one turn")


def _extract_our_turn1_actions(record: BattleRecord) -> list[dict[str, Any]]:
    if not record.turns:
        return []
    actions = record.turns[0].get("ourActions")
    if not isinstance(actions, list):
        return []
    return [a for a in actions if isinstance(a, dict)]


def aggregate_refinement(
    battles: Sequence[BattleRecord],
    configuration: FixedBattleConfiguration,
    *,
    battle_ids: Sequence[str],
) -> RefinementSection:
    wins = losses = draws = 0
    for battle in battles:
        validate_refinement_battle(battle, configuration)
        if battle.outcome == "win":
            wins += 1
        elif battle.outcome == "loss":
            losses += 1
        else:
            draws += 1

    sample_size = wins + losses + draws
    joint_counter: Counter[str] = Counter()
    for battle in battles:
        actions = _extract_our_turn1_actions(battle)
        if len(actions) != 2:
            continue
        joint_counter[canonical_joint_key(actions)] += 1

    first_turns: list[dict[str, Any]] = []
    for key, count in sorted(
        joint_counter.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        actions = json.loads(key)
        first_turns.append(
            {
                "value": actions,
                "count": count,
                "sampleSize": sample_size,
            }
        )

    display_four = four_slots_leads_first(configuration.our_four, configuration.our_lead)
    limitations = [
        (
            f"Configuration ciblée (phase D) : lead adverse {configuration.opponent_lead_id} "
            f"({configuration.opponent_lead[0]}-{configuration.opponent_lead[1]}), "
            f"back {configuration.opponent_back[0]}-{configuration.opponent_back[1]}."
        ),
        "Observations distinctes des statistiques globales de la phase C.",
    ]
    if sample_size < 10:
        limitations.append("Faible échantillon : ne pas extrapoler au-delà de ces parties.")

    return RefinementSection(
        configuration=LeadSelection(
            ourFourSlots=display_four,
            ourLeadSlots=configuration.our_lead,
        ),
        sampleSize=sample_size,
        outcomes={"wins": wins, "losses": losses, "draws": draws},
        firstTurns=first_turns,
        battleIds=list(battle_ids),
        limitations=limitations,
    )


def studied_lead_count_from_parameters(parameters: dict[str, Any]) -> int:
    return studied_opponent_lead_count(parameters)
