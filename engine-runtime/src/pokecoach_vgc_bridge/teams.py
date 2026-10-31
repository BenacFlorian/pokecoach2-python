"""Team construction from PokeCoach snapshots (no set rewriting)."""

from __future__ import annotations

from typing import Any


def roster_slots(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    mons = snapshot.get("pokemon")
    if not isinstance(mons, list):
        raise ValueError("snapshot.pokemon must be an array")
    if len(mons) != 6:
        raise ValueError("VGC team must have exactly six Pokémon")
    return [dict(m) if isinstance(m, dict) else {} for m in mons]
