from __future__ import annotations

import pytest

from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap


def test_identity_resolves_side_from_protocol():
    identity = PokemonIdentityMap.from_snapshots(
        {"pokemon": [{"species": "A"}]},
        {"pokemon": [{"species": "B"}]},
    )
    assert identity.resolve_side_from_protocol("p1", our_is_p1=True) == "ours"
    assert identity.resolve_side_from_protocol("p2", our_is_p1=True) == "opponent"


def test_identity_species_requires_slot():
    identity = PokemonIdentityMap.from_snapshots(
        {"pokemon": [{"species": "Flutter Mane"}]},
        {"pokemon": []},
    )
    assert identity.species("ours", 0) == "Flutter Mane"
    with pytest.raises(ValueError):
        identity.species("ours", 3)
