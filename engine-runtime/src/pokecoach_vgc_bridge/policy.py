"""Load pinned bridge manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_manifest(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"schemaVersion": 0, "missing": True, "path": path}
    return json.loads(p.read_text(encoding="utf-8"))
