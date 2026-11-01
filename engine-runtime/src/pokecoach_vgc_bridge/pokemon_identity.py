"""Stable snapshot-slot identity for capture and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Side = Literal["ours", "opponent"]


@dataclass(frozen=True)
class PokemonIdentityMap:
    """Maps roster slots 0-5 to species labels from team snapshots."""

    our_species: tuple[str, ...]
    opponent_species: tuple[str, ...]

    @classmethod
    def from_snapshots(
        cls,
        our_snapshot: dict[str, Any],
        opponent_snapshot: dict[str, Any],
    ) -> PokemonIdentityMap:
        return cls(
            our_species=_species_row(our_snapshot),
            opponent_species=_species_row(opponent_snapshot),
        )

    def species(self, side: Side, slot: int) -> str:
        row = self.our_species if side == "ours" else self.opponent_species
        if slot < 0 or slot >= len(row):
            raise ValueError(f"identity slot out of range: {side}:{slot}")
        name = row[slot]
        if not name:
            raise ValueError(f"unresolved identity for {side}:{slot}")
        return name

    def pokemon_ref(self, side: Side, slot: int) -> dict[str, Any]:
        return {"side": side, "slot": int(slot)}

    def resolve_side_from_protocol(self, prefix: str, *, our_is_p1: bool) -> Side:
        if prefix not in {"p1", "p2"}:
            raise ValueError(f"invalid protocol prefix {prefix}")
        is_p1 = prefix == "p1"
        ours = is_p1 if our_is_p1 else not is_p1
        return "ours" if ours else "opponent"


def _species_row(snapshot: dict[str, Any]) -> tuple[str, ...]:
    mons = snapshot.get("pokemon") or []
    names: list[str] = []
    for idx in range(6):
        if idx < len(mons) and isinstance(mons[idx], dict):
            raw = mons[idx].get("species") or mons[idx].get("name") or ""
            names.append(str(raw).strip())
        else:
            names.append("")
    return tuple(names)
