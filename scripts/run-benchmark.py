#!/usr/bin/env python3
"""Run benchmark manifest sequentially via analysis API."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    with open(args.manifest, encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not manifest.get("matchups"):
        print("manifest has no matchups", file=sys.stderr)
        return 1
    print("Use analysis-smoke.py per matchup until batch API exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
