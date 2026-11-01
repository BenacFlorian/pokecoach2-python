"""Contract validation for conditioned openings workflow (plan 10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokecoach_python.schemas.analysis_result import validate_result

_EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples" / "openings"


def test_empty_envelope():
    payload = json.loads((_EXAMPLES / "empty.json").read_text())
    validate_result(payload)


def test_progressive_checkpoints():
    for name in ("a.json", "ac.json", "acb.json", "acbd.json"):
        payload = json.loads((_EXAMPLES / name).read_text())
        validate_result(payload)


def test_ac_has_lead_pick_without_openings():
    payload = json.loads((_EXAMPLES / "ac.json").read_text())
    result = validate_result(payload)
    assert result.completedPhases == ["A", "C"]
    assert result.leadPick is not None
    assert result.openings is None


def test_acb_recommendation_matches_top_our_action():
    payload = json.loads((_EXAMPLES / "acb.json").read_text())
    result = validate_result(payload)
    assert result.openings is not None
    study = result.openings.byOpponentLead[0]
    assert study.recommendation == study.ourActions[0]
