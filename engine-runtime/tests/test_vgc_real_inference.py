from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pokecoach_vgc_bridge.model_profile import InferenceConfig, ModelArchitecture, VgcModelProfile
from pokecoach_vgc_bridge.vgc_real import RealRuntime


def test_hello_exposes_inference_observability(tmp_path: Path):
    ckpt = tmp_path / "c.zip"
    ckpt.write_bytes(b"zip")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"normalizerVersion": 1}', encoding="utf-8")
    profile = VgcModelProfile(
        model_id="obs",
        profile_path=tmp_path / "p.yaml",
        checkpoint_path=ckpt,
        architecture=ModelArchitecture(),
        inference=InferenceConfig(deterministic=True, open_team_sheets=True),
    )
    with (
        patch("pokecoach_vgc_bridge.vgc_real.verify_checkpoint", return_value="a" * 64),
        patch.dict("os.environ", {}, clear=True),
    ):
        runtime = RealRuntime(str(ckpt), str(manifest), model_profile=profile)
        payload = runtime.hello()
    assert payload["stochastic"] is True
    assert payload["profileDeterministic"] is True
    assert payload["previewDeterministic"] is False
    assert payload["openTeamSheets"] is True
