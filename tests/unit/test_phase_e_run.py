from __future__ import annotations

import uuid

import pytest

from pokecoach_python.core.config import Settings
from pokecoach_python.db.analysis_repository import ClaimedRun, RunRow
from pokecoach_python.engine.provenance import build_run_provenance
from pokecoach_python.graphs.matchup_gameplan.models import StrategyOutput
from pokecoach_python.schemas.analysis_result import validate_result
from pokecoach_python.workflow import registry
from pokecoach_python.workflow.phases.phase_e import assemble_complete_result, run_phase_e
from pokecoach_python.workflow.runner import WorkflowRunner
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput
from tests.unit.phase_e_fixtures import make_snapshots, make_stored_battle


def _strategy_payload() -> dict:
    return {
        "gameplan": {
            "opening": "Use the first turns to secure speed with {{ours:0}}.",
            "midgame": "Trade into their damage core once positioning is stable via {{ours:1}}.",
            "endgame": "Preserve {{ours:0}} for the final exchange.",
            "threats": [
                {
                    "pokemon": {"side": "opponent", "slot": 2},
                    "explanation": "{{opponent:2}} was the main damage source in the observed loss.",
                }
            ],
            "strengths": [
                {
                    "pokemon": {"side": "ours", "slot": 0},
                    "explanation": "{{ours:0}} converted early pressure into clean endgames in the wins.",
                }
            ],
            "evidenceBattleIds": ["b1", "b2"],
        },
        "winCondition": {
            "description": "Contain {{opponent:2}}, then close with {{ours:0}} once tempo is secured.",
            "rationale": "The winning lines preserved {{ours:0}} for the final turns after stabilising.",
            "evidenceBattleIds": ["b1"],
        },
    }


def _partial_acbd(battle_ids: list[str]) -> dict:
    wins = 1 if len(battle_ids) >= 1 else 0
    losses = 1 if len(battle_ids) >= 2 else 0
    draws = max(0, len(battle_ids) - wins - losses)
    return {
        "schemaVersion": 2,
        "source": "simulation",
        "completedPhases": ["A", "C", "B", "D"],
        "opponentLeads": {
            "sampleSize": 2,
            "leads": [
                {"id": "lead-0-1", "slots": [0, 1], "count": 1},
                {"id": "lead-2-3", "slots": [2, 3], "count": 1},
            ],
        },
        "leadPick": {
            "selection": {"ourFourSlots": [0, 1, 4, 5], "ourLeadSlots": [0, 1]},
            "comparisons": [],
            "selectionRuleVersion": "selection-v1",
            "limitations": [],
        },
        "openings": {
            "selection": {"ourFourSlots": [0, 1, 4, 5], "ourLeadSlots": [0, 1]},
            "recommendationRule": "model-frequency-v1",
            "samplingPolicy": "conditional-back-v1",
            "byOpponentLead": [],
        },
        "refinement": {
            "configuration": {"ourFourSlots": [0, 1, 4, 5], "ourLeadSlots": [0, 1]},
            "samplingPolicy": "weighted-ab",
            "samplingScope": "all-observed-leads",
            "sampleSize": len(battle_ids),
            "outcomes": {"wins": wins, "losses": losses, "draws": draws},
            "scenarioCounts": [
                {
                    "opponentLeadId": "lead-0-1",
                    "opponentLeadSlots": [0, 1],
                    "opponentBackPair": [2, 3],
                    "count": len(battle_ids),
                }
            ],
            "firstTurnSampleSize": 0,
            "firstTurns": [],
            "battleIds": battle_ids,
            "limitations": [],
        },
        "gameplan": None,
        "winCondition": None,
    }


def _real_run_provenance() -> dict:
    return build_run_provenance(
        engine_mode="vgc_bench",
        product_phases=["A", "C", "B", "D", "synthesis"],
        hello={"engine": "vgc-bench", "checkpointLoaded": True},
        checkpoint_id="stub-bc-v1",
    )


class _FakeStore:
    def __init__(self) -> None:
        self.sources = None
        self.create_calls = 0
        self.update_calls = 0

    def create_sources(self, *, sources, **_kwargs):
        self.create_calls += 1
        self.sources = sources

    def update_sources(self, *, sources, **_kwargs):
        self.update_calls += 1
        self.sources = sources

    def load_sources(self, _run_id):
        return self.sources


class _FakeClient:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or _strategy_payload()
        self.last_invocation = {"model": "deepseek-ai/DeepSeek-V4.1-Flash-1017"}

    def generate(self, _sources, _messages):
        return StrategyOutput.model_validate(self.payload)


