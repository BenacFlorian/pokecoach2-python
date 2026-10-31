"""Async Showdown battles via poke-env (requires vgc-bench deps + local server)."""

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


async def _run_policy_preview_battle(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
) -> dict[str, Any]:
    deps = _require_vgc_bench()
    ensure_showdown_available()
    reg = pokecoach_regulation_to_vgc_reg(regulation)
    battle_format = deps["format_map"][reg]
    port = _showdown_port_from_env()
    our_packed = snapshot_to_showdown_export(our_snapshot)
    opp_packed = snapshot_to_showdown_export(opponent_snapshot)
    server = deps["ServerConfiguration"](
        f"ws://localhost:{port}/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )
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
    await p1.battle_against(p2, n_battles=1)
    if not p1.battles:
        raise RuntimeError("BATTLE_NO_STATE: no battle recorded")
    battle = next(iter(p1.battles.values()))
    opp_lead = _lead_slots_from_battle(battle)
    our_lead = opp_lead
    from pokecoach_vgc_bridge.normalization import build_preview

    return build_preview(
        opponent_lead=opp_lead,
        our_lead=our_lead,
        engine="vgc-bench",
    )


def _lead_slots_from_battle(battle: Any) -> tuple[int, int]:
    active = getattr(battle, "active_pokemon", None) or []
    if len(active) < 2:
        raise RuntimeError("PREVIEW_INCOMPLETE: fewer than two actives after preview")
    team = list(getattr(battle, "team", {}).values())
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


def run_preview_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_run_policy_preview_battle(**kwargs))


async def run_first_turn_battle(**kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("FIRST_TURN_PENDING: turn-1 trace extraction not wired yet")


async def run_full_battle(**kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("FULL_BATTLE_PENDING: terminal battle trace not wired yet")
