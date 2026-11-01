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
        "threats": [],
        "preserve": [],
        "eliminate": [],
        "adaptations": [],
        "evidenceBattleIds": [],
    }
    with pytest.raises(ValueError):
        validate_result(payload)
