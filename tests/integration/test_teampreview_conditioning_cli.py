from __future__ import annotations

import json
from pathlib import Path

from pokecoach_python.diagnostics.teampreview_conditioning import (
    NamedSnapshot,
    report_exit_code,
    report_to_jsonable,
    run_conditioning_audit,
)
from pokecoach_python.engine.contracts import EngineAdapter, PreviewRecord, SimulationRequest


class FakePreviewEngine(EngineAdapter):
    def preflight(self, config, snapshots):
        raise NotImplementedError

    def close(self) -> None:
        return None

    def preview(self, request: SimulationRequest) -> PreviewRecord:
        opp_name = request.opponent_snapshot.get("_name", "x")
        seed = request.seed
        base_four = (0, 1, 2, 3) if opp_name == "balance" else (0, 1, 4, 5)
        if seed % 5 == 0:
            base_four = (0, 1, 2, 4)
        fp = f"sha256-v1:{opp_name}-{seed}"
        return PreviewRecord(
            opponent_lead_slots=(0, 1),
            our_lead_slots=(base_four[0], base_four[1]),
            our_four_slots=base_four,
            opponent_four_slots=(0, 1, 2, 3),
            meta={"ourObservationFingerprint": fp},
        )

    def first_turn(self, request):
        raise NotImplementedError

    def full_battle(self, request):
        raise NotImplementedError


def test_run_conditioning_audit_paired_seeds(tmp_path: Path):
    our = {"pokemon": [], "_name": "ours"}
    opponents = [
        NamedSnapshot("balance", {"pokemon": [], "_name": "balance"}),
        NamedSnapshot("trick", {"pokemon": [], "_name": "trick"}),
    ]
    engine = FakePreviewEngine()
    report = run_conditioning_audit(
        engine,
        our_snapshot=our,
        opponents=opponents,
        regulation="M-C",
        checkpoint_id="test",
        base_seed=1,
        samples=5,
        timeout_seconds=1.0,
    )
    assert report.samples == 5
    assert report_exit_code(report) == 0
    statuses = {row.status for row in report.pair_comparisons}
    assert "observation-and-selection-differ" in statuses
    out = tmp_path / "audit.json"
    out.write_text(json.dumps(report_to_jsonable(report), indent=2), encoding="utf-8")
    assert out.is_file()
