"""Construct the configured engine adapter."""

from __future__ import annotations

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import EngineAdapter
from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter


def build_engine_adapter(settings: Settings) -> EngineAdapter:
    mode = settings.engine_mode.lower()
    if mode == "vgc_bench":
        return VgcBenchEngineAdapter(settings)
    if mode == "stub":
        return StubEngineAdapter()
    raise ValueError(f"unsupported POKECOACH_ENGINE mode: {settings.engine_mode}")
