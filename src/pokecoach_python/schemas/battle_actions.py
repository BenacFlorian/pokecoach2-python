"""Shared validation for normalized battle move actions (Showdown targets)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class PokemonRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["ours", "opponent"]
    slot: int = Field(ge=0, le=5)


class ActionTargetPokemon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pokemon"]
    ref: PokemonRef


class ActionTargetZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["zone"]
    zone: ShowdownMoveTarget


class MoveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["move"]
    actor: PokemonRef
    move: str
    targets: list[ActionTargetPokemon | ActionTargetZone]
    move_id: str | None = Field(default=None, alias="moveId")
    target_type: ShowdownMoveTarget | None = Field(default=None, alias="targetType")
    target_source: TargetSource | None = Field(default=None, alias="targetSource")
    terastallize: str | None = None

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, targets: list[Any]) -> list[Any]:
        if not isinstance(targets, list):
            raise ValueError("targets must be a list")
        return targets


def validate_move_action(raw: dict[str, Any]) -> MoveAction:
    return MoveAction.model_validate(raw)


def is_valid_move_action(raw: dict[str, Any]) -> bool:
    try:
        validate_move_action(raw)
    except ValueError:
        return False
    return True
