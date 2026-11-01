"""Tests for Showdown move target catalog and resolver."""

from __future__ import annotations

import pytest

from pokecoach_vgc_bridge.move_targets import (
    build_action_targets,
    load_move_catalog,
    resolve_move_target,
    to_move_id,
)


@pytest.fixture(scope="module")
def catalog():
    return load_move_catalog("gen9championsvgc2026regma")


@pytest.mark.parametrize(
    ("target", "sample_id"),
    [
        ("normal", "tackle"),
        ("adjacentFoe", "doodle"),
        ("adjacentAlly", "helpinghand"),
        ("adjacentAllyOrSelf", "acupressure"),
        ("any", "acrobatics"),
        ("self", "protect"),
        ("allAdjacent", "earthquake"),
        ("allAdjacentFoes", "rockslide"),
        ("allies", "lifedew"),
        ("allySide", "tailwind"),
        ("allyTeam", "aromatherapy"),
        ("foeSide", "stickyweb"),
        ("all", "perishsong"),
        ("randomNormal", "outrage"),
        ("scripted", "counter"),
    ],
)
def test_catalog_covers_showdown_target_enum(target: str, sample_id: str, catalog) -> None:
    info = resolve_move_target(sample_id, catalog)
    assert info.target_type == target
    assert info.target_source == "dex"


def test_resolve_unknown_move(catalog) -> None:
    info = resolve_move_target("Not A Real Move 9000", catalog)
    assert info.target_type is None
    assert info.target_source == "unknown"


def test_request_target_overrides_dex(catalog) -> None:
    info = resolve_move_target("tailwind", catalog, request_target="foeSide")
    assert info.target_type == "foeSide"
    assert info.target_source == "request"


def test_tailwind_zone_target(catalog) -> None:
    info = resolve_move_target("Tailwind", catalog)
    targets = build_action_targets(
        info,
        actor_side="ours",
        actor_slot=0,
        target_side="opponent",
        target_roster_slot=2,
    )
    assert info.target_type == "allySide"
    assert targets == [{"kind": "zone", "zone": "allySide"}]


def test_protect_self_individual(catalog) -> None:
    info = resolve_move_target("Protect", catalog)
    targets = build_action_targets(
        info,
        actor_side="ours",
        actor_slot=1,
        target_side="opponent",
        target_roster_slot=None,
    )
    assert info.target_type == "self"
    assert targets[0]["ref"]["slot"] == 1


def test_two_catalog_formats_do_not_share_cache_entry() -> None:
    a = load_move_catalog("gen9championsvgc2026regma")
    b = load_move_catalog("gen9championsvgc2026regmb")
    assert a.battle_format != b.battle_format or a.fingerprint == b.fingerprint


def test_move_id_aliases() -> None:
    assert to_move_id("Fake Out") == "fakeout"
    assert to_move_id("Make It Rain") == "makeitrain"
