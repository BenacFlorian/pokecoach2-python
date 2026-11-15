import json
from pathlib import Path

import pytest

from pokecoach_python.schemas.analysis_result import validate_result

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "examples"
OPENINGS = CONTRACTS / "openings"


@pytest.mark.parametrize(
    "name",
    [
        "empty.json",
        "a.json",
        "ac.json",
        "acb.json",
        "acbd.json",
    ],
)
def test_contract_examples_validate(name: str) -> None:
    payload = json.loads((OPENINGS / name).read_text(encoding="utf-8"))
    validate_result(payload)


def test_ac_with_sampling_diagnostics_validates() -> None:
    payload = json.loads((OPENINGS / "ac.json").read_text(encoding="utf-8"))
    payload["leadPick"]["samplingDiagnostics"] = {
        "source": "policy-samples",
        "samplingPolicy": "stochastic-team-preview-v1",
        "sampleSize": 4,
        "uniqueFours": 1,
        "uniqueSelections": 1,
        "fourFrequencies": [{"ourFourSlots": [0, 1, 4, 5], "count": 4}],
        "selectionFrequencies": [
            {
                "selection": {"ourFourSlots": [0, 1, 4, 5], "ourLeadSlots": [0, 1]},
                "count": 4,
            }
        ],
    }
    validate_result(payload)


def test_rejects_extra_root_field() -> None:
    payload = json.loads((OPENINGS / "empty.json").read_text(encoding="utf-8"))
    payload["unexpected"] = True
    with pytest.raises(ValueError):
        validate_result(payload)


def test_rejects_llm_fields_before_synthesis() -> None:
    payload = json.loads((OPENINGS / "acbd.json").read_text(encoding="utf-8"))
    payload["gameplan"] = {
        "opening": "x",
        "midgame": "x",
        "endgame": "x",
        "threats": [{"pokemon": {"side": "opponent", "slot": 0}, "explanation": "x"}],
        "strengths": [{"pokemon": {"side": "ours", "slot": 0}, "explanation": "x"}],
        "evidenceBattleIds": ["b1"],
    }
    with pytest.raises(ValueError):
        validate_result(payload)
