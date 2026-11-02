"""Instanciation policy VGC-Bench alignée sur le profil modèle."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from pokecoach_vgc_bridge.checkpoint import verify_checkpoint
from pokecoach_vgc_bridge.model_profile import ModelProfileError, VgcModelProfile
from pokecoach_vgc_bridge.vgc_source import prepare_vgc_bench_source


class ModelLoadError(RuntimeError):
    """Échec de chargement checkpoint / architecture."""


def resolve_inference_device(requested: str) -> str:
    import torch

    if requested != "auto":
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise ModelLoadError(f"device demandé indisponible: {requested}")
        return requested
    if torch.cuda.is_available():
        major, minor = torch.cuda.get_device_capability(0)
        if (major, minor) < (7, 5):
            return "cpu"
        return "cuda:0"
    return "cpu"


def load_policy_from_profile(profile: VgcModelProfile, device_str: str | None = None):
    """Retourne une ``MaskedActorCriticPolicy`` prête pour l'inférence."""

    import os

    root = prepare_vgc_bench_source()
    previous = os.getcwd()
    os.chdir(root)
    try:
        return _load_policy_from_profile_cwd(profile, device_str)
    finally:
        os.chdir(previous)


def _load_policy_from_profile_cwd(profile: VgcModelProfile, device_str: str | None = None):
    ckpt = profile.resolved_checkpoint_path
    if not ckpt.is_file():
        raise ModelLoadError(f"checkpoint introuvable: {ckpt}")

    expected = profile.checkpoint_sha256
    env_sha = __import__("os").environ.get("POKECOACH_CHECKPOINT_SHA256")
    if env_sha and not expected:
        expected = env_sha
    digest = verify_checkpoint(str(ckpt), expected)

    device_name = resolve_inference_device(device_str or profile.inference.device)
    import torch

    torch_device = torch.device(device_name)

    from poke_env.player import RandomPlayer
    from stable_baselines3 import PPO
    from vgc_bench.src.env import ShowdownEnv
    from vgc_bench.src.policy import MaskedActorCriticPolicy
    from vgc_bench.src.utils import format_map, set_global_seed

    set_global_seed(42)
    kwargs = profile.policy_kwargs()
    env = ShowdownEnv(
        battle_format=format_map["mb"],
        log_level=40,
        accept_open_team_sheet=True,
        start_listening=False,
        choose_on_teampreview=kwargs["choose_on_teampreview"],
    )
    opponent = RandomPlayer(start_listening=False)
    from poke_env.environment import SingleAgentWrapper

    wrapped = SingleAgentWrapper(env, opponent)
    ppo = PPO(
        MaskedActorCriticPolicy,
        wrapped,
        policy_kwargs=kwargs,
        device=device_name,
        n_steps=256,
        batch_size=64,
    )
    policy = ppo.policy

    try:
        loaded = PPO.load(str(ckpt), device=torch_device, print_system_info=False)
        if loaded.policy.__class__ != MaskedActorCriticPolicy:
            raise ModelLoadError("checkpoint SB3 inattendu (policy)")
        policy.load_state_dict(loaded.policy.state_dict())
    except Exception as exc:
        try:
            with zipfile.ZipFile(ckpt, "r") as zf:
                with zf.open("policy.pth") as f:
                    state_dict = torch.load(
                        io.BytesIO(f.read()), map_location=torch_device, weights_only=True
                    )
            policy.load_state_dict(state_dict)
        except Exception as inner:
            raise ModelLoadError(
                f"chargement checkpoint échoué (sha256={digest[:16]}…): {exc}; {inner}"
            ) from inner

    if bool(getattr(policy, "choose_on_teampreview", False)) != kwargs["choose_on_teampreview"]:
        raise ModelLoadError("choose_on_teampreview incohérent entre profil et policy")

    policy.to(torch_device)
    policy.eval()
    return policy


def attach_policy_to_player(player, profile: VgcModelProfile, device_str: str | None = None) -> None:
    policy = load_policy_from_profile(profile, device_str)
    player.policy = policy
