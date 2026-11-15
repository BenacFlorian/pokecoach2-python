#!/usr/bin/env python3
"""Audit contrefactuel du conditionnement team preview (opérateur)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pokecoach_python.core.config import Settings
from pokecoach_python.diagnostics.teampreview_conditioning import (
    NamedSnapshot,
    report_exit_code,
    report_to_jsonable,
    run_conditioning_audit,
)
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_opponent(raw: str) -> NamedSnapshot:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("opponent must be NAME=PATH")
    name, path = raw.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("opponent name required")
    snapshot = _load_snapshot(Path(path).expanduser())
    return NamedSnapshot(name=name, snapshot=snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit team preview conditioning")
    parser.add_argument("--our-snapshot", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=_parse_opponent, required=True)
    parser.add_argument("--regulation", required=True)
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--base-seed", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        our = _load_snapshot(args.our_snapshot)
        opponents = list(args.opponent)
        if len(opponents) < 2:
            raise ValueError("at least two opponents required")
        settings = Settings()
        engine = VgcBenchEngineAdapter(settings)
        try:
            engine.preflight(
                {"regulation": args.regulation, "checkpoint_id": args.checkpoint_id},
                (our, opponents[0].snapshot),
            )
            report = run_conditioning_audit(
                engine,
                our_snapshot=our,
                opponents=opponents,
                regulation=args.regulation,
                checkpoint_id=args.checkpoint_id,
                base_seed=args.base_seed,
                samples=args.samples,
                timeout_seconds=args.timeout_seconds,
            )
        finally:
            engine.close()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = report_to_jsonable(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