def test_run_phase_e_prepares_sources_and_assembles_complete_result() -> None:
    battles = [
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(0, 1),
            opponent_survivors=(),
        ),
        make_stored_battle(
            "b2",
            "refinement:0002",
            outcome="loss",
            our_survivors=(),
            opponent_survivors=(2,),
        ),
    ]
    progress = []
    store = _FakeStore()
    ctx = PhaseContext(
        run_id=uuid.uuid4(),
        lease_token=uuid.uuid4(),
        matchup_id=uuid.uuid4(),
        regulation="M-B",
        target_phase="synthesis",
        profile="smoke",
        seed=1,
        our_snapshot=make_snapshots()[0],
        opponent_snapshot=make_snapshots()[1],
        partial_result=_partial_acbd(["b1", "b2"]),
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1", "seed": "1"},
        engine=None,
        report_progress=lambda *args: progress.append(args),
        list_d_battles=lambda: battles,
        run_provenance=_real_run_provenance(),
        result_revision=1,
        settings=Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key"),
        analysis_repository=object(),
        synthesis_store=store,
        synthesis_client=_FakeClient(),
    )
    out = run_phase_e(ctx)
    assert out.result.completedPhases == ["A", "C", "B", "D", "synthesis"]
    assert out.result.gameplan is not None
    assert out.result.gameplan.strengths[0].pokemon.slot == 0
    assert store.create_calls == 1
    assert progress == [("synthesis", 0, 1), ("synthesis", 1, 1)]
    assert out.metadata_patch["synthesis"]["invocation"]["selectedBattleIds"] == ["b2", "b1"]


def test_run_phase_e_rejects_mismatched_battle_ids() -> None:
    ctx = PhaseContext(
        run_id=uuid.uuid4(),
        lease_token=uuid.uuid4(),
        matchup_id=uuid.uuid4(),
        regulation="M-B",
        target_phase="synthesis",
        profile="smoke",
        seed=1,
        our_snapshot=make_snapshots()[0],
        opponent_snapshot=make_snapshots()[1],
        partial_result=_partial_acbd(["expected"]),
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1", "seed": "1"},
        engine=None,
        report_progress=lambda *_: None,
        list_d_battles=lambda: [
            make_stored_battle(
                "other",
                "refinement:0001",
                outcome="win",
                our_survivors=(0,),
                opponent_survivors=(),
            )
        ],
        run_provenance=_real_run_provenance(),
        result_revision=1,
        settings=Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key"),
        analysis_repository=object(),
        synthesis_store=_FakeStore(),
        synthesis_client=_FakeClient(),
    )
    with pytest.raises(RuntimeError, match="battle ids"):
        run_phase_e(ctx)


def test_workflow_runner_synthesis_only_skips_engine_build(monkeypatch) -> None:
    original = registry._HANDLERS["synthesis"]
    complete_result = assemble_complete_result(_partial_acbd(["b1", "b2"]), _strategy_payload())

    def fake_phase_e(ctx: PhaseContext) -> PhaseOutput:
        assert ctx.list_d_battles is not None
        return PhaseOutput(
            phase="synthesis",
            result=complete_result,
            execution_slice={"phase": "synthesis"},
            metadata_patch={"phases": {"synthesis": {"phase": "synthesis"}}},
        )

    class FakeRepo:
        def __init__(self) -> None:
            self.complete_calls = 0
            self.row = RunRow(
                id=uuid.uuid4(),
                matchup_id=uuid.uuid4(),
                status="running",
                target_phase="synthesis",
                partial_result=_partial_acbd(["b1", "b2"]),
                result_revision=1,
                parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1", "seed": "1"},
                regulation="M-B",
                our_snapshot=make_snapshots()[0],
                opponent_snapshot=make_snapshots()[1],
                process_status="PENDING_STATS",
                provenance=_real_run_provenance(),
            )

        def ensure_run_active(self, *_args, **_kwargs):
            return None

        def update_progress(self, *_args, **_kwargs):
            return True

        def is_cancelled(self, *_args, **_kwargs):
            return False

        def list_d_battles(self, *_args, **_kwargs):
            return []

        def publish_complete(self, *_args, **_kwargs):
            self.complete_calls += 1
            self.row = RunRow(
                id=self.row.id,
                matchup_id=self.row.matchup_id,
                status="succeeded",
                target_phase="synthesis",
                partial_result=complete_result.model_dump(mode="json"),
                result_revision=2,
                parameters=self.row.parameters,
                regulation=self.row.regulation,
                our_snapshot=self.row.our_snapshot,
                opponent_snapshot=self.row.opponent_snapshot,
                process_status="SUCCESS",
                provenance=self.row.provenance,
            )

        def load_run_row(self, *_args, **_kwargs):
            return self.row

        def fail_run(self, *_args, **_kwargs):
            raise AssertionError("run should not fail")

    registry._HANDLERS["synthesis"] = fake_phase_e
    monkeypatch.setattr(
        "pokecoach_python.workflow.runner.provenance_for_worker_compat",
        lambda *_: (_ for _ in ()).throw(AssertionError("no provenance check")),
    )
    monkeypatch.setattr("pokecoach_python.workflow.runner.build_engine_adapter", lambda *_: (_ for _ in ()).throw(AssertionError("no engine build")))
    repo = FakeRepo()
    runner = WorkflowRunner(
        repo,
        Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key"),
    )
    try:
        runner.run_claimed(ClaimedRun(context_row=repo.row, lease_token=uuid.uuid4()))
    finally:
        registry._HANDLERS["synthesis"] = original
    assert repo.complete_calls == 1


