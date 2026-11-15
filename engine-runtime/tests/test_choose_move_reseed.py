from __future__ import annotations

from pokecoach_vgc_bridge.inference_control import PolicyDecisionSeedStream, seed_torch_for_policy_decision


class _CudaStub:
    def is_available(self) -> bool:
        return False


class _TorchStub:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.cuda = _CudaStub()

    def manual_seed(self, seed: int) -> None:
        self.calls.append(seed)


def test_stochastic_player_reseeds_before_each_choose_move():
    """Même logique que RecordingPolicyPlayer.choose_move."""
    torch_stub = _TorchStub()
    stream = PolicyDecisionSeedStream(99, "ours")

    class Parent:
        def choose_move(self, battle):
            return battle

    class Player(Parent):
        deterministic = False
        pokecoach_seed_stream = stream

        def choose_move(self, battle):
            inner_stream = getattr(self, "pokecoach_seed_stream", None)
            if inner_stream is not None and not getattr(self, "deterministic", False):
                seed_torch_for_policy_decision(torch_stub, inner_stream)
            return super().choose_move(battle)

    player = Player()
    player.choose_move(object())
    player.choose_move(object())
    assert stream.decision_index == 2
    assert len(torch_stub.calls) == 2
    assert torch_stub.calls[0] != torch_stub.calls[1]


def test_deterministic_player_skips_reseed():
    torch_stub = _TorchStub()
    stream = PolicyDecisionSeedStream(1, "ours")

    class Parent:
        def choose_move(self, battle):
            return battle

    class Player(Parent):
        deterministic = True
        pokecoach_seed_stream = stream

        def choose_move(self, battle):
            inner_stream = getattr(self, "pokecoach_seed_stream", None)
            if inner_stream is not None and not getattr(self, "deterministic", False):
                seed_torch_for_policy_decision(torch_stub, inner_stream)
            return super().choose_move(battle)

    Player().choose_move(object())
    assert stream.decision_index == 0
    assert torch_stub.calls == []
