"""Unit tests for global refinement sampling plan."""

from __future__ import annotations

import pytest

from pokecoach_python.schemas.analysis_result import (
    LeadPickSection,
    LeadSelection,
    OpeningStudyEntry,
    OpeningsSection,
    OpponentLeadEntry,
    OpponentLeadsSection,
    SimulationResultV2,
)
from pokecoach_python.workflow.refinement_sampling import (
    build_refinement_plan,
    validate_refinement_sampling_inputs,
    _pick_weighted,
    _weighted_scenarios,
)


def _selection() -> LeadSelection:
    return LeadSelection(ourFourSlots=(0, 1, 4, 5), ourLeadSlots=(0, 1))


def _openings_two_leads() -> OpeningsSection:
    sel = _selection()
    return OpeningsSection(
        selection=sel,
        recommendationRule="model-frequency-v1",
        samplingPolicy="conditional-back-v1",
        byOpponentLead=[
            OpeningStudyEntry(
                opponentLeadId="lead-L1",
                opponentLeadSlots=(0, 1),
                sampleSize=4,
                opponentActions=[],
                ourActions=[],
                recommendation={"value": [], "count": 1, "sampleSize": 4},
                backPairs=[
                    {"value": [2, 3], "count": 3, "sampleSize": 4},
                    {"value": [4, 5], "count": 1, "sampleSize": 4},
                ],
                backSlotMarginals=[],
                endStateNotes=[],
            ),
            OpeningStudyEntry(
                opponentLeadId="lead-L2",
                opponentLeadSlots=(2, 3),
                sampleSize=5,
                opponentActions=[],
                ourActions=[],
                recommendation={"value": [], "count": 1, "sampleSize": 5},
                backPairs=[{"value": [0, 4], "count": 5, "sampleSize": 5}],
                backSlotMarginals=[],
                endStateNotes=[],
            ),
        ],
    )


def _result_60_40() -> SimulationResultV2:
    return SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "C", "B"],
        opponentLeads=OpponentLeadsSection(
            sampleSize=100,
            leads=[
                OpponentLeadEntry(id="lead-L1", slots=(0, 1), count=60),
                OpponentLeadEntry(id="lead-L2", slots=(2, 3), count=40),
            ],
        ),
        leadPick=LeadPickSection(
            selection=_selection(),
            comparisons=[],
            selectionRuleVersion="selection-v1",
            limitations=[],
        ),
        openings=_openings_two_leads(),
        refinement=None,
        gameplan=None,
        winCondition=None,
    )


def test_weights_match_60_40_example():
    weighted = _weighted_scenarios(_result_60_40())
    by_key = {(s.opponent_lead_id, s.opponent_back_pair): w for s, w in weighted}
    assert by_key[("lead-L1", (2, 3))] == 60 * 3
    assert by_key[("lead-L1", (4, 5))] == 60 * 1
    assert by_key[("lead-L2", (0, 4))] == 40 * 5
    total = sum(by_key.values())
    assert by_key[("lead-L1", (2, 3))] / total == pytest.approx(180 / 440)
    assert by_key[("lead-L1", (4, 5))] / total == pytest.approx(60 / 440)
    assert by_key[("lead-L2", (0, 4))] / total == pytest.approx(200 / 440)


def test_low_frequency_lead_remains_eligible():
    weighted = _weighted_scenarios(_result_60_40())
    lead_ids = {s.opponent_lead_id for s, _ in weighted}
    assert "lead-L2" in lead_ids


def test_plan_is_deterministic_for_seed():
    result = _result_60_40()
    a = build_refinement_plan(result, seed=99, budget=5)
    b = build_refinement_plan(result, seed=99, budget=5)
    assert a.scenarios == b.scenarios


def test_plan_prefix_stable_when_budget_grows():
    result = _result_60_40()
    short = build_refinement_plan(result, seed=7, budget=2)
    long = build_refinement_plan(result, seed=7, budget=5)
    assert short.scenarios == long.scenarios[:2]


def test_permutation_of_json_lists_does_not_change_plan():
    result = _result_60_40()
    base = build_refinement_plan(result, seed=11, budget=3)
    openings = result.openings
    assert openings is not None
    shuffled = openings.model_copy(
        update={"byOpponentLead": list(reversed(openings.byOpponentLead))}
    )
    leads = result.opponentLeads
    assert leads is not None
    shuffled_leads = leads.model_copy(update={"leads": list(reversed(leads.leads))})
    permuted = result.model_copy(update={"openings": shuffled, "opponentLeads": shuffled_leads})
    other = build_refinement_plan(permuted, seed=11, budget=3)
    assert base.scenarios == other.scenarios


def test_single_scenario_support_allows_repeats():
    result = _result_60_40()
    openings = result.openings
    assert openings is not None
    only_l1 = openings.model_copy(update={"byOpponentLead": [openings.byOpponentLead[0]]})
    only_a = result.opponentLeads
    assert only_a is not None
    one_lead = only_a.model_copy(update={"leads": [only_a.leads[0]], "sampleSize": 60})
    narrowed = result.model_copy(update={"openings": only_l1, "opponentLeads": one_lead})
    plan = build_refinement_plan(narrowed, seed=1, budget=4)
    assert len(plan.scenarios) == 4


def test_missing_backs_raises():
    result = _result_60_40()
    openings = result.openings
    assert openings is not None
    bad = openings.model_copy(
        update={
            "byOpponentLead": [
                OpeningStudyEntry(
                    opponentLeadId="lead-L2",
                    opponentLeadSlots=(2, 3),
                    sampleSize=0,
                    opponentActions=[],
                    ourActions=[],
                    recommendation={"value": [], "count": 0, "sampleSize": 0},
                    backPairs=[],
                    backSlotMarginals=[],
                    endStateNotes=[],
                ),
                openings.byOpponentLead[0],
            ]
        }
    )
    broken = result.model_copy(update={"openings": bad})
    with pytest.raises(ValueError):
        validate_refinement_sampling_inputs(broken)


def test_pick_weighted_covers_all_intervals():
    weighted = _weighted_scenarios(_result_60_40())
    total = sum(w for _, w in weighted)
    import random

    for roll in range(total):
        picked = _pick_weighted(random.Random(roll), weighted)
        assert picked in [s for s, _ in weighted]