def test_workflow_runner_publishes_d_before_synthesis(monkeypatch) -> None:
    original_d = registry._HANDLERS["D"]
    original_e = registry._HANDLERS["synthesis"]
    partial_before_d = _partial_acbd(["b1", "b2"])
    partial_before_d["completedPhases"] = ["A", "C", "B"]
    partial_before_d["refinement"] = None
    complete_result = assemble_complete_result(_partial_acbd(["b1", "b2"]), _strategy_payload())

    def fake_phase_d(_ctx: PhaseContext) -> PhaseOutput:
        return PhaseOutput(
            phase="D",
            result=validate_result(_partial_acbd(["b1", "b2"])),
            execution_slice={"phase": "D"},
        )

    def fake_phase_e(ctx: PhaseContext) -> PhaseOutput:
        assert ctx.result_revision == 1
        return PhaseOutput(
            phase="synthesis",
            result=complete_result,
            execution_slice={"phase": "synthesis"},
            metadata_patch={"phases": {"synthesis": {"phase": "synthesis"}}},
        )

    class DummyEngine:
        def close(self) -> None:
            return None

    class FakeRepo:
        def __init__(self) -> None:
            self.publish_phase_calls = 0
            self.publish_complete_calls = 0
            self.row = RunRow(
                id=uuid.uuid4(),
                matchup_id=uuid.uuid4(),
                status="running",
                target_phase="synthesis",
                partial_result=partial_before_d,
                result_revision=0,
                parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1", "seed": "1"},
                regulation="M-B",
                our_snapshot=make_snapshots()[0],
                opponent_snapshot=make_snapshots()[1],
                process_status="PENDING_STATS",
                provenance=_real_run_provenance(),
            )

        def ensure_run_active(self, *_args, **_kwargs):
            return None

        def update_progress(self, *_args, **_kwargs):
            return True

        def is_cancelled(self, *_args, **_kwargs):
            return False

        def list_battles(self, *_args, **_kwargs):
            return []

        def list_d_battles(self, *_args, **_kwargs):
            return []

        def publish_phase(self, *_args, partial_result, **_kwargs):
            self.publish_phase_calls += 1
            self.row = RunRow(
                id=self.row.id,
                matchup_id=self.row.matchup_id,
                status="running",
                target_phase="synthesis",
                partial_result=partial_result,
                result_revision=1,
                parameters=self.row.parameters,
                regulation=self.row.regulation,
                our_snapshot=self.row.our_snapshot,
                opponent_snapshot=self.row.opponent_snapshot,
                process_status="PENDING_STATS",
                provenance=self.row.provenance,
            )

        def publish_complete(self, *_args, **_kwargs):
            self.publish_complete_calls += 1
            self.row = RunRow(
                id=self.row.id,
                matchup_id=self.row.matchup_id,
                status="succeeded",
                target_phase="synthesis",
                partial_result=complete_result.model_dump(mode="json"),
                result_revision=2,
                parameters=self.row.parameters,
                regulation=self.row.regulation,
                our_snapshot=self.row.our_snapshot,
                opponent_snapshot=self.row.opponent_snapshot,
                process_status="SUCCESS",
                provenance=self.row.provenance,
            )

        def load_run_row(self, *_args, **_kwargs):
            return self.row

        def fail_run(self, *_args, **_kwargs):
            raise AssertionError("run should not fail")

    registry._HANDLERS["D"] = fake_phase_d
    registry._HANDLERS["synthesis"] = fake_phase_e
    monkeypatch.setattr("pokecoach_python.workflow.runner.provenance_for_worker_compat", lambda *_: {})
    monkeypatch.setattr("pokecoach_python.workflow.runner.assert_run_engine_compatible", lambda *_: None)
    monkeypatch.setattr("pokecoach_python.workflow.runner.build_engine_adapter", lambda *_: DummyEngine())
    repo = FakeRepo()
    runner = WorkflowRunner(
        repo,
        Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key"),
    )
    try:
        runner.run_claimed(ClaimedRun(context_row=repo.row, lease_token=uuid.uuid4()))
    finally:
        registry._HANDLERS["D"] = original_d
        registry._HANDLERS["synthesis"] = original_e
    assert repo.publish_phase_calls == 1
    assert repo.publish_complete_calls == 1
