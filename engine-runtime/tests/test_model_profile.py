from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pokecoach_vgc_bridge.model_profile import ModelProfileError, load_vgc_model_profile


def test_load_minimal_profile_resolves_relative_checkpoint(tmp_path: Path):
    ckpt = tmp_path / "models" / "final.zip"
    ckpt.parent.mkdir()
    ckpt.write_bytes(b"fake")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(
        yaml.safe_dump(
            {
                "model_id": "test-model",
                "checkpoint": {"path": "models/final.zip"},
                "architecture": {
                    "d_model": 128,
                    "num_layers": 2,
                    "num_heads": 4,
                    "embed_len": 32,
                    "choose_on_teampreview": True,
                },
            }
        ),
        encoding="utf-8",
    )
    profile = load_vgc_model_profile(profile_yaml)
    assert profile.model_id == "test-model"
    assert profile.resolved_checkpoint_path == ckpt.resolve()
    assert profile.architecture.d_model == 128


def test_invalid_heads_rejected(tmp_path: Path):
    ckpt = tmp_path / "x.zip"
    ckpt.write_bytes(b"fake")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(
        yaml.safe_dump(
            {
                "checkpoint": {"path": "x.zip"},
                "architecture": {"d_model": 128, "num_heads": 3},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelProfileError, match="divisible"):
        load_vgc_model_profile(profile_yaml)


def test_inference_options_loaded_from_profile(tmp_path: Path):
    ckpt = tmp_path / "x.zip"
    ckpt.write_bytes(b"fake")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(
        yaml.safe_dump(
            {
                "checkpoint": {"path": "x.zip"},
                "architecture": {"d_model": 128, "num_heads": 4, "num_layers": 2},
                "inference": {
                    "device": "cpu",
                    "deterministic": False,
                    "open_team_sheets": True,
                },
            }
        ),
        encoding="utf-8",
    )
    profile = load_vgc_model_profile(profile_yaml)
    assert profile.inference.device == "cpu"
    assert profile.inference.deterministic is False
    assert profile.inference.open_team_sheets is True


def test_legacy_profile_defaults_open_team_sheets_to_false(tmp_path: Path):
    ckpt = tmp_path / "x.zip"
    ckpt.write_bytes(b"fake")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(
        yaml.safe_dump(
            {
                "checkpoint": {"path": "x.zip"},
                "architecture": {"d_model": 128, "num_heads": 4, "num_layers": 2},
            }
        ),
        encoding="utf-8",
    )
    profile = load_vgc_model_profile(profile_yaml)
    assert profile.inference.open_team_sheets is False


def test_trainer_package_dir_loads_manifest(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "model.zip").write_bytes(b"zip")
    manifest = {
        "model_id": "from-manifest",
        "checkpoint_sha256": "abc",
        "architecture": {
            "d_model": 256,
            "num_layers": 3,
            "num_heads": 4,
            "embed_len": 32,
            "choose_on_teampreview": True,
        },
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(
        yaml.safe_dump({"trainer_package_dir": "package"}),
        encoding="utf-8",
    )
    profile = load_vgc_model_profile(profile_yaml)
    assert profile.model_id == "from-manifest"
    assert profile.architecture.num_layers == 3
    assert profile.resolved_checkpoint_path == (package / "model.zip").resolve()
    assert profile.checkpoint_sha256 == "abc"
