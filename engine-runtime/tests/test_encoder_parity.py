"""Dimensions encodeur / masque attendues (inspect mb-002)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mb002_inspect_dims.json"


def test_mb002_inspect_dimensions_fixture():
    if not FIXTURE.is_file():
        pytest.skip("fixture absente")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["observation_shape"] == [7, 6936]
    assert data["mask_shape"] == [7, 214]
