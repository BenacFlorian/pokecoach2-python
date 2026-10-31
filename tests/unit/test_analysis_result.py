import json
from pathlib import Path

import pytest

from pokecoach_python.schemas.analysis_result import validate_result

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "examples"


@pytest.mark.parametrize(
    "name",
    [
        "simulation-empty.json",
        "simulation-a.json",
        "simulation-ab.json",
        "simulation-abc.json",
        "simulation-abcd.json",
        "simulation-complete.json",
    ],
)
def test_contract_examples_validate(name: str) -> None:
    payload = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    require_complete = name == "simulation-complete.json"
    validate_result(payload, require_complete=require_complete)


def test_rejects_extra_root_field() -> None:
    payload = json.loads((CONTRACTS / "simulation-empty.json").read_text(encoding="utf-8"))
    payload["unexpected"] = True
    with pytest.raises(ValueError):
        validate_result(payload)


def test_rejects_llm_fields_before_synthesis() -> None:
    payload = json.loads((CONTRACTS / "simulation-abcd.json").read_text(encoding="utf-8"))
    payload["gameplan"] = {"opening": "x", "midgame": "x", "endgame": "x", "threats": [], "preserve": [], "eliminate": [], "adaptations": [], "evidenceBattleIds": []}
    with pytest.raises(ValueError):
        validate_result(payload)
