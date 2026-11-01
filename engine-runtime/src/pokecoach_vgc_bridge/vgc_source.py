"""Locate the checked-out VGC-Bench source required by its namespace package."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_POLICY_PLAYER = Path("vgc_bench") / "src" / "policy_player.py"


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "vendor" / "vgc-bench"


def prepare_vgc_bench_source() -> Path:
    """Expose VGC-Bench's un-packaged ``vgc_bench.src`` source tree."""
    configured = os.environ.get("POKECOACH_VGC_BENCH_ROOT")
    root = Path(configured).expanduser().resolve() if configured else _default_root()
    if not (root / _POLICY_PLAYER).is_file():
        raise RuntimeError(
            "VGC_BENCH_SOURCE: checkout the pinned VGC-Bench repository at "
            f"{root} (run: devbox run engine-setup)"
        )
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        importlib.invalidate_caches()
    return root
