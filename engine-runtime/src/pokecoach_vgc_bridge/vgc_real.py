"""Optional VGC-Bench / PyTorch integration (installed in engine-runtime venv)."""

from __future__ import annotations

from typing import Any


def try_load(checkpoint_path: str, manifest_path: str) -> RealRuntime | None:
    import os

    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        return None
    try:
        import torch  # noqa: F401
    except ImportError:
        return None
    # Real BC + Showdown wiring lands in a follow-up once vgc-bench is installed in engine-runtime.
    return None


class RealRuntime:
    """Loads BC checkpoint and drives Showdown (filled when deps are installed)."""

    def __init__(self, checkpoint_path: str, manifest_path: str) -> None:
        from pokecoach_vgc_bridge.policy import load_manifest

        self._checkpoint_path = checkpoint_path
        self._manifest = load_manifest(manifest_path)
        raise RuntimeError(
            "VGC-Bench real runtime not yet wired in this checkout; "
            "install pinned vgc-bench in engine-runtime and implement policy_player hook"
        )

    def hello(self) -> dict[str, Any]:
        return {
            "engine": "vgc-bench",
            "protocolVersion": 1,
            "supportedModes": [
                "hello",
                "preflight",
                "preview",
                "first_turn",
                "full_battle",
                "shutdown",
            ],
            "manifest": self._manifest,
            "checkpointLoaded": True,
            "stochastic": True,
        }

    def handle(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"real mode {mode} not implemented")
