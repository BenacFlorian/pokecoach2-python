"""Canonical regulation labels (M-A / M-B / M-C) for API and DB."""

from __future__ import annotations


def canonical_regulation_label(regulation: str) -> str:
    """Normalize MA/MB/MC and M-A/M-B/M-C to canonical M-X labels."""
    normalized = regulation.strip().upper().replace("_", "-")
    aliases = {
        "MB": "M-B",
        "M-B": "M-B",
        "MA": "M-A",
        "M-A": "M-A",
        "MC": "M-C",
        "M-C": "M-C",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized


def canonical_regulation_allowed(regulation: str, allowed: list[str]) -> bool:
    label = canonical_regulation_label(regulation)
    allowed_labels = {canonical_regulation_label(r) for r in allowed}
    return label in allowed_labels
