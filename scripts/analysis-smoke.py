#!/usr/bin/env python3
"""Smoke analysis command against live API + GraphQL polling."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


def _post(url: str, body: dict | None, key: uuid.UUID) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(key),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode() or "{}")
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matchup-id", type=uuid.UUID)
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--target", required=True, choices=["A", "B", "C", "D", "synthesis"])
    parser.add_argument("--profile", default="smoke", choices=["smoke", "standard"])
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="seconds to wait for pause/success",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("POKECOACH_PYTHON_URL", "http://127.0.0.1:8042/api-python"),
    )
    parser.add_argument(
        "--frontend-base",
        default=os.environ.get("POKECOACH_ANGULAR_URL", "http://127.0.0.1:4200"),
    )
    args = parser.parse_args()
    key = uuid.uuid4()
    if args.run_id:
        status, payload = _post(
            f"{args.api_base}/analyses/{args.run_id}/continue",
            {"targetPhase": args.target},
            key,
        )
        run_id = str(args.run_id)
    else:
        if not args.matchup_id:
            parser.error("--matchup-id required when --run-id omitted")
        status, payload = _post(
            f"{args.api_base}/matchups/{args.matchup_id}/analyses",
            {"targetPhase": args.target, "profile": args.profile},
            key,
        )
        run_id = payload.get("runId", "")
    print(json.dumps({"httpStatus": status, "response": payload}, indent=2))
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        time.sleep(5)
        # Minimal status poll via API is not exposed; operator should watch GraphQL/UI.
        print(f"… en attente (runId={run_id})", file=sys.stderr)
        break
    team_hint = os.environ.get("SMOKE_TEAM_ID", "team")
    matchup_part = args.matchup_id or "matchup"
    url = f"{args.frontend_base}/teams/{team_hint}/matchups/{matchup_part}?runId={run_id}"
    print(f"Frontend: {url}")
    return 0 if status in (200, 202) else 1


if __name__ == "__main__":
    raise SystemExit(main())
