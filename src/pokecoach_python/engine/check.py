"""CLI: devbox run engine-check"""

from __future__ import annotations

import json
from dataclasses import asdict

from pokecoach_python.core.config import get_settings
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.factory import build_engine_adapter


def main() -> int:
    settings = get_settings()
    engine = build_engine_adapter(settings)
    regulation = settings.analysis_regulation_list()[0]
    caps = engine.preflight(
        {"regulation": regulation, "checkpoint_id": settings.analysis_checkpoint_id},
        ({}, {}),
    )
    print(json.dumps({"capabilities": asdict(caps)}, default=str, indent=2))
    req = SimulationRequest(
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        regulation=regulation,
        checkpoint_id=settings.analysis_checkpoint_id,
        seed=1,
        timeout_seconds=settings.analysis_preview_timeout_seconds,
    )
    preview = engine.preview(req)
    preview2 = engine.preview(req)
    print(
        json.dumps(
            {
                "preview": preview.opponent_lead_slots,
                "reproducible": preview.opponent_lead_slots == preview2.opponent_lead_slots,
            },
            indent=2,
        )
    )
    engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
