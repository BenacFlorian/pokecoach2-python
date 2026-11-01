from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pokecoach_vgc_bridge.vgc_source import prepare_vgc_bench_source


def test_prepare_vgc_bench_source_exposes_upstream_namespace(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    original_cwd = Path.cwd()
    root = tmp_path / "vgc-bench"
    policy_player = root / "vgc_bench" / "src" / "policy_player.py"
    policy_player.parent.mkdir(parents=True)
    policy_player.write_text("# test policy player\n", encoding="utf-8")
    monkeypatch.setenv("POKECOACH_VGC_BENCH_ROOT", str(root))
    monkeypatch.setattr(sys, "path", list(sys.path))

    assert prepare_vgc_bench_source() == root
    assert str(root) == sys.path[0]
    assert Path.cwd() == original_cwd


def test_prepare_vgc_bench_source_rejects_incomplete_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("POKECOACH_VGC_BENCH_ROOT", str(tmp_path))

    with pytest.raises(RuntimeError, match="VGC_BENCH_SOURCE"):
        prepare_vgc_bench_source()
