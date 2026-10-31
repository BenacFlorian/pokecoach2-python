"""Deterministic Showdown-shaped simulation for protocol tests (not production stub)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pokecoach_vgc_bridge.normalization import (
    TRACE_VERSION,
    build_battle_record,
    build_preview,
    build_turn_one,
)
from pokecoach_vgc_bridge.policy import load_manifest


class FixtureRuntime:
    """Legal-ish decisions derived from snapshots and seed (fixture / CI only)."""

    def __init__(self, manifest_path: str) -> None:
        self._manifest = load_manifest(manifest_path)

    def hello(self) -> dict[str, Any]:
        return {
            "engine": "fixture-bridge",
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
            "checkpointLoaded": False,
            "stochastic": True,
            "normalizerVersion": self._manifest.get("normalizerVersion", 1),
            "traceVersion": TRACE_VERSION,
        }

    def preflight(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = payload.get("config") or {}
        regulation = str(config.get("regulation", ""))
        _require_snapshots(payload)
        showdown = _showdown_format(payload, regulation)
        return {
            "regulation": regulation,
            "checkpointId": str(config.get("checkpoint_id", "fixture")),
            "checkpointFingerprint": "fixture",
            "showdownFormat": showdown,
            "supportsPreview": True,
            "supportsFirstTurn": True,
            "supportsFullBattle": True,
            "stochastic": True,
            "pythonVersion": _python_version(),
            "notes": ("fixture bridge — not BC weights",),
        }

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        seed = int(payload["seed"])
        our, opp = _snapshots(payload)
        digest = _digest(f"preview:{seed}", our, opp)
        opp_lead = _pick_pair(digest, 0)
        our_lead = _pick_pair(digest, 2)
        return build_preview(opponent_lead=opp_lead, our_lead=our_lead, engine="fixture-bridge")

    def first_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        seed = int(payload["seed"])
        our, opp = _snapshots(payload)
        lead = payload.get("opponentLead")
        if not lead or len(lead) != 2:
            raise ValueError("opponentLead required")
        opp_lead = (int(lead[0]), int(lead[1]))
        if opp_lead[0] == opp_lead[1]:
            raise ValueError("invalid opponentLead")
        our_lead_raw = payload.get("ourLeadSlots")
        if our_lead_raw and len(our_lead_raw) == 2:
            our_lead = (int(our_lead_raw[0]), int(our_lead_raw[1]))
        else:
            digest = _digest(f"preview:{seed}", our, opp)
            our_lead = _pick_pair(digest, 2)
        digest = _digest(f"first-turn:{seed}:{opp_lead}", our, opp)
        if digest[0] == 255:
            raise ValueError("simulated preview rejection")
        back_pair = _back_pair(opp_lead, digest[3])
        actions = _opponent_turn1_actions(opp, opp_lead, digest)
        return build_turn_one(
            opponent_lead=opp_lead,
            our_lead=our_lead,
            actions=actions,
            back_pair=back_pair,
            engine="fixture-bridge",
        )

    def full_battle(self, payload: dict[str, Any]) -> dict[str, Any]:
        seed = int(payload["seed"])
        our, opp = _snapshots(payload)
        lead = payload.get("opponentLead")
        if not lead:
            raise ValueError("opponentLead required")
        opp_lead = (int(lead[0]), int(lead[1]))
        digest = _digest(f"full:{seed}:{opp_lead}", our, opp)
        if digest[0] == 0:
            raise ValueError("simulated battle rejection")
        our_four, our_lead = _resolve_our_lineup(payload, seed, our)
        outcome_roll = digest[8] % 10
        if outcome_roll == 0:
            outcome: Literal["win", "loss", "draw"] = "draw"
        elif outcome_roll <= 5:
            outcome = "win"
        else:
            outcome = "loss"
        our_actions = _our_turn1_actions(our, our_lead, digest)
        opp_actions = _opponent_turn1_actions(opp, opp_lead, digest)
        return build_battle_record(
            opponent_lead=opp_lead,
            our_lead=our_lead,
            our_four=our_four,
            our_actions=our_actions,
            opponent_actions=opp_actions,
            outcome=outcome,
            seed=seed,
            engine="fixture-bridge",
            payload=payload,
        )


def _python_version() -> str:
    import sys

    return sys.version.split()[0]


def _require_snapshots(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    our = payload.get("ourSnapshot")
    opp = payload.get("opponentSnapshot")
    if not isinstance(our, dict) or not isinstance(opp, dict):
        raise ValueError("ourSnapshot and opponentSnapshot required")
    if not our.get("pokemon") or not opp.get("pokemon"):
        raise ValueError("snapshots require non-empty pokemon arrays")
    return our, opp


def _snapshots(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _require_snapshots(payload)


def _showdown_format(payload: dict[str, Any], regulation: str) -> str:
    mapping_raw = payload.get("regulationShowdownMap")
    if isinstance(mapping_raw, str):
        mapping = json.loads(mapping_raw)
    elif isinstance(mapping_raw, dict):
        mapping = mapping_raw
    else:
        mapping = {"M-B": "gen9vgc2024regf"}
    fmt = mapping.get(regulation)
    if not isinstance(fmt, str):
        raise ValueError(f"unmapped regulation {regulation!r}")
    return fmt


def _digest(prefix: str, our: dict[str, Any], opp: dict[str, Any]) -> bytes:
    blob = json.dumps(
        {"p": prefix, "our": our.get("pokemon"), "opp": opp.get("pokemon")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).digest()


def _pick_pair(digest: bytes, offset: int) -> tuple[int, int]:
    a = digest[offset] % 6
    b = (digest[offset + 1] + 1) % 6
    if a == b:
        b = (b + 1) % 6
    return (a, b) if a < b else (b, a)


def _back_pair(lead: tuple[int, int], roll: int) -> tuple[int, int]:
    pool = [s for s in range(6) if s not in lead]
    idx = roll % max(1, len(pool) - 1)
    pair = sorted((pool[idx], pool[(idx + 1) % len(pool)]))
    return (pair[0], pair[1])


def _move_name(snapshot: dict[str, Any], slot: int, move_idx: int) -> str:
    mons = snapshot.get("pokemon") or []
    if slot >= len(mons):
        return "Struggle"
    mon = mons[slot]
    moves = mon.get("moves")
    if isinstance(moves, list) and moves:
        name = moves[move_idx % len(moves)]
        if isinstance(name, str):
            return name
        if isinstance(name, dict) and isinstance(name.get("name"), str):
            return name["name"]
    for key in ("move1", "move2", "move3", "move4"):
        val = mon.get(key)
        if isinstance(val, str):
            return val
    return "Tackle"


def _opponent_turn1_actions(
    opp: dict[str, Any],
    lead: tuple[int, int],
    digest: bytes,
) -> list[dict[str, Any]]:
    slot_a, slot_b = lead
    return [
        {
            "kind": "move",
            "actor": {"side": "opponent", "slot": slot_a},
            "move": _move_name(opp, slot_a, digest[1]),
            "targets": [
                {
                    "kind": "pokemon",
                    "ref": {"side": "ours", "slot": digest[2] % 6},
                }
            ],
        },
        {
            "kind": "move",
            "actor": {"side": "opponent", "slot": slot_b},
            "move": _move_name(opp, slot_b, digest[3]),
            "targets": [
                {
                    "kind": "pokemon",
                    "ref": {"side": "ours", "slot": digest[4] % 6},
                }
            ],
        },
    ]


def _our_turn1_actions(
    our: dict[str, Any],
    lead: tuple[int, int],
    digest: bytes,
) -> list[dict[str, Any]]:
    slot_a, slot_b = lead
    return [
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": slot_a},
            "move": _move_name(our, slot_a, digest[5]),
            "targets": [
                {
                    "kind": "pokemon",
                    "ref": {"side": "opponent", "slot": digest[6] % 6},
                }
            ],
        },
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": slot_b},
            "move": _move_name(our, slot_b, digest[7]),
            "targets": [
                {
                    "kind": "pokemon",
                    "ref": {"side": "opponent", "slot": digest[8] % 6},
                }
            ],
        },
    ]


def _resolve_our_lineup(
    payload: dict[str, Any],
    seed: int,
    our: dict[str, Any],
) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    sel = payload.get("ourSelection")
    lead_raw = payload.get("ourLeadSlots")
    if sel and len(sel) == 4:
        four = tuple(sorted(int(s) for s in sel))  # type: ignore[return-value]
        if lead_raw and len(lead_raw) == 2:
            lead = (int(lead_raw[0]), int(lead_raw[1]))
            if lead[0] > lead[1]:
                lead = (lead[1], lead[0])
            return four, lead
    digest = _digest(f"lineup:{seed}", our, our)
    picked: list[int] = []
    idx = 0
    while len(picked) < 4:
        slot = digest[idx] % 6
        if slot not in picked:
            picked.append(slot)
        idx += 1
    four = tuple(sorted(picked))  # type: ignore[return-value]
    la = picked[digest[4] % 4]
    lb = picked[(digest[5] % 3 + 1) % 4]
    if lb == la:
        lb = picked[(picked.index(la) + 1) % 4]
    lead = (la, lb) if la < lb else (lb, la)
    return four, lead


def manifest_path_default() -> str:
    return str(Path(__file__).resolve().parents[2] / "manifest.json")
