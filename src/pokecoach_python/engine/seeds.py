"""Deterministic seeds for engine, worker and Showdown (plan 04b)."""

from __future__ import annotations

import hashlib


def run_base_seed(parameters: dict) -> int:
    raw = parameters.get("seed", "0")
    text = str(raw)
    try:
        if len(text) > 8:
            return int(text, 16) % (2**31)
        return int(text) % (2**31)
    except ValueError:
        digest = hashlib.sha256(text.encode()).digest()
        return int.from_bytes(digest[:4], "big") % (2**31)


def phase_attempt_seed(run_seed: int, phase: str, *parts: int) -> int:
    blob = f"{run_seed}:{phase}:" + ":".join(str(p) for p in parts)
    digest = hashlib.sha256(blob.encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def showdown_battle_seed(run_seed: int, mode: str, attempt: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:showdown:{mode}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)
