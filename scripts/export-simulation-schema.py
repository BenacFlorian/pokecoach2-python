#!/usr/bin/env python3
"""Regenerate simulation-result-v2.schema.json from Pydantic models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pokecoach_python.schemas.analysis_result import SimulationResultV2  # noqa: E402

OUT = ROOT / "contracts" / "simulation-result-v2.schema.json"


def main() -> None:
    schema = SimulationResultV2.model_json_schema()
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
