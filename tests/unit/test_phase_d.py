"""Unit tests for phase D global refinement."""

from __future__ import annotations

import json

from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.schemas.analysis_result import (
    LeadPickSection,
    LeadSelection,
    OpeningStudyEntry,
    OpeningsSection,
    OpponentLeadEntry,
    OpponentLeadsSection,
    SimulationResultV2,
)
from pokecoach_python.workflow.aggregation.refinement import (
    aggregate_refinement,
    validate_refinement_battle,
)
from pokecoach_python.workflow.refinement_sampling import (
    OpponentScenario,
    RefinementSamplingPlan,
    build_refinement_plan,
)


def _openings_for_leads() -> OpeningsSection:
    selection = LeadSelection(ourFourSlots=(0, 1, 4, 5), ourLeadSlots=(0, 1))
    return OpeningsSection(
        selection=selection,
        recommendationRule="model-frequency-v1",
        samplingPolicy="conditional-back-v1",
        byOpponentLead=[
            OpeningStudyEntry(
                opponentLeadId="lead-0-1",
                opponentLeadSlots=(0, 1),
                sampleSize=3,
                opponentActions=[],
                ourActions=[],
                recommendation={"value": [], "count": 1, "sampleSize": 3},
                backPairs=[
                    {"value": [2, 3], "count": 2, "sampleSize": 3},
                    {"value": [4, 5], "count": 1, "sampleSize": 3},
                ],
                backSlotMarginals=[],
                endStateNotes=[],
            ),
            OpeningStudyEntry(
                opponentLeadId="lead-2-3",
                opponentLeadSlots=(2, 3),
                sampleSize=3,
                opponentActions=[],
                ourActions=[],
                recommendation={"value": [], "count": 1, "sampleSize": 3},
                backPairs=[{"value": [0, 4], "count": 3, "sampleSize": 3}],
                backSlotMarginals=[],
                endStateNotes=[],
            ),
        ],
    )


def _result_with_back_pairs() -> SimulationResultV2:
    return SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "C", "B"],
        opponentLeads=OpponentLeadsSection(
            sampleSize=80,
            leads=[
                OpponentLeadEntry(id="lead-0-1", slots=(0, 1), count=50),
                OpponentLeadEntry(id="lead-2-3", slots=(2, 3), count=30),
            ],
        ),
        leadPick=LeadPickSection(
            selection=LeadSelection(ourFourSlots=(0, 1, 4, 5), ourLeadSlots=(0, 1)),
            comparisons=[],
            selectionRuleVersion="selection-v1",
            limitations=[],
        ),
        openings=_openings_for_leads(),
        refinement=None,
        gameplan=None,
        winCondition=None,
    )


def _battle(
    selection: LeadSelection,
    scenario: OpponentScenario,
    outcome: str,
    seed: int,
) -> BattleRecord:
    actions = [
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": selection.ourLeadSlots[0]},
            "move": f"M{seed}A",
            "targets": [{"kind": "pokemon", "ref": {"side": "opponent", "slot": 0}}],
        },
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": selection.ourLeadSlots[1]},
            "move": f"M{seed}B",
            "targets": [{"kind": "pokemon", "ref": {"side": "opponent", "slot": 1}}],
        },
    ]
    return BattleRecord(
        preview=PreviewRecord(
            opponent_lead_slots=scenario.opponent_lead_slots,
            our_lead_slots=selection.ourLeadSlots,
            meta={},
        ),
        turns=({"turn": 1, "ourActions": actions},),
        outcome=outcome,  # type: ignore[arg-type]
        participants={
            "ourFourSlots": list(selection.ourFourSlots),
            "ourLeadSlots": list(selection.ourLeadSlots),
            "opponentBackPair": list(scenario.opponent_back_pair),
        },
    )


