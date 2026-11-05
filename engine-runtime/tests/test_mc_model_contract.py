from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pokecoach_vgc_bridge.model_profile import ModelProfileError, load_vgc_model_profile


def test_trainer_package_v2_rejects_incomplete_architecture(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "model.zip").write_bytes(b"zip")
    manifest = {
        "schema_version": 2,
        "model_id": "mc-incomplete",
        "checkpoint_sha256": "a" * 64,
        "architecture": {"d_model": 256, "num_layers": 3},
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    profile_yaml = tmp_path / "vgc_model.yaml"
    profile_yaml.write_text(yaml.safe_dump({"trainer_package_dir": "package"}), encoding="utf-8")
    with pytest.raises(ModelProfileError, match="incomplète"):
        load_vgc_model_profile(profile_yaml)


def test_trainer_package_v2_requires_checkpoint_sha256(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "model.zip").write_bytes(b"zip")
    manifest = {
        "schema_version": 2,
        "model_id": "mc-no-hash",
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
    profile_yaml.write_text(yaml.safe_dump({"trainer_package_dir": "package"}), encoding="utf-8")
    with pytest.raises(ModelProfileError, match="checkpoint_sha256"):
        load_vgc_model_profile(profile_yaml)


def test_trainer_package_v1_legacy_still_loads_partial_manifest(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "model.zip").write_bytes(b"zip")
    manifest = {
        "model_id": "legacy-partial",
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
    profile_yaml.write_text(yaml.safe_dump({"trainer_package_dir": "package"}), encoding="utf-8")
    profile = load_vgc_model_profile(profile_yaml)
    assert profile.model_id == "legacy-partial"
    assert profile.architecture.num_layers == 3
