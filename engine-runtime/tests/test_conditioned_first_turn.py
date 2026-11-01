from __future__ import annotations

from pokecoach_vgc_bridge.battle_session import imposed_four_with_lead_order


def test_imposed_four_with_lead_order_puts_leads_first():
    four = imposed_four_with_lead_order((3, 5, 0, 1), (3, 5))
    assert four == (3, 5, 0, 1)


def test_imposed_four_with_lead_order_canonical_back_order():
    four = imposed_four_with_lead_order((0, 1, 4, 5), (0, 1))
    assert four[0:2] == (0, 1)
    assert set(four) == {0, 1, 4, 5}
