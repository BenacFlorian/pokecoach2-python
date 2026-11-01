from __future__ import annotations

import asyncio

from pokecoach_vgc_bridge.battle_runner import _await_preview_selection


class _Client:
    def __init__(self) -> None:
        self.stopped = False

    async def stop_listening(self) -> None:
        self.stopped = True


class _Battle:
    def __init__(self) -> None:
        self.team = {str(index): object() for index in range(6)}
        self._active_reads = 0

    @property
    def active_pokemon(self):
        self._active_reads += 1
        if self._active_reads == 1:
            raise ValueError("player_role is None")
        return [self.team["0"], self.team["1"]]


class _Player:
    def __init__(self) -> None:
        self.battles: dict[str, _Battle] = {}
        self.ps_client = _Client()
        self.cancelled = False

    async def battle_against(self, opponent, n_battles: int) -> None:
        del n_battles
        self.battles["battle"] = _Battle()
        opponent.battles["battle"] = _Battle()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_preview_selection_stops_before_full_battle():
    p1 = _Player()
    p2 = _Player()
    our_lead, opponent_lead = asyncio.run(
        _await_preview_selection(p1, p2, timeout_seconds=1)
    )

    assert our_lead == (0, 1)
    assert opponent_lead == (0, 1)
    assert p1.cancelled
    assert p1.ps_client.stopped
    assert p2.ps_client.stopped
