"""Build Showdown export text from PokeCoach team snapshots."""

from __future__ import annotations

from typing import Any


def snapshot_to_showdown_export(snapshot: dict[str, Any]) -> str:
    mons = snapshot.get("pokemon")
    if not isinstance(mons, list) or len(mons) != 6:
        raise ValueError("snapshot must contain exactly six Pokémon")
    blocks: list[str] = []
    for idx, mon in enumerate(mons):
        if not isinstance(mon, dict):
            raise ValueError(f"pokemon[{idx}] must be an object")
        raw = mon.get("rawBlock")
        if isinstance(raw, str) and raw.strip():
            blocks.append(raw.strip())
            continue
        species = mon.get("species")
        moves = mon.get("moves")
        if not isinstance(species, str) or not isinstance(moves, list):
            raise ValueError(f"pokemon[{idx}] missing rawBlock or species/moves")
        move_lines = "\n".join(f"- {m}" for m in moves if isinstance(m, str))
        blocks.append(f"{species}\n{move_lines}".strip())
    return "\n\n".join(blocks)


def pokecoach_regulation_to_vgc_reg(regulation: str) -> str:
    """Map PokeCoach regulation label to VGC-Bench reg key (e.g. M-B -> mb)."""
    normalized = regulation.strip().upper().replace("_", "-")
    if normalized in ("M-B", "MB"):
        return "mb"
    if normalized in ("M-A", "MA"):
        return "ma"
    if len(normalized) == 2 and normalized.isalpha():
        return normalized.lower()
    raise ValueError(f"unsupported regulation {regulation!r}")
