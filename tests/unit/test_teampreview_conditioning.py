from __future__ import annotations

from pokecoach_python.diagnostics.teampreview_conditioning import (
    count_four_distribution,
    canonical_four_slots,
    total_variation_distance,
)
from pokecoach_python.diagnostics.teampreview_conditioning import (
    OpponentAuditSample,
    selection_key,
)


def test_canonical_four_sorted():
    assert canonical_four_slots((4, 2, 5, 1)) == (1, 2, 4, 5)


def test_total_variation_distance_disjoint_support():
    p = {"a": 1.0}
    q = {"b": 1.0}
    assert total_variation_distance(p, q) == 1.0


def test_selection_key_includes_lead_order():
    key = selection_key((1, 2, 4, 5), (4, 5))
    assert key.startswith("(4, 5,")


def test_four_distribution_counts():
    rows = [
        OpponentAuditSample("a", 1, (0, 1, 2, 3), (0, 1), "sha256-v1:x"),
        OpponentAuditSample("a", 2, (0, 1, 2, 3), (0, 1), "sha256-v1:x"),
        OpponentAuditSample("a", 3, (0, 1, 4, 5), (0, 1), "sha256-v1:y"),
    ]
    dist = count_four_distribution(rows)
    assert dist["0,1,2,3"] == 2 / 3
    assert dist["0,1,4,5"] == 1 / 3
