"""Dispatch bridge modes to fixture or real VGC runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pokecoach_vgc_bridge.fixture_sim import FixtureRuntime
from pokecoach_vgc_bridge.policy import load_manifest


class BridgeRuntime:
    def __init__(self, *, checkpoint_path: str, manifest_path: str) -> None:
        self._manifest_path = manifest_path
        self._manifest = load_manifest(manifest_path)
        self._fixture_allowed = os.environ.get("POKECOACH_BRIDGE_FIXTURE") == "1"
        self._fixture = FixtureRuntime(manifest_path) if self._fixture_allowed else None
        self._real = None
        profile_path = os.environ.get("VGC_MODEL_PROFILE", "").strip()
        resolved_checkpoint = checkpoint_path.strip()
        if profile_path:
            from pokecoach_vgc_bridge.model_profile import load_vgc_model_profile

            profile = load_vgc_model_profile(Path(profile_path))
            resolved_checkpoint = str(profile.resolved_checkpoint_path)
            if profile.checkpoint_sha256:
                os.environ.setdefault(
                    "POKECOACH_CHECKPOINT_SHA256", profile.checkpoint_sha256
                )
        self._checkpoint_path = resolved_checkpoint
        if self._checkpoint_path and not self._fixture_allowed:
            from pokecoach_vgc_bridge import vgc_real

            self._real = vgc_real.try_load(self._checkpoint_path, manifest_path)

    def handle(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        if mode == "hello":
            if self._real is not None:
                return self._real.hello()
            if self._fixture is not None:
                return self._fixture.hello()
            return {
                "engine": "vgc-bridge",
                "protocolVersion": 1,
                "supportedModes": ["hello", "shutdown"],
                "manifest": self._manifest,
                "checkpointLoaded": False,
                "stochastic": True,
                "normalizerVersion": self._manifest.get("normalizerVersion", 1),
                "traceVersion": 1,
            }
        if self._real is not None:
            return self._real.handle(mode, payload)
        if self._fixture is not None:
            dispatch = {
                "preflight": self._fixture.preflight,
                "preview": self._fixture.preview,
                "first_turn": self._fixture.first_turn,
                "full_battle": self._fixture.full_battle,
            }
            fn = dispatch.get(mode)
            if fn is None:
                raise ValueError(f"unsupported mode {mode}")
            return fn(payload)
        if mode == "preflight":
            raise RuntimeError("CHECKPOINT_UNAVAILABLE: configure VGC_CHECKPOINT_PATH")
        raise RuntimeError("CHECKPOINT_UNAVAILABLE: real engine not loaded")
