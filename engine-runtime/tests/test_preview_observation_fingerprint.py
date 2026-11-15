from __future__ import annotations

import numpy as np

from pokecoach_vgc_bridge.observation_fingerprint import fingerprint_policy_observation


def test_fingerprint_stable_for_same_arrays():
    obs = np.zeros((4, 8), dtype=np.float32)
    mask = np.ones(12, dtype=bool)
    a = fingerprint_policy_observation(obs, mask)
    b = fingerprint_policy_observation(obs, mask)
    assert a == b
    assert a.startswith("sha256-v1:")


def test_fingerprint_accepts_python_list_mask():
    obs = np.zeros((2, 4), dtype=np.float32)
    mask = [True, False, True]
    assert fingerprint_policy_observation(obs, mask).startswith("sha256-v1:")


def test_fingerprint_changes_when_observation_changes():
    obs_a = np.zeros((4, 8), dtype=np.float32)
    obs_b = obs_a.copy()
    obs_b[0, 0] = 1.0
    mask = np.ones(12, dtype=bool)
    assert fingerprint_policy_observation(obs_a, mask) != fingerprint_policy_observation(
        obs_b, mask
    )
