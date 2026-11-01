"""Turn-1 action resolutions for aggregation (decision vs observed outcome)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

ResolutionCause = Literal[
    "unchanged",
    "switch",
    "redirect",
    "other",
    "not-executed",
]


def resolution_fingerprint(
    actions: list[dict[str, Any]],
    *,
    side: str,
    events: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Stable key for resolution variants of the same initial joint decision."""
    parts: list[str] = []
    for action in actions:
        actor = action.get("actor") or {}
        slot = int(actor.get("slot", -1))
        parts.append(_actor_resolution_token(side, slot, action, events))
    return tuple(parts)


def _actor_resolution_token(
    side: str,
    slot: int,
    action: dict[str, Any],
    events: list[dict[str, Any]],
) -> str:
    kind = action.get("kind")
    if kind == "switch":
        return f"switch:{slot}->{action.get('switchTo', {}).get('slot')}"
    move = str(action.get("move") or "")
    selected = _selected_target_token(action)
    executed = _executed_target_from_events(side, slot, move, events)
    if executed is None:
        return f"move:{slot}:{move}:not-executed"
    if selected == executed:
        return f"move:{slot}:{move}:{executed}"
    return f"move:{slot}:{move}:sel={selected}:exe={executed}"


def _selected_target_token(action: dict[str, Any]) -> str:
    targets = action.get("targets") or []
    if not targets:
        return "none"
    first = targets[0]
    if first.get("kind") == "zone":
        return f"zone:{first.get('zone')}"
    ref = first.get("ref") or {}
    return f"{ref.get('side')}:{ref.get('slot')}"


def _executed_target_from_events(
    side: str,
    slot: int,
    move: str,
    events: list[dict[str, Any]],
) -> str | None:
    role_order = ("a", "b")
    for role in role_order:
        for event in events:
            if event.get("kind") != "move":
                continue
            if event.get("side") != side:
                continue
            if event.get("role") != role:
                continue
            if str(event.get("move") or "").lower() != move.lower():
                continue
            token = event.get("targetToken")
            if token:
                return str(token)
            return "executed"
    switch_before = any(
        event.get("kind") == "switch" and event.get("side") == side for event in events
    )
    if switch_before:
        return "post-switch"
    return None


def build_action_resolutions(
    actions: list[dict[str, Any]],
    *,
    side: str,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build per-actor resolution entries aligned with the two actors."""
    resolutions: list[dict[str, Any]] = []
    for action in actions:
        actor = action.get("actor") or {}
        slot = int(actor.get("slot", -1))
        cause: ResolutionCause = "unchanged"
        executed = True
        reason: str | None = None
        if action.get("kind") == "switch":
            cause = "switch"
        else:
            token = _executed_target_from_events(
                side,
                slot,
                str(action.get("move") or ""),
                events,
            )
            if token is None:
                executed = False
                cause = "not-executed"
                reason = "move not observed in replay"
            elif token == "post-switch":
                cause = "switch"
            elif token != _selected_target_token(action):
                cause = "redirect" if "[" in str(token) else "other"
        resolutions.append(
            {
                "actor": {"side": side, "slot": slot},
                "executed": executed,
                "reason": reason,
                "selectedTarget": _selected_target_dict(action),
                "resolvedTargets": _resolved_targets(side, slot, action, events),
                "cause": cause,
            }
        )
    return resolutions


def _selected_target_dict(action: dict[str, Any]) -> dict[str, Any] | None:
    targets = action.get("targets") or []
    if not targets:
        return None
    first = targets[0]
    if first.get("kind") == "zone":
        return {"kind": "zone", "zone": first.get("zone")}
    ref = first.get("ref")
    if isinstance(ref, dict):
        return {"kind": "pokemon", "ref": dict(ref)}
    return None


def _resolved_targets(
    side: str,
    slot: int,
    action: dict[str, Any],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    move = str(action.get("move") or "")
    for event in events:
        if event.get("kind") != "move" or event.get("side") != side:
            continue
        if str(event.get("move") or "").lower() != move.lower():
            continue
        token = event.get("targetToken")
        if token and token.startswith("p"):
            return [{"kind": "protocol", "token": token}]
    targets = action.get("targets") or []
    out: list[dict[str, Any]] = []
    for target in targets:
        if target.get("kind") == "pokemon" and isinstance(target.get("ref"), dict):
            out.append({"kind": "pokemon", "ref": dict(target["ref"])})
    return out


def attach_resolutions_to_frequency_rows(
    rows: list[dict[str, Any]],
    *,
    records: list[Any],
    side: str,
    joint_key_fn: Any,
    actions_from_payload: Any,
) -> list[dict[str, Any]]:
    """Attach resolutions[] to each frequency row from per-sample payloads."""
    by_joint: dict[str, list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]] = {}
    for record in records:
        payload = record.payload
        actions = actions_from_payload(payload, side=side)
        events = payload.get("turnEvents") or []
        key = joint_key_fn(actions)
        resolutions = build_action_resolutions(actions, side=side, events=events)
        by_joint.setdefault(key, []).append((actions, resolutions))

    enriched: list[dict[str, Any]] = []
    for row in rows:
        key = joint_key_fn(row["value"])
        samples = by_joint.get(key, [])
        counter: Counter[str] = Counter()
        resolution_by_key: dict[str, list[dict[str, Any]]] = {}
        for _actions, resolutions in samples:
            fp = json.dumps(resolutions, sort_keys=True, separators=(",", ":"))
            counter[fp] += 1
            resolution_by_key[fp] = resolutions
        resolution_rows = [
            {"value": resolution_by_key[fp], "count": count}
            for fp, count in counter.most_common()
        ]
        if resolution_rows:
            total = sum(item["count"] for item in resolution_rows)
            if total != row["count"]:
                raise ValueError("resolution counts must sum to row count")
            row = {**row, "resolutions": resolution_rows}
        enriched.append(row)
    return enriched
