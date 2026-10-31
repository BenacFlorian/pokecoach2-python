"""CLI: devbox run engine-check"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from pokecoach_python.core.config import get_settings
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.factory import build_engine_adapter


def _load_snapshot(path: str | None) -> dict:
    if not path:
        return {"pokemon": []}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PokeCoach engine diagnostic")
    parser.add_argument("--our-team", dest="our_team", help="JSON snapshot path")
    parser.add_argument("--opponent-team", dest="opponent_team", help="JSON snapshot path")
    parser.add_argument("--regulation", default=None)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--modes",
        default="preview",
        help="comma-separated: preview,first_turn,full_battle",
    )
    parser.add_argument("--output", help="write JSON report path")
    args = parser.parse_args(argv)

    settings = get_settings()
    regulation = args.regulation or settings.analysis_regulation_list()[0]
    our = _load_snapshot(args.our_team)
    opp = _load_snapshot(args.opponent_team)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    report: dict = {
        "engineMode": settings.engine_mode,
        "regulation": regulation,
        "modes": {},
        "capabilities": None,
        "reproduciblePreview": None,
    }
    exit_code = 0
    engine = build_engine_adapter(settings)
    try:
        caps = engine.preflight(
            {"regulation": regulation, "checkpoint_id": settings.analysis_checkpoint_id},
            (our, opp),
        )
        report["capabilities"] = asdict(caps)
        if not our.get("pokemon") or not opp.get("pokemon"):
            report["warning"] = (
                "empty snapshots — use --our-team and --opponent-team for full diagnostic"
            )
        base_req = SimulationRequest(
            our_snapshot=our,
            opponent_snapshot=opp,
            regulation=regulation,
            checkpoint_id=settings.analysis_checkpoint_id,
            seed=args.seed,
            timeout_seconds=settings.analysis_preview_timeout_seconds,
        )
        if "preview" in modes and our.get("pokemon"):
            p1 = engine.preview(base_req)
            p2 = engine.preview(base_req)
            report["modes"]["preview"] = {
                "opponentLeadSlots": p1.opponent_lead_slots,
                "ourLeadSlots": p1.our_lead_slots,
            }
            report["reproduciblePreview"] = p1.opponent_lead_slots == p2.opponent_lead_slots
            if settings.engine_mode == "vgc_bench" and not report["reproduciblePreview"]:
                exit_code = 2
        if "first_turn" in modes and our.get("pokemon"):
            preview = engine.preview(base_req)
            req = replace(base_req, opponent_lead=preview.opponent_lead_slots)
            turn1 = engine.first_turn(req)
            report["modes"]["first_turn"] = {
                "lead": turn1.opponent_lead_slots,
                "actionMoves": [a.get("move") for a in turn1.payload.get("actions", [])],
            }
        if "full_battle" in modes and our.get("pokemon"):
            preview = engine.preview(base_req)
            req = replace(base_req, opponent_lead=preview.opponent_lead_slots)
            battle = engine.full_battle(req)
            report["modes"]["full_battle"] = {
                "outcome": battle.outcome,
                "turnCount": len(battle.turns),
                "engine": battle.meta.get("engine"),
            }
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        exit_code = 1
    finally:
        engine.close()

    text = json.dumps(report, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
