"""Shared battle session helpers for policy vs policy Showdown runs."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlparse

from pokecoach_vgc_bridge.showdown_teams import pokecoach_regulation_to_vgc_reg, snapshot_to_showdown_export


def _showdown_port_from_env() -> int:
    url = os.environ.get("POKECOACH_SHOWDOWN_SERVER", "ws://127.0.0.1:8090/showdown/websocket")
    parsed = urlparse(url.replace("ws://", "http://").replace("wss://", "https://"))
    return parsed.port or 8090


async def _probe_showdown(timeout: float = 2.0) -> None:
    import websockets

    url = os.environ.get("POKECOACH_SHOWDOWN_SERVER", "ws://127.0.0.1:8090/showdown/websocket")
    async with asyncio.timeout(timeout):
        async with websockets.connect(url):
            return


def ensure_showdown_available() -> None:
    try:
        asyncio.run(_probe_showdown())
    except Exception as exc:
        raise RuntimeError(
            f"SHOWDOWN_UNAVAILABLE: cannot reach local Showdown ({exc})"
        ) from exc


def vgc_deps_available() -> bool:
    try:
        _require_vgc_bench()
        return True
    except RuntimeError:
        return False


def _require_vgc_bench() -> dict[str, Any]:
    try:
        import torch
        from poke_env.ps_client import AccountConfiguration, ServerConfiguration
        from poke_env.teambuilder import Teambuilder
        from vgc_bench.src.policy_player import PolicyPlayer
        from vgc_bench.src.utils import format_map
    except ImportError as exc:
        raise RuntimeError(
            "VGC_BENCH_DEPS: install vgc-bench in engine-runtime (see docs/recettes/moteur-reel.md)"
        ) from exc
    return {
        "torch": torch,
        "PolicyPlayer": PolicyPlayer,
        "AccountConfiguration": AccountConfiguration,
        "ServerConfiguration": ServerConfiguration,
        "Teambuilder": Teambuilder,
        "format_map": format_map,
    }


def _static_builder(Teambuilder: type, packed: str):
    class StaticTeam(Teambuilder):  # type: ignore[misc, valid-type]
        def yield_team(self):
            yield packed

    return StaticTeam()


async def create_policy_pair(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
) -> tuple[Any, Any]:
    deps = _require_vgc_bench()
    ensure_showdown_available()
    reg = pokecoach_regulation_to_vgc_reg(regulation)
    battle_format = deps["format_map"][reg]
    port = _showdown_port_from_env()
    server = deps["ServerConfiguration"](
        f"ws://localhost:{port}/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )
    our_packed = snapshot_to_showdown_export(our_snapshot)
    opp_packed = snapshot_to_showdown_export(opponent_snapshot)
    p1 = deps["PolicyPlayer"](
        account_configuration=deps["AccountConfiguration"](f"P1-{seed}", None),
        battle_format=battle_format,
        server_configuration=server,
        team=_static_builder(deps["Teambuilder"], our_packed),
        max_concurrent_battles=1,
        log_level=40,
        accept_open_team_sheet=True,
    )
    p2 = deps["PolicyPlayer"](
        account_configuration=deps["AccountConfiguration"](f"P2-{seed}", None),
        battle_format=battle_format,
        server_configuration=server,
        team=_static_builder(deps["Teambuilder"], opp_packed),
        max_concurrent_battles=1,
        log_level=40,
        accept_open_team_sheet=True,
    )
    device = deps["torch"].device("cpu")
    p1.set_policy(checkpoint_path, device)
    p2.set_policy(checkpoint_path, device)
    return p1, p2


def _lead_slots_from_battle(battle: Any, *, team_attr: str = "team") -> tuple[int, int]:
    active = getattr(battle, "active_pokemon", None) or []
    if len(active) < 2:
        raise RuntimeError("PREVIEW_INCOMPLETE: fewer than two actives after preview")
    team = list(getattr(battle, team_attr, {}).values())
    slots: list[int] = []
    for mon in active[:2]:
        for idx, candidate in enumerate(team):
            if candidate is mon:
                slots.append(idx)
                break
        else:
            raise RuntimeError("PREVIEW_SLOT_MAP: active not in team")
    a, b = slots[0], slots[1]
    return (a, b) if a < b else (b, a)
