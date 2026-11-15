"""Contrôle RNG policy et résolution OTS pour l'inférence VGC."""

from __future__ import annotations

import hashlib
from typing import Literal

Side = Literal["ours", "opponent"]

_MAX_POLICY_SEED = (1 << 63) - 1


class PolicyDecisionSeedStream:
    """Flux de seeds dérivées de la seed de requête, du côté et de l'index de décision."""

    def __init__(self, request_seed: int, side: Side) -> None:
        if side not in ("ours", "opponent"):
            raise ValueError(f"invalid policy side: {side!r}")
        self._request_seed = int(request_seed)
        self._side = side
        self._index = 0

    @property
    def decision_index(self) -> int:
        return self._index

    def next_seed(self) -> int:
        message = (
            f"pokecoach-policy-v1:{self._request_seed}:{self._side}:{self._index}"
        ).encode()
        digest = hashlib.sha256(message).digest()
        seed = int.from_bytes(digest[:8], "big") % (_MAX_POLICY_SEED + 1)
        self._index += 1
        return seed


def seed_torch_for_policy_decision(torch_module, stream: PolicyDecisionSeedStream) -> int:
    seed = stream.next_seed()
    torch_module.manual_seed(seed)
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "is_available", None)) and cuda.is_available():
        cuda.manual_seed_all(seed)
    return seed


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def resolve_open_team_sheets(
    profile,
    env_value: str | None,
) -> bool:
    """Priorité : env explicite → profil → défaut legacy false."""
    if env_value is not None:
        normalized = env_value.strip().lower()
        if normalized in _TRUTHY:
            return True
        if normalized in _FALSY:
            return False
        raise ValueError(
            f"invalid POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS value: {env_value!r}"
        )
    if profile is not None:
        return bool(profile.inference.open_team_sheets)
    return False