def test_build_plan_includes_both_leads():
    result = _result_with_back_pairs()
    plan = build_refinement_plan(result, seed=42, budget=20)
    lead_ids = {s.opponent_lead_id for s in plan.scenarios}
    assert "lead-2-3" in lead_ids


def test_aggregate_refinement_outcomes_and_histogram():
    result = _result_with_back_pairs()
    plan = build_refinement_plan(result, seed=1, budget=3)
    selection = plan.our_selection
    battles = [
        _battle(selection, plan.scenarios[0], "win", 1),
        _battle(selection, plan.scenarios[1], "loss", 2),
        _battle(selection, plan.scenarios[2], "draw", 3),
    ]
    section = aggregate_refinement(
        battles,
        selection=selection,
        plan=plan,
        battle_ids=["a", "b", "c"],
    )
    assert section.sampleSize == 3
    assert section.outcomes == {"wins": 1, "losses": 1, "draws": 1}
    assert section.samplingPolicy == "weighted-ab"
    assert sum(row.count for row in section.scenarioCounts) == 3
    assert section.firstTurnSampleSize == 3


def test_phase_d_does_not_mutate_lead_pick_or_opponent_leads():
    from pokecoach_python.workflow.phases.phase_a import run_phase_a
    from pokecoach_python.workflow.phases.phase_b import run_phase_b
    from pokecoach_python.workflow.phases.phase_c import run_phase_c
    from pokecoach_python.workflow.phases.phase_d import run_phase_d
    from pokecoach_python.workflow.types import PhaseContext
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    def _ctx(profile: str, target: str, partial: dict, seed: int = 17) -> PhaseContext:
        return PhaseContext(
            run_id=__import__("uuid").uuid4(),
            lease_token=__import__("uuid").uuid4(),
            matchup_id=__import__("uuid").uuid4(),
            regulation="M-B",
            target_phase=target,  # type: ignore[arg-type]
            profile=profile,
            seed=seed,
            our_snapshot={"pokemon": []},
            opponent_snapshot={"pokemon": []},
            partial_result=partial,
            parameters={"profile": profile, "checkpoint_id": "stub-bc-v1"},
            engine=StubEngineAdapter(),
            report_progress=lambda *_: None,
        )

    partial: dict = {"completedPhases": []}
    partial = run_phase_a(_ctx("smoke", "A", partial)).result.model_dump(mode="json")
    partial = run_phase_c(_ctx("smoke", "C", partial)).result.model_dump(mode="json")
    partial = run_phase_b(_ctx("smoke", "B", partial)).result.model_dump(mode="json")
    before_leads = json.dumps(partial["opponentLeads"], sort_keys=True)
    before_pick = json.dumps(partial["leadPick"], sort_keys=True)
    before_openings = json.dumps(partial["openings"], sort_keys=True)
    out = run_phase_d(_ctx("smoke", "D", partial))
    assert json.dumps(out.result.opponentLeads.model_dump(mode="json"), sort_keys=True) == before_leads
    assert json.dumps(out.result.leadPick.model_dump(mode="json"), sort_keys=True) == before_pick
    assert json.dumps(out.result.openings.model_dump(mode="json"), sort_keys=True) == before_openings
    assert out.result.refinement is not None
    assert out.result.refinement.scenarioCounts
    assert out.result.completedPhases == ["A", "C", "B", "D"]


def test_aggregate_refinement_first_turn_m0():
    result = _result_with_back_pairs()
    plan = build_refinement_plan(result, seed=2, budget=1)
    selection = plan.our_selection
    battle = _battle(selection, plan.scenarios[0], "win", 1)
    battle = BattleRecord(
        preview=battle.preview,
        turns=({"turn": 1, "ourActions": []},),
        outcome=battle.outcome,
        participants=battle.participants,
    )
    section = aggregate_refinement(
        [battle],
        selection=selection,
        plan=plan,
        battle_ids=["x"],
    )
    assert section.firstTurnSampleSize == 0
    assert section.firstTurns == []


