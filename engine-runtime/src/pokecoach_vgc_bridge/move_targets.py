"""Resolve Showdown move target categories for normalized battle actions."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

ShowdownMoveTarget = Literal[
    "normal",
    "adjacentFoe",
    "adjacentAlly",
    "adjacentAllyOrSelf",
    "any",
    "self",
    "allAdjacent",
    "allAdjacentFoes",
    "allies",
    "allySide",
    "allyTeam",
    "foeSide",
    "all",
    "randomNormal",
    "scripted",
]

TargetSource = Literal["request", "dex", "unknown"]

SHOWDOWN_MOVE_TARGETS: frozenset[str] = frozenset(
    {
        "normal",
        "adjacentFoe",
        "adjacentAlly",
        "adjacentAllyOrSelf",
        "any",
        "self",
        "allAdjacent",
        "allAdjacentFoes",
        "allies",
        "allySide",
        "allyTeam",
        "foeSide",
        "all",
        "randomNormal",
        "scripted",
    }
)

INDIVIDUAL_MOVE_TARGETS: frozenset[str] = frozenset(
    {"normal", "adjacentFoe", "adjacentAlly", "adjacentAllyOrSelf", "any"}
)


@dataclass(frozen=True)
class MoveTargetInfo:
    move_id: str | None
    move_name: str
    target_type: ShowdownMoveTarget | None
    target_source: TargetSource


@dataclass(frozen=True)
class MoveTargetCatalog:
    battle_format: str
    fingerprint: str
    source: str
    moves: dict[str, dict[str, str]]


def showdown_root() -> Path:
    configured = Path(__file__).resolve().parents[2] / "vendor" / "vgc-bench" / "pokemon-showdown"
    return configured


def export_script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "export_move_targets.cjs"


def to_move_id(name_or_id: str) -> str:
    text = name_or_id.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _catalog_from_poke_env(gen: int = 9) -> MoveTargetCatalog:
    from poke_env.data import GenData

    data = GenData.from_gen(gen)
    moves: dict[str, dict[str, str]] = {}
    for move_id, entry in data.moves.items():
        if not isinstance(entry, dict):
            continue
        target = entry.get("target")
        if not isinstance(target, str) or target not in SHOWDOWN_MOVE_TARGETS:
            continue
        moves[str(move_id)] = {"name": str(entry.get("name") or move_id), "target": target}
    return MoveTargetCatalog(
        battle_format=f"gen{gen}",
        fingerprint=f"poke-env-gen{gen}:{len(moves)}",
        source="poke-env-gendata",
        moves=moves,
    )


def _catalog_from_node(showdown_path: Path, battle_format: str) -> MoveTargetCatalog | None:
    script = export_script_path()
    if not script.is_file():
        return None
    try:
        proc = subprocess.run(
            ["node", str(script), str(showdown_path), battle_format],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    payload = json.loads(proc.stdout)
    moves = payload.get("moves") or {}
    if not isinstance(moves, dict):
        return None
    return MoveTargetCatalog(
        battle_format=str(payload.get("battleFormat") or battle_format),
        fingerprint=str(payload.get("fingerprint") or battle_format),
        source=str(payload.get("source") or "showdown-dex"),
        moves={str(k): dict(v) for k, v in moves.items() if isinstance(v, dict)},
    )


@lru_cache(maxsize=8)
def load_move_catalog(battle_format: str) -> MoveTargetCatalog:
    """Load move targets once per process/format (Showdown Dex or poke-env fallback)."""
    root = showdown_root()
    if root.is_dir():
        from_node = _catalog_from_node(root, battle_format)
        if from_node is not None and from_node.moves:
            return from_node
    return _catalog_from_poke_env(9)


def _coerce_target(value: Any) -> ShowdownMoveTarget | None:
    if isinstance(value, str) and value in SHOWDOWN_MOVE_TARGETS:
        return value  # type: ignore[return-value]
    return None


def resolve_move_target(
    move_name: str,
    catalog: MoveTargetCatalog,
    *,
    request_target: Any = None,
) -> MoveTargetInfo:
    move_id = to_move_id(move_name)
    entry = catalog.moves.get(move_id)
    dex_target = _coerce_target(entry.get("target") if entry else None)
    req_target = _coerce_target(request_target)
    if req_target is not None:
        return MoveTargetInfo(
            move_id=move_id or None,
            move_name=str(entry.get("name") if entry else move_name),
            target_type=req_target,
            target_source="request",
        )
    if dex_target is not None:
        return MoveTargetInfo(
            move_id=move_id or None,
            move_name=str(entry.get("name") if entry else move_name),
            target_type=dex_target,
            target_source="dex",
        )
    return MoveTargetInfo(
        move_id=move_id or None,
        move_name=move_name,
        target_type=None,
        target_source="unknown",
    )


def build_action_targets(
    info: MoveTargetInfo,
    *,
    actor_side: str,
    actor_slot: int,
    target_side: str,
    target_roster_slot: int | None,
) -> list[dict[str, Any]]:
    if info.target_type is None:
        return []
    if info.target_type == "self":
        return [
            {
                "kind": "pokemon",
                "ref": {"side": actor_side, "slot": int(actor_slot)},
            }
        ]
    if info.target_type in INDIVIDUAL_MOVE_TARGETS:
        if target_roster_slot is not None:
            return [
                {
                    "kind": "pokemon",
                    "ref": {"side": target_side, "slot": int(target_roster_slot)},
                }
            ]
        return []
    return [{"kind": "zone", "zone": info.target_type}]


def enrich_move_action(
    action: dict[str, Any],
    info: MoveTargetInfo,
    *,
    actor_side: str,
    actor_slot: int,
    target_side: str,
    target_roster_slot: int | None,
) -> dict[str, Any]:
    if action.get("kind") != "move":
        return action
    targets = build_action_targets(
        info,
        actor_side=actor_side,
        actor_slot=actor_slot,
        target_side=target_side,
        target_roster_slot=target_roster_slot,
    )
    enriched = dict(action)
    enriched["moveId"] = info.move_id
    enriched["targetType"] = info.target_type
    enriched["targetSource"] = info.target_source
    enriched["targets"] = targets
    return enriched
