#!/usr/bin/env python3
"""Export benchmark manifest (placeholder — fill from real matchups)."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--matchup-id", action="append", default=[])
    args = parser.parse_args()
    manifest = {"version": 1, "matchups": args.matchup_id}
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
