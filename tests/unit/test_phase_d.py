"""Unit tests for phase D refinement configuration and aggregation."""

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
            sampleSize=100,
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


from pokecoach_python.workflow.aggregation.refinement import (
    FixedBattleConfiguration,
    aggregate_refinement,
    select_refinement_configuration,
    validate_refinement_battle,
)


def _battle(config: FixedBattleConfiguration, outcome: str, seed: int) -> BattleRecord:
    actions = [
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": config.our_lead[0]},
            "move": f"M{seed}A",
            "targets": [{"kind": "pokemon", "ref": {"side": "opponent", "slot": 0}}],
        },
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": config.our_lead[1]},
            "move": f"M{seed}B",
            "targets": [{"kind": "pokemon", "ref": {"side": "opponent", "slot": 1}}],
        },
    ]
    return BattleRecord(
        preview=PreviewRecord(
            opponent_lead_slots=config.opponent_lead,
            our_lead_slots=config.our_lead,
            meta={},
        ),
        turns=({"turn": 1, "ourActions": actions},),
        outcome=outcome,  # type: ignore[arg-type]
        participants={
            "ourFourSlots": list(config.our_four),
            "ourLeadSlots": list(config.our_lead),
            "opponentBackPair": list(config.opponent_back),
        },
    )


def test_select_configuration_uses_top_studied_lead_and_best_back():
    result = _result_with_back_pairs()
    config = select_refinement_configuration(result, studied_lead_count=2)
    assert config.opponent_lead_id == "lead-0-1"
    assert config.opponent_back == (2, 3)
    assert config.our_four == (0, 1, 4, 5)


def test_back_tie_break_by_slots():
    result = _result_with_back_pairs()
    openings = result.openings
    assert openings is not None
    patched_openings = openings.model_copy(
        update={
            "byOpponentLead": [
                OpeningStudyEntry(
                    opponentLeadId="lead-0-1",
                    opponentLeadSlots=(0, 1),
                    sampleSize=4,
                    opponentActions=[],
                    ourActions=[],
                    recommendation={"value": [], "count": 1, "sampleSize": 4},
                    backPairs=[
                        {"value": [5, 4], "count": 2, "sampleSize": 4},
                        {"value": [2, 3], "count": 2, "sampleSize": 4},
                    ],
                    backSlotMarginals=[],
                    endStateNotes=[],
                )
            ]
        }
    )
    patched = result.model_copy(update={"openings": patched_openings})
    config = select_refinement_configuration(patched, studied_lead_count=1)
    assert config.opponent_back == (2, 3)


def test_aggregate_refinement_outcomes_and_preserves_checkpoint_fields():
    result = _result_with_back_pairs()
    config = select_refinement_configuration(result, studied_lead_count=2)
    battles = [
        _battle(config, "win", 1),
        _battle(config, "loss", 2),
        _battle(config, "draw", 3),
    ]
    section = aggregate_refinement(battles, config, battle_ids=["a", "b", "c"])
    assert section.sampleSize == 3
    assert section.outcomes == {"wins": 1, "losses": 1, "draws": 1}
    assert len(section.firstTurns) >= 1


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
    assert out.result.completedPhases == ["A", "C", "B", "D"]


def test_validate_refinement_rejects_wrong_back():
    result = _result_with_back_pairs()
    config = select_refinement_configuration(result, studied_lead_count=1)
    bad = _battle(config, "win", 1)
    bad_participants = dict(bad.participants)
    bad_participants["opponentBackPair"] = [4, 5]
    bad = BattleRecord(
        preview=bad.preview,
        turns=bad.turns,
        outcome=bad.outcome,
        participants=bad_participants,
    )
    try:
        validate_refinement_battle(bad, config)
        raise AssertionError("expected validation error")
    except ValueError as exc:
        assert "back mismatch" in str(exc)
