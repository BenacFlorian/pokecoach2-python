from __future__ import annotations

import os
from pathlib import Path

import pytest
from pokecoach_vgc_bridge.model_profile import (
    InferenceConfig,
    ModelArchitecture,
    VgcModelProfile,
)


def test_attach_policy_to_player_respects_deterministic_override(monkeypatch):
    profile = VgcModelProfile(
        model_id="test",
        profile_path=Path("/tmp/vgc_model.yaml"),
        checkpoint_path=Path("/tmp/final.zip"),
        architecture=ModelArchitecture(),
        inference=InferenceConfig(deterministic=True),
    )
    player = type("P", (), {"policy": None, "deterministic": None})()

    def fake_load(*_args, **_kwargs):
        return object()

    monkeypatch.setattr(
        "pokecoach_vgc_bridge.policy_factory.load_policy_from_profile",
        fake_load,
    )
    from pokecoach_vgc_bridge.policy_factory import attach_policy_to_player

    attach_policy_to_player(player, profile)
    assert player.deterministic is True
    assert player.policy is not None

    player2 = type("P", (), {"policy": None, "deterministic": None})()
    attach_policy_to_player(player2, profile, deterministic=False)
    assert player2.deterministic is False


@pytest.mark.skipif(
    not os.environ.get("POKECOACH_TEST_CHECKPOINT"),
    reason="POKECOACH_TEST_CHECKPOINT non défini",
)
def test_load_tiny_checkpoint_from_profile():
    ckpt = Path(os.environ["POKECOACH_TEST_CHECKPOINT"])
    profile = VgcModelProfile(
        model_id="test",
        profile_path=Path("/tmp/vgc_model.yaml"),
        checkpoint_path=ckpt,
        architecture=ModelArchitecture(
            d_model=128,
            num_layers=2,
            num_heads=4,
            embed_len=32,
            choose_on_teampreview=True,
        ),
    )
    from pokecoach_vgc_bridge.policy_factory import load_policy_from_profile

    policy = load_policy_from_profile(profile, device_str="cpu")
    assert policy is not None
    assert policy.choose_on_teampreview is True
