"""Optional VGC-Bench / PyTorch integration (installed in engine-runtime venv)."""

from __future__ import annotations

import os
from typing import Any

from pokecoach_vgc_bridge.checkpoint import fingerprint_from_path, verify_checkpoint
from pokecoach_vgc_bridge.policy import load_manifest
from pokecoach_vgc_bridge.showdown_teams import pokecoach_regulation_to_vgc_reg, snapshot_to_showdown_export


def try_load(checkpoint_path: str, manifest_path: str) -> RealRuntime | None:
    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        return None
    try:
        return RealRuntime(checkpoint_path, manifest_path)
    except Exception:
        return None


class RealRuntime:
    """Loads BC checkpoint and drives Showdown via poke-env + vgc-bench."""

    def __init__(self, checkpoint_path: str, manifest_path: str) -> None:
        self._checkpoint_path = checkpoint_path
        self._manifest = load_manifest(manifest_path)
        expected = os.environ.get("POKECOACH_CHECKPOINT_SHA256") or None
        self._fingerprint = verify_checkpoint(checkpoint_path, expected)
        self._device_note = "cpu"

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
            "checkpointFingerprint": self._fingerprint[:16],
            "stochastic": True,
            "normalizerVersion": self._manifest.get("normalizerVersion", 1),
            "traceVersion": 1,
        }

    def handle(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        if mode == "preflight":
            return self._preflight(payload)
        if mode == "preview":
            return self._preview(payload)
        if mode == "first_turn":
            return self._first_turn(payload)
        if mode == "full_battle":
            return self._full_battle(payload)
        raise ValueError(f"unsupported mode {mode}")

    def _preflight(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = payload.get("config") or {}
        regulation = str(config.get("regulation", ""))
        our = payload.get("ourSnapshot")
        opp = payload.get("opponentSnapshot")
        if not isinstance(our, dict) or not isinstance(opp, dict):
            raise ValueError("ourSnapshot and opponentSnapshot required")
        snapshot_to_showdown_export(our)
        snapshot_to_showdown_export(opp)
        reg_key = pokecoach_regulation_to_vgc_reg(regulation)
        return {
            "regulation": regulation,
            "checkpointId": str(config.get("checkpoint_id", "")),
            "checkpointFingerprint": self._fingerprint[:16],
            "showdownFormat": _format_for_reg(payload, reg_key),
            "supportsPreview": True,
            "supportsFirstTurn": False,
            "supportsFullBattle": False,
            "stochastic": True,
            "pythonVersion": _python_version(),
            "notes": (
                f"checkpoint sha256={self._fingerprint[:16]}…",
                "first_turn/full_battle wiring in progress",
            ),
        }

    def _preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        from pokecoach_vgc_bridge.battle_runner import run_preview_sync

        regulation = str(payload.get("regulation", "M-B"))
        seed = int(payload.get("seed", 0))
        our = payload["ourSnapshot"]
        opp = payload["opponentSnapshot"]
        result = run_preview_sync(
            checkpoint_path=self._checkpoint_path,
            our_snapshot=our,
            opponent_snapshot=opp,
            regulation=regulation,
            seed=seed,
        )
        meta = dict(result.get("meta") or {})
        meta["engineFingerprint"] = self._fingerprint[:16]
        result["meta"] = meta
        return result

    def _first_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("FIRST_TURN_PENDING: turn-1 trace extraction not wired yet")

    def _full_battle(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("FULL_BATTLE_PENDING: terminal battle trace not wired yet")


def _python_version() -> str:
    import sys

    return sys.version.split()[0]


def _format_for_reg(payload: dict[str, Any], reg_key: str) -> str:
    mapping_raw = payload.get("regulationShowdownMap")
    if isinstance(mapping_raw, str):
        import json

        mapping = json.loads(mapping_raw)
    elif isinstance(mapping_raw, dict):
        mapping = mapping_raw
    else:
        mapping = {}
    for label, fmt in mapping.items():
        try:
            if pokecoach_regulation_to_vgc_reg(str(label)) == reg_key:
                return str(fmt)
        except ValueError:
            continue
    defaults = {"mb": "gen9championsvgc2026regmb", "ma": "gen9championsvgc2026regma"}
    return defaults.get(reg_key, reg_key)
