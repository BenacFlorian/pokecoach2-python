"""Checkpoint file verification and fingerprint."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checkpoint(path: str, expected_sha256: str | None) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    digest = sha256_file(p)
    if expected_sha256 and expected_sha256.strip().lower() != digest.lower():
        raise ValueError("checkpoint SHA-256 mismatch")
    return digest


def fingerprint_from_path(path: str) -> str:
    return sha256_file(path)[:16]
