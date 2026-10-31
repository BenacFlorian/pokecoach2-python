"""Unit tests for phase C selection aggregation."""

from __future__ import annotations

from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.schemas.analysis_result import OpponentLeadEntry, OpponentLeadsSection
from pokecoach_python.workflow.aggregation.selections import aggregate_selections


def _battle(
    *,
    opp_lead: tuple[int, int],
    our_four: tuple[int, int, int, int],
    our_lead: tuple[int, int],
    outcome: str,
    seed: int,
) -> BattleRecord:
    return BattleRecord(
        preview=PreviewRecord(
            opponent_lead_slots=opp_lead,
            our_lead_slots=our_lead,
            meta={},
        ),
        turns=(
            {
                "turn": 1,
                "ourActions": [
                    {
                        "kind": "move",
                        "actor": {"side": "ours", "slot": our_lead[0]},
                        "move": f"Move-{seed}-A",
                        "targets": [
                            {"kind": "pokemon", "ref": {"side": "opponent", "slot": 0}}
                        ],
                    },
                    {
                        "kind": "move",
                        "actor": {"side": "ours", "slot": our_lead[1]},
                        "move": f"Move-{seed}-B",
                        "targets": [
                            {"kind": "pokemon", "ref": {"side": "opponent", "slot": 1}}
                        ],
                    },
                ],
            },
        ),
        outcome=outcome,  # type: ignore[arg-type]
        participants={
            "ourFourSlots": list(our_four),
            "ourLeadSlots": list(our_lead),
        },
    )


def _leads_section() -> OpponentLeadsSection:
    return OpponentLeadsSection(
        sampleSize=100,
        leads=[
            OpponentLeadEntry(id="lead-0-1", slots=(0, 1), count=50, turn1=None),
            OpponentLeadEntry(id="lead-2-3", slots=(2, 3), count=30, turn1=None),
            OpponentLeadEntry(id="lead-4-5", slots=(4, 5), count=20, turn1=None),
        ],
    )


def test_four_slots_leads_first_order():
    from pokecoach_python.workflow.battle_records import four_slots_leads_first

    assert four_slots_leads_first((2, 3, 4, 5), (4, 5)) == (4, 5, 2, 3)


def test_weighted_average_beats_simple_majority():
    leads = _leads_section()
    cand_a = (0, 1, 2, 3)
    cand_b = (0, 1, 4, 5)
    battles: list[BattleRecord] = []
    for seed, outcome in enumerate(["win", "win"], start=1):
        battles.append(
            _battle(
                opp_lead=(0, 1),
                our_four=cand_a,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    for seed, outcome in enumerate(["loss", "loss"], start=10):
        battles.append(
            _battle(
                opp_lead=(2, 3),
                our_four=cand_a,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    for seed, outcome in enumerate(["win", "win"], start=20):
        battles.append(
            _battle(
                opp_lead=(4, 5),
                our_four=cand_a,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    for seed, outcome in enumerate(["loss", "loss"], start=30):
        battles.append(
            _battle(
                opp_lead=(0, 1),
                our_four=cand_b,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    for seed, outcome in enumerate(["win", "win"], start=40):
        battles.append(
            _battle(
                opp_lead=(2, 3),
                our_four=cand_b,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    for seed, outcome in enumerate(["win", "win"], start=50):
        battles.append(
            _battle(
                opp_lead=(4, 5),
                our_four=cand_b,
                our_lead=(0, 1),
                outcome=outcome,
                seed=seed,
            )
        )
    result = aggregate_selections(battles, leads, top_n=3)
    assert result.selection.ourFourSlots == cand_a


def test_incomplete_coverage_fallback():
    leads = _leads_section()
    cand = (0, 1, 2, 3)
    battles = [
        _battle(opp_lead=(0, 1), our_four=cand, our_lead=(0, 1), outcome="win", seed=1),
        _battle(opp_lead=(2, 3), our_four=cand, our_lead=(0, 1), outcome="win", seed=2),
    ]
    result = aggregate_selections(battles, leads, top_n=3)
    assert any("incomplète" in line.lower() for line in result.limitations)


def test_draw_and_single_battle_rate():
    leads = OpponentLeadsSection(
        sampleSize=10,
        leads=[OpponentLeadEntry(id="lead-0-1", slots=(0, 1), count=10, turn1=None)],
    )
    cand = (0, 1, 2, 3)
    battles = [
        _battle(opp_lead=(0, 1), our_four=cand, our_lead=(0, 1), outcome="draw", seed=1),
    ]
    result = aggregate_selections(battles, leads, top_n=1)
    row = next(c for c in result.comparisons if c["opponentLeadId"] == "lead-0-1")
    assert row["draws"] == 1 and row["wins"] == 0 and row["losses"] == 0


def test_unobserved_matchup_omitted_from_comparisons():
    leads = _leads_section()
    cand = (0, 1, 2, 3)
    battles = [
        _battle(opp_lead=(0, 1), our_four=cand, our_lead=(0, 1), outcome="win", seed=1),
    ]
    result = aggregate_selections(battles, leads, top_n=3)
    ids = {row["opponentLeadId"] for row in result.comparisons}
    assert "lead-2-3" not in ids
    assert all(row.get("sampleSize", 0) > 0 for row in result.comparisons)


def test_phase_c_envelope_preserves_ab():
    from pokecoach_python.workflow.phases.phase_a import run_phase_a
    from pokecoach_python.workflow.phases.phase_b import run_phase_b
    from pokecoach_python.workflow.phases.phase_c import run_phase_c
    from pokecoach_python.workflow.types import PhaseContext
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    def _ctx(profile: str, target: str, partial: dict, seed: int = 11) -> PhaseContext:
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

    phase_a = run_phase_a(_ctx("smoke", "A", {"completedPhases": []}))
    partial = phase_a.result.model_dump(mode="json")
    phase_b = run_phase_b(_ctx("smoke", "B", partial))
    partial_b = phase_b.result.model_dump(mode="json")
    phase_c = run_phase_c(_ctx("smoke", "C", partial_b))
    assert phase_c.result.completedPhases == ["A", "B", "C"]
    assert phase_c.result.opponentLeads == phase_b.result.opponentLeads
    assert phase_c.result.leadPick is not None
    assert phase_c.result.leadPick.selectionRuleVersion == "selection-v1"
