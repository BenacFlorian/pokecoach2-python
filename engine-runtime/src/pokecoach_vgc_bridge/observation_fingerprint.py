"""Empreinte non sensible d'une observation policy (team preview)."""

from __future__ import annotations

import hashlib

import numpy as np
import numpy.typing as npt


def fingerprint_policy_observation(
    observation: npt.NDArray[np.float32],
    action_mask: npt.NDArray,
) -> str:
    obs = np.ascontiguousarray(observation, dtype=np.float32)
    mask = np.ascontiguousarray(np.asarray(action_mask, dtype=np.bool_))
    digest = hashlib.sha256()
    digest.update(f"{obs.shape}".encode())
    digest.update(obs.tobytes())
    digest.update(mask.tobytes())
    return f"sha256-v1:{digest.hexdigest()}"
