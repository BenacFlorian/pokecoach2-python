from __future__ import annotations

import pytest

from pokecoach_vgc_bridge.inference_control import (
    PolicyDecisionSeedStream,
    resolve_open_team_sheets,
    seed_torch_for_policy_decision,
)
from pokecoach_vgc_bridge.model_profile import InferenceConfig, ModelArchitecture, VgcModelProfile


def test_seed_stream_reproducible():
    a = PolicyDecisionSeedStream(42, "ours")
    b = PolicyDecisionSeedStream(42, "ours")
    assert [a.next_seed() for _ in range(3)] == [b.next_seed() for _ in range(3)]


def test_seed_stream_differs_by_request_seed():
    s1 = PolicyDecisionSeedStream(1, "ours")
    s2 = PolicyDecisionSeedStream(2, "ours")
    assert s1.next_seed() != s2.next_seed()


def test_seed_stream_differs_by_side():
    ours = PolicyDecisionSeedStream(9, "ours")
    opponent = PolicyDecisionSeedStream(9, "opponent")
    assert ours.next_seed() != opponent.next_seed()


def test_seed_stream_bounds_and_counter():
    stream = PolicyDecisionSeedStream(0, "opponent")
    assert stream.decision_index == 0
    seed = stream.next_seed()
    assert 0 <= seed <= (1 << 63) - 1
    assert stream.decision_index == 1
    stream.next_seed()
    assert stream.decision_index == 2


def test_invalid_side_rejected():
    with pytest.raises(ValueError, match="invalid policy side"):
        PolicyDecisionSeedStream(1, "p1")  # type: ignore[arg-type]


class _CudaStub:
    def __init__(self, available: bool) -> None:
        self._available = available
        self.manual_seed_all_calls: list[int] = []

    def is_available(self) -> bool:
        return self._available

    def manual_seed_all(self, seed: int) -> None:
        self.manual_seed_all_calls.append(seed)


class _TorchStub:
    def __init__(self, cuda_available: bool) -> None:
        self.manual_seed_calls: list[int] = []
        self.cuda = _CudaStub(cuda_available)

    def manual_seed(self, seed: int) -> None:
        self.manual_seed_calls.append(seed)


def test_seed_torch_cpu_only():
    torch_stub = _TorchStub(cuda_available=False)
    stream = PolicyDecisionSeedStream(5, "ours")
    applied = seed_torch_for_policy_decision(torch_stub, stream)
    assert applied == torch_stub.manual_seed_calls[0]
    assert torch_stub.cuda.manual_seed_all_calls == []


def test_seed_torch_cuda_path():
    torch_stub = _TorchStub(cuda_available=True)
    stream = PolicyDecisionSeedStream(5, "ours")
    applied = seed_torch_for_policy_decision(torch_stub, stream)
    assert torch_stub.manual_seed_calls == [applied]
    assert torch_stub.cuda.manual_seed_all_calls == [applied]


def _profile(*, ots: bool) -> VgcModelProfile:
    from pathlib import Path

    return VgcModelProfile(
        model_id="t",
        profile_path=Path("/tmp/vgc.yaml"),
        checkpoint_path=Path("/tmp/c.zip"),
        architecture=ModelArchitecture(),
        inference=InferenceConfig(open_team_sheets=ots),
    )


def test_resolve_ots_env_overrides_profile():
    profile = _profile(ots=False)
    assert resolve_open_team_sheets(profile, "true") is True
    assert resolve_open_team_sheets(profile, "0") is False


def test_resolve_ots_profile_when_env_absent():
    assert resolve_open_team_sheets(_profile(ots=True), None) is True
    assert resolve_open_team_sheets(_profile(ots=False), None) is False
    assert resolve_open_team_sheets(None, None) is False


def test_resolve_ots_invalid_env():
    with pytest.raises(ValueError, match="POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS"):
        resolve_open_team_sheets(None, "maybe")
