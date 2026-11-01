"""Global refinement (phase D) validation and aggregation."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.schemas.analysis_result import (
    LeadSelection,
    RefinementScenarioCount,
    RefinementSection,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.turn_one import canonical_joint_key
from pokecoach_python.workflow.battle_records import canonical_four
from pokecoach_python.workflow.refinement_sampling import OpponentScenario, RefinementSamplingPlan


def validate_refinement_battle(
    record: BattleRecord,
    *,
    our_selection: LeadSelection,
    scenario: OpponentScenario,
) -> None:
    if record.outcome == "technical":
        raise ValueError("technical outcome is not a valid refinement battle")
    if record.outcome not in ("win", "loss", "draw"):
        raise ValueError("battle outcome must be win, loss, or draw")
    if canonical_lead(record.preview.opponent_lead_slots) != canonical_lead(
        scenario.opponent_lead_slots
    ):
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
    four = tuple(int(s) for s in four_raw)
    lead = (int(lead_raw[0]), int(lead_raw[1]))
    back = canonical_lead((int(back_raw[0]), int(back_raw[1])))
    expected_four = our_selection.ourFourSlots
    if canonical_four(four) != canonical_four(expected_four):
        raise ValueError("our selection mismatch in refinement battle")
    if lead != our_selection.ourLeadSlots:
        raise ValueError("our lead slots mismatch in refinement battle")
    if back != scenario.opponent_back_pair:
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


def _scenario_key(scenario: OpponentScenario) -> tuple[str, tuple[int, int], tuple[int, int]]:
    return (
        scenario.opponent_lead_id,
        scenario.opponent_lead_slots,
        scenario.opponent_back_pair,
    )


def aggregate_refinement(
    battles: Sequence[BattleRecord],
    *,
    selection: LeadSelection,
    plan: RefinementSamplingPlan,
    battle_ids: Sequence[str],
) -> RefinementSection:
    if len(battles) != len(plan.scenarios):
        raise ValueError("battle count must match planned scenarios")
    if len(battle_ids) != len(battles):
        raise ValueError("battleIds length mismatch")

    wins = losses = draws = 0
    scenario_counter: Counter[tuple[str, tuple[int, int], tuple[int, int]]] = Counter()

    for index, battle in enumerate(battles):
        scenario = plan.scenarios[index]
        validate_refinement_battle(
            battle,
            our_selection=selection,
            scenario=scenario,
        )
        scenario_counter[_scenario_key(scenario)] += 1
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

    first_turn_sample = sum(joint_counter.values())
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
                "sampleSize": first_turn_sample,
            }
        )

    scenario_rows: list[RefinementScenarioCount] = []
    for (lead_id, lead_slots, back_pair), count in sorted(
        scenario_counter.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        scenario_rows.append(
            RefinementScenarioCount(
                opponentLeadId=lead_id,
                opponentLeadSlots=lead_slots,
                opponentBackPair=back_pair,
                count=count,
            )
        )

    limitations = [
        (
            "Évaluation globale (phase D) : combats complets avec notre sélection C, "
            "scénarios adverses tirés selon les fréquences observées en A (lead) "
            "et B (back conditionnel au lead)."
        ),
        "Distribution empirique du modèle pour ce run — pas une preuve d'optimalité du bring.",
    ]
    if sample_size < 10:
        limitations.append("Faible échantillon : ne pas extrapoler au-delà de ces parties.")

    return RefinementSection(
        configuration=selection,
        samplingPolicy="weighted-ab",
        samplingScope="all-observed-leads",
        sampleSize=sample_size,
        outcomes={"wins": wins, "losses": losses, "draws": draws},
        scenarioCounts=scenario_rows,
        firstTurnSampleSize=first_turn_sample,
        firstTurns=first_turns,
        battleIds=list(battle_ids),
        limitations=limitations,
    )
