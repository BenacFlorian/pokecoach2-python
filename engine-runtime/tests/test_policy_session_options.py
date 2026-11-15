from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pokecoach_vgc_bridge.inference_control import resolve_open_team_sheets
from pokecoach_vgc_bridge.model_profile import InferenceConfig, ModelArchitecture, VgcModelProfile


def _sample_profile(*, deterministic: bool = True, ots: bool = False) -> VgcModelProfile:
    return VgcModelProfile(
        model_id="test",
        profile_path=Path("/tmp/vgc_model.yaml"),
        checkpoint_path=Path("/tmp/final.zip"),
        architecture=ModelArchitecture(),
        inference=InferenceConfig(deterministic=deterministic, open_team_sheets=ots),
    )


@pytest.mark.parametrize(
    ("env", "profile_ots", "expected"),
    [
        (None, True, True),
        (None, False, False),
        ("1", False, True),
        ("false", True, False),
        (None, False, False),
    ],
)
def test_resolve_open_team_sheets_matrix(env, profile_ots, expected):
    profile = _sample_profile(ots=profile_ots)
    assert resolve_open_team_sheets(profile, env) is expected


@pytest.mark.parametrize("server_url", [
    None,
    "ws://showdown:8000/showdown/websocket",
    "wss://sim.example.test/custom/websocket",
])
def test_create_policy_pair_uses_profile_deterministic(monkeypatch, server_url):
    import asyncio
    profile = _sample_profile(deterministic=True)

    class FakePolicyPlayer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.deterministic = kwargs.get("deterministic")
            self.policy = None
            self.pokecoach_seed_stream = None
            self.ps_client = None

        def set_policy(self, *_args, **_kwargs):
            return None

    fake_deps = {
        "torch": MagicMock(device=MagicMock(return_value="cpu")),
        "PolicyPlayer": FakePolicyPlayer,
        "AccountConfiguration": lambda *a, **k: None,
        "ServerConfiguration": MagicMock(),
        "Teambuilder": MagicMock(
            join_team=lambda *a, **k: "",
            parse_showdown_team=lambda *a, **k: [],
        ),
        "format_map": {"mc": "gen9championsvgc2026regmc"},
    }

    captured: list[dict] = []

    def fake_attach(player, prof, device_str=None, **kwargs):
        captured.append({"deterministic": kwargs.get("deterministic"), "ots": kwargs.get("open_team_sheets")})
        player.policy = object()

    with (
        patch(
            "pokecoach_vgc_bridge.battle_session._require_vgc_bench",
            return_value=fake_deps,
        ),
        patch(
            "pokecoach_vgc_bridge.battle_session.ensure_showdown_available_async",
            new_callable=AsyncMock,
        ),
        patch(
            "pokecoach_vgc_bridge.model_profile.load_vgc_model_profile_from_env",
            return_value=profile,
        ),
        patch(
            "pokecoach_vgc_bridge.battle_session.snapshot_to_showdown_export",
            return_value="",
        ),
        patch(
            "pokecoach_vgc_bridge.battle_session._start_ps_listening",
        ),
        patch(
            "pokecoach_vgc_bridge.policy_factory.attach_policy_to_player",
            side_effect=fake_attach,
        ),
        patch.dict(os.environ, {}, clear=False),
    ):
        monkeypatch.delenv("POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS", raising=False)
        if server_url is None:
            monkeypatch.delenv("POKECOACH_SHOWDOWN_SERVER", raising=False)
        else:
            monkeypatch.setenv("POKECOACH_SHOWDOWN_SERVER", server_url)
        from pokecoach_vgc_bridge.battle_session import create_policy_pair

        p1, p2 = asyncio.run(
            create_policy_pair(
                checkpoint_path="/tmp/x.zip",
                our_snapshot={"teamName": "a", "slots": []},
                opponent_snapshot={"teamName": "b", "slots": []},
                regulation="M-C",
                seed=11,
            )
        )

    assert p1.deterministic is True
    assert p2.deterministic is True
    assert captured[0]["deterministic"] is True
    assert captured[1]["deterministic"] is True
    fake_deps["ServerConfiguration"].assert_called_once_with(
        server_url or "ws://127.0.0.1:8090/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )


def test_create_policy_pair_preview_override_deterministic(monkeypatch):
    import asyncio
    profile = _sample_profile(deterministic=True)
    fake_deps = {
        "torch": MagicMock(device=MagicMock(return_value="cpu")),
        "PolicyPlayer": type(
            "FP",
            (),
            {
                "__init__": lambda self, **kw: setattr(self, "deterministic", kw.get("deterministic")),
            },
        ),
        "AccountConfiguration": lambda *a, **k: None,
        "ServerConfiguration": lambda *a, **k: None,
        "Teambuilder": MagicMock(
            join_team=lambda *a, **k: "",
            parse_showdown_team=lambda *a, **k: [],
        ),
        "format_map": {"mc": "gen9championsvgc2026regmc"},
    }

    with (
        patch("pokecoach_vgc_bridge.battle_session._require_vgc_bench", return_value=fake_deps),
        patch(
            "pokecoach_vgc_bridge.battle_session.ensure_showdown_available_async",
            new_callable=AsyncMock,
        ),
        patch(
            "pokecoach_vgc_bridge.model_profile.load_vgc_model_profile_from_env",
            return_value=profile,
        ),
        patch("pokecoach_vgc_bridge.battle_session.snapshot_to_showdown_export", return_value=""),
        patch("pokecoach_vgc_bridge.battle_session._start_ps_listening"),
        patch("pokecoach_vgc_bridge.policy_factory.attach_policy_to_player"),
        patch.dict(os.environ, {}, clear=False),
    ):
        monkeypatch.delenv("POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS", raising=False)
        from pokecoach_vgc_bridge.battle_session import create_policy_pair

        p1, p2 = asyncio.run(
            create_policy_pair(
                checkpoint_path="/tmp/x.zip",
                our_snapshot={"teamName": "a", "slots": []},
                opponent_snapshot={"teamName": "b", "slots": []},
                regulation="M-C",
                seed=3,
                deterministic=False,
            )
        )

    assert p1.deterministic is False
    assert p2.deterministic is False
