from __future__ import annotations

import os
from pathlib import Path

import pytest
from pokecoach_vgc_bridge.model_profile import ModelArchitecture, VgcModelProfile


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