def test_aggregate_single_scenario_repeated():
    result = _result_with_back_pairs()
    plan = build_refinement_plan(result, seed=1, budget=1)
    selection = plan.our_selection
    scenario = plan.scenarios[0]
    repeated_plan = RefinementSamplingPlan(
        our_selection=selection,
        scenarios=[scenario, scenario, scenario],
    )
    battles = [_battle(selection, scenario, "win", i) for i in range(3)]
    section = aggregate_refinement(
        battles,
        selection=selection,
        plan=repeated_plan,
        battle_ids=["a", "b", "c"],
    )
    assert section.sampleSize == 3
    assert len(section.scenarioCounts) == 1
    assert section.scenarioCounts[0].count == 3


def test_phase_d_rejects_preexisting_battles():
    from pokecoach_python.workflow.phases.phase_d import run_phase_d
    from pokecoach_python.workflow.types import PhaseContext
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    partial = _result_with_back_pairs().model_dump(mode="json")
    partial["completedPhases"] = ["A", "C", "B"]

    def list_battles():
        return [_battle(
            LeadSelection(ourFourSlots=(0, 1, 4, 5), ourLeadSlots=(0, 1)),
            OpponentScenario("lead-0-1", (0, 1), (2, 3)),
            "win",
            1,
        )]

    ctx = PhaseContext(
        run_id=__import__("uuid").uuid4(),
        lease_token=__import__("uuid").uuid4(),
        matchup_id=__import__("uuid").uuid4(),
        regulation="M-B",
        target_phase="D",
        profile="smoke",
        seed=1,
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        partial_result=partial,
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1"},
        engine=StubEngineAdapter(),
        report_progress=lambda *_: None,
        list_battles=list_battles,
    )
    try:
        run_phase_d(ctx)
        raise AssertionError("expected pre-existing battles error")
    except RuntimeError as exc:
        assert "pre-existing" in str(exc)


def test_phase_d_retries_same_scenario_after_engine_error():
    from pokecoach_python.engine.contracts import SimulationRequest
    from pokecoach_python.workflow.phases.phase_d import run_phase_d
    from pokecoach_python.workflow.types import PhaseContext
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    class FlakyEngine(StubEngineAdapter):
        def __init__(self) -> None:
            super().__init__()
            self._calls = 0

        def full_battle(self, request: SimulationRequest):
            self._calls += 1
            if self._calls == 1:
                raise RuntimeError("simulated timeout")
            return super().full_battle(request)

    partial = _result_with_back_pairs().model_dump(mode="json")
    partial["completedPhases"] = ["A", "C", "B"]
    engine = FlakyEngine()
    ctx = PhaseContext(
        run_id=__import__("uuid").uuid4(),
        lease_token=__import__("uuid").uuid4(),
        matchup_id=__import__("uuid").uuid4(),
        regulation="M-B",
        target_phase="D",
        profile="smoke",
        seed=5,
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        partial_result=partial,
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1"},
        engine=engine,
        report_progress=lambda *_: None,
    )
    out = run_phase_d(ctx)
    assert out.result.refinement is not None
    assert engine._calls >= 2


def test_validate_refinement_rejects_wrong_back():
    result = _result_with_back_pairs()
    plan = build_refinement_plan(result, seed=0, budget=1)
    selection = plan.our_selection
    scenario = plan.scenarios[0]
    bad = _battle(selection, scenario, "win", 1)
    bad_participants = dict(bad.participants)
    bad_participants["opponentBackPair"] = [4, 5]
    bad = BattleRecord(
        preview=bad.preview,
        turns=bad.turns,
        outcome=bad.outcome,
        participants=bad_participants,
    )
    try:
        validate_refinement_battle(bad, our_selection=selection, scenario=scenario)
        raise AssertionError("expected validation error")
    except ValueError as exc:
        assert "back mismatch" in str(exc)
