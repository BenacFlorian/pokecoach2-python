"""Shared battle session helpers for policy vs policy Showdown runs."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any
from urllib.parse import urlparse

from pokecoach_vgc_bridge.showdown_teams import (
    pokecoach_regulation_to_vgc_reg,
    snapshot_to_showdown_export,
)
from pokecoach_vgc_bridge.vgc_source import prepare_vgc_bench_source


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


async def ensure_showdown_available_async() -> None:
    try:
        await _probe_showdown()
    except Exception as exc:
        raise RuntimeError(
            f"SHOWDOWN_UNAVAILABLE: cannot reach local Showdown ({exc})"
        ) from exc


def ensure_showdown_available() -> None:
    """Probe Showdown from synchronous bridge code only (no running event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(_probe_showdown())
        except Exception as exc:
            raise RuntimeError(
                f"SHOWDOWN_UNAVAILABLE: cannot reach local Showdown ({exc})"
            ) from exc
        return
    raise RuntimeError(
        "ensure_showdown_available() cannot run inside asyncio; "
        "use ensure_showdown_available_async()"
    )


def vgc_deps_available() -> bool:
    try:
        _require_vgc_bench()
        return True
    except RuntimeError:
        return False


def _require_vgc_bench() -> dict[str, Any]:
    try:
        prepare_vgc_bench_source()
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


def _static_builder(Teambuilder: type, showdown_export: str):
    packed = Teambuilder.join_team(Teambuilder.parse_showdown_team(showdown_export))

    class StaticTeam(Teambuilder):  # type: ignore[misc, valid-type]
        def yield_team(self):
            return packed

    return StaticTeam()


def _validate_lead_slots(lead: tuple[int, int]) -> tuple[int, int]:
    a, b = lead
    if a == b or not (0 <= a <= 5 and 0 <= b <= 5):
        raise ValueError(f"invalid lead slots {lead}")
    return (a, b)


def _preview_slots_from_team_command(choice: str) -> tuple[int, ...] | None:
    if not isinstance(choice, str) or not choice.startswith("/team "):
        return None
    digits = choice.removeprefix("/team ").strip()
    if len(digits) != 4 or not digits.isdigit():
        return None
    slots = tuple(int(char) - 1 for char in digits)
    if len(set(slots)) != 4:
        return None
    return slots


def _start_ps_listening(player: Any) -> None:
    client = getattr(player, "ps_client", None)
    if client is None or getattr(client, "_listening_coroutine", None) is not None:
        return
    client._listening_coroutine = asyncio.run_coroutine_threadsafe(
        client.listen(),
        client.loop,
    )


async def create_policy_pair(
    *,
    checkpoint_path: str,
    our_snapshot: dict[str, Any],
    opponent_snapshot: dict[str, Any],
    regulation: str,
    seed: int,
    our_imposed_lead: tuple[int, int] | None = None,
    opponent_imposed_lead: tuple[int, int] | None = None,
) -> tuple[Any, Any]:
    deps = _require_vgc_bench()
    await ensure_showdown_available_async()
    reg = pokecoach_regulation_to_vgc_reg(regulation)
    battle_format = deps["format_map"][reg]
    port = _showdown_port_from_env()
    server = deps["ServerConfiguration"](
        f"ws://localhost:{port}/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )
    our_packed = snapshot_to_showdown_export(our_snapshot)
    opp_packed = snapshot_to_showdown_export(opponent_snapshot)
    session_id = uuid.uuid4().hex[:10]
    accept_ots = os.environ.get("POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS", "0") == "1"

    class RecordingPolicyPlayer(deps["PolicyPlayer"]):
        def teampreview(self, battle: Any):
            imposed = getattr(self, "pokecoach_imposed_lead", None)
            if imposed is None:
                choice = super().teampreview(battle)
            else:
                choice = _teampreview_with_imposed_lead(self, battle, imposed)
            slots = _preview_slots_from_team_command(choice)
            if slots is not None:
                self.pokecoach_preview_slots = slots
            return choice

    p1 = RecordingPolicyPlayer(
        account_configuration=deps["AccountConfiguration"](
            f"Pc1{seed}{session_id}"[:18],
            None,
        ),
        battle_format=battle_format,
        server_configuration=server,
        team=_static_builder(deps["Teambuilder"], our_packed),
        max_concurrent_battles=1,
        log_level=40,
        start_listening=False,
        accept_open_team_sheet=accept_ots,
    )
    p2 = RecordingPolicyPlayer(
        account_configuration=deps["AccountConfiguration"](
            f"Pc2{seed}{session_id}"[:18],
            None,
        ),
        battle_format=battle_format,
        server_configuration=server,
        team=_static_builder(deps["Teambuilder"], opp_packed),
        max_concurrent_battles=1,
        log_level=40,
        start_listening=False,
        accept_open_team_sheet=accept_ots,
    )
    device = deps["torch"].device("cpu")
    p1.set_policy(checkpoint_path, device)
    p2.set_policy(checkpoint_path, device)
    p1.pokecoach_imposed_lead = (
        _validate_lead_slots(our_imposed_lead) if our_imposed_lead is not None else None
    )
    p2.pokecoach_imposed_lead = (
        _validate_lead_slots(opponent_imposed_lead)
        if opponent_imposed_lead is not None
        else None
    )
    _start_ps_listening(p1)
    _start_ps_listening(p2)
    return p1, p2


def _teampreview_with_imposed_lead(
    player: Any,
    battle: Any,
    imposed_lead: tuple[int, int],
) -> str:
    """Fix lead slots in /team; second policy pick chooses the back pair."""
    from poke_env.battle import DoubleBattle
    from poke_env.environment import DoublesEnv

    lead_a, lead_b = _validate_lead_slots(imposed_lead)
    if not isinstance(battle, DoubleBattle):
        raise RuntimeError("IMPOSED_LEAD_REQUIRES_DOUBLE_BATTLE")
    policy = player.policy
    if policy is None:
        raise RuntimeError("IMPOSED_LEAD_REQUIRES_POLICY")
    if not getattr(policy, "choose_on_teampreview", False):
        raise RuntimeError(
            "IMPOSED_LEAD_REQUIRES_CHOOSE_ON_TEAMPREVIEW: enable policy teampreview in checkpoint"
        )
    team = list(battle.team.values())
    team[lead_a]._selected_in_teampreview = True
    team[lead_b]._selected_in_teampreview = True
    order2 = player.choose_move(battle)
    if asyncio.iscoroutine(order2):
        raise RuntimeError("async choose_move not supported for imposed teampreview")
    action2 = DoublesEnv.order_to_action(order2, battle)
    team[action2[0] - 1]._selected_in_teampreview = True
    team[action2[1] - 1]._selected_in_teampreview = True
    return f"/team {lead_a + 1}{lead_b + 1}{action2[0]}{action2[1]}"


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
            mon_name = getattr(mon, "species", None) or getattr(mon, "name", None)
            for idx, candidate in enumerate(team):
                cand_name = getattr(candidate, "species", None) or getattr(
                    candidate, "name", None
                )
                if mon_name and mon_name == cand_name:
                    slots.append(idx)
                    break
            else:
                raise RuntimeError("PREVIEW_SLOT_MAP: active not in team")
    a, b = slots[0], slots[1]
    return (a, b) if a < b else (b, a)
