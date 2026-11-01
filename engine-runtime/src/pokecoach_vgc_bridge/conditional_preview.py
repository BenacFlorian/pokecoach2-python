"""Conditional preview sampling until opponent lead matches (phase B)."""

from __future__ import annotations

import os
from typing import Any

from pokecoach_vgc_bridge.normalization import build_preview


def preview_until_opponent_lead(
    *,
    preview_fn,
    opponent_lead: tuple[int, int],
    seed: int,
    max_rejects: int | None = None,
    **preview_kwargs: Any,
) -> tuple[dict[str, Any], int, int]:
    """Return preview dict, seed used, and reject count."""
    cap = max_rejects
    if cap is None:
        cap = int(os.environ.get("POKECOACH_ENGINE_MAX_REJECT_PREVIEWS", "500"))
    lead = (min(opponent_lead[0], opponent_lead[1]), max(opponent_lead[0], opponent_lead[1]))
    for attempt in range(cap):
        attempt_seed = seed + attempt
        raw = preview_fn(seed=attempt_seed, **preview_kwargs)
        opp = raw.get("opponentLeadSlots") or raw.get("opponent_lead_slots")
        if not opp or len(opp) != 2:
            continue
        got = (int(opp[0]), int(opp[1]))
        if got[0] == got[1]:
            continue
        ordered = (min(got[0], got[1]), max(got[0], got[1]))
        if ordered == lead:
            return raw, attempt_seed, attempt
    raise ValueError(f"simulated lead rejection after {cap} previews")
