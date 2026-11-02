"""Profil modèle unique (`vgc_model.yaml`) pour checkpoint + architecture."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ModelProfileError(ValueError):
    """Configuration de profil invalide ou incohérente."""


@dataclass(frozen=True)
class ModelArchitecture:
    d_model: int = 128
    num_layers: int = 2
    num_heads: int = 4
    embed_len: int = 32
    choose_on_teampreview: bool = True

    def __post_init__(self) -> None:
        if self.d_model <= 0:
            raise ModelProfileError("d_model doit être > 0")
        if self.num_layers < 1 or self.num_heads < 1 or self.embed_len < 1:
            raise ModelProfileError("num_layers, num_heads et embed_len doivent être >= 1")
        if self.d_model % self.num_heads != 0:
            raise ModelProfileError("d_model doit être divisible par num_heads")

    def policy_kwargs(self) -> dict[str, Any]:
        return {
            "d_model": self.d_model,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "embed_len": self.embed_len,
            "choose_on_teampreview": self.choose_on_teampreview,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "d_model": self.d_model,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "embed_len": self.embed_len,
            "choose_on_teampreview": self.choose_on_teampreview,
        }


@dataclass(frozen=True)
class InferenceConfig:
    device: str = "auto"
    deterministic: bool = True


@dataclass(frozen=True)
class VgcModelProfile:
    model_id: str
    profile_path: Path
    checkpoint_path: Path
    architecture: ModelArchitecture
    checkpoint_sha256: str | None = None
    trainer_package_dir: Path | None = None
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    @property
    def resolved_checkpoint_path(self) -> Path:
        return self.checkpoint_path.resolve()

    @property
    def architecture_dict(self) -> dict[str, Any]:
        return self.architecture.to_dict()

    def policy_kwargs(self) -> dict[str, Any]:
        return self.architecture.policy_kwargs()


def _resolve_path(base_dir: Path, raw: str | None) -> Path | None:
    if raw is None or not str(raw).strip():
        return None
    p = Path(str(raw).strip())
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def _architecture_from_mapping(data: dict[str, Any] | None) -> ModelArchitecture:
    data = data or {}
    return ModelArchitecture(
        d_model=int(data.get("d_model", 128)),
        num_layers=int(data.get("num_layers", 2)),
        num_heads=int(data.get("num_heads", 4)),
        embed_len=int(data.get("embed_len", 32)),
        choose_on_teampreview=bool(data.get("choose_on_teampreview", True)),
    )


def _load_trainer_package(package_dir: Path) -> tuple[Path, ModelArchitecture, str | None, str]:
    manifest_path = package_dir / "manifest.json"
    model_zip = package_dir / "model.zip"
    if not manifest_path.is_file():
        raise ModelProfileError(f"manifest Trainer absent: {manifest_path}")
    if not model_zip.is_file():
        raise ModelProfileError(f"model.zip absent: {model_zip}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    arch_raw = manifest.get("architecture") or {}
    architecture = _architecture_from_mapping(arch_raw)
    sha = manifest.get("checkpoint_sha256")
    model_id = str(manifest.get("model_id") or package_dir.parent.name)
    return model_zip.resolve(), architecture, sha, model_id


def load_vgc_model_profile(path: Path) -> VgcModelProfile:
    """Charge et normalise un profil YAML (chemins relatifs au dossier du fichier)."""

    profile_path = path.expanduser().resolve()
    if not profile_path.is_file():
        raise ModelProfileError(f"profil introuvable: {profile_path}")
    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ModelProfileError("vgc_model.yaml doit être un objet YAML")

    base_dir = profile_path.parent
    package_dir = _resolve_path(base_dir, raw.get("trainer_package_dir"))
    checkpoint_block = raw.get("checkpoint") or {}
    arch_block = raw.get("architecture")

    model_id = str(raw.get("model_id") or "model")
    checkpoint_path: Path | None = None
    architecture: ModelArchitecture | None = None
    sha256: str | None = None

    if package_dir is not None:
        if not package_dir.is_dir():
            raise ModelProfileError(f"trainer_package_dir introuvable: {package_dir}")
        ckpt, architecture, sha256, pkg_id = _load_trainer_package(package_dir)
        checkpoint_path = ckpt
        if raw.get("model_id") is None:
            model_id = pkg_id
        if arch_block:
            raise ModelProfileError(
                "ne pas mélanger trainer_package_dir et architecture explicite"
            )
        if checkpoint_block.get("path"):
            raise ModelProfileError(
                "ne pas mélanger trainer_package_dir et checkpoint.path"
            )
    else:
        ckpt_raw = checkpoint_block.get("path")
        if not ckpt_raw:
            raise ModelProfileError("checkpoint.path ou trainer_package_dir requis")
        checkpoint_path = _resolve_path(base_dir, str(ckpt_raw))
        if checkpoint_path is None or not checkpoint_path.is_file():
            raise ModelProfileError(f"checkpoint introuvable: {ckpt_raw}")
        architecture = _architecture_from_mapping(arch_block if isinstance(arch_block, dict) else {})
        sha_val = checkpoint_block.get("sha256")
        if sha_val is not None and str(sha_val).strip().lower() not in ("null", "none", ""):
            sha256 = str(sha_val).strip().lower()

    assert checkpoint_path is not None and architecture is not None

    inf_raw = raw.get("inference") or {}
    inference = InferenceConfig(
        device=str(inf_raw.get("device", "auto")),
        deterministic=bool(inf_raw.get("deterministic", True)),
    )

    return VgcModelProfile(
        model_id=model_id,
        profile_path=profile_path,
        checkpoint_path=checkpoint_path,
        architecture=architecture,
        checkpoint_sha256=sha256,
        trainer_package_dir=package_dir,
        inference=inference,
    )


def load_vgc_model_profile_from_env() -> VgcModelProfile | None:
    import os

    raw = os.environ.get("VGC_MODEL_PROFILE", "").strip()
    if not raw:
        return None
    return load_vgc_model_profile(Path(raw))
