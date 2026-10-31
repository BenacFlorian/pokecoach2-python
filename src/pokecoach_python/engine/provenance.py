"""Run and battle provenance for stub vs real engine."""

from __future__ import annotations

from typing import Any

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.engine.errors import EngineBridgeError

NORMALIZER_VERSION = 1


def build_run_provenance(
    *,
    engine_mode: str,
    product_phases: list[str],
    hello: dict[str, Any] | None,
    checkpoint_id: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "productPhases": product_phases,
        "engineMode": engine_mode,
        "checkpointId": checkpoint_id,
        "normalizerVersion": NORMALIZER_VERSION,
    }
    if hello is None:
        base["engineIdentity"] = {"kind": "stub"}
        return base
    manifest = hello.get("manifest") or {}
    base["engineIdentity"] = {
        "kind": hello.get("engine"),
        "checkpointLoaded": hello.get("checkpointLoaded"),
        "checkpointFingerprint": hello.get("checkpointFingerprint")
        or manifest.get("checkpoint", {}).get("sha256"),
        "manifestSchema": manifest.get("schemaVersion"),
        "vgcBenchCommit": manifest.get("vgcBenchCommit"),
        "traceVersion": hello.get("traceVersion"),
    }
    return base


def assert_run_engine_compatible(
    stored: dict[str, Any],
    current: dict[str, Any],
) -> None:
    if stored.get("engineMode") != current.get("engineMode"):
        raise EngineBridgeError(
            "ENGINE_MODE_MISMATCH",
            "engine mode changed since run creation",
        )
    if stored.get("engineMode") == "stub":
        return
    a = stored.get("engineIdentity") or {}
    b = current.get("engineIdentity") or {}
    if a.get("kind") != b.get("kind"):
        raise EngineBridgeError("ENGINE_IDENTITY_MISMATCH", "engine identity drift")
    if a.get("checkpointFingerprint") and b.get("checkpointFingerprint"):
        if a["checkpointFingerprint"] != b["checkpointFingerprint"]:
            raise EngineBridgeError(
                "CHECKPOINT_MISMATCH",
                "checkpoint fingerprint changed",
            )


def assert_real_battles_eligible(
    run_provenance: dict[str, Any],
    records: list[BattleRecord],
) -> None:
    mode = run_provenance.get("engineMode")
    if mode != "vgc_bench":
        raise EngineBridgeError(
            "NOT_REAL_ENGINE",
            "LLM synthesis requires vgc_bench provenance",
        )
    identity = run_provenance.get("engineIdentity") or {}
    if not identity.get("checkpointLoaded") and identity.get("kind") != "vgc-bench":
        if identity.get("kind") == "fixture-bridge":
            raise EngineBridgeError("FIXTURE_ENGINE", "fixture battles not eligible for LLM")
        raise EngineBridgeError("ENGINE_NOT_VERIFIED", "checkpoint not loaded at run time")
    for record in records:
        meta = record.meta or {}
        if meta.get("engine") in (None, "stub"):
            raise EngineBridgeError("STUB_BATTLE", "battle record from stub engine")
        if not meta.get("terminalEvidence"):
            raise EngineBridgeError("INCOMPLETE_TRACE", "missing terminal evidence")
        if record.outcome == "technical":
            raise EngineBridgeError("TECHNICAL_OUTCOME", "technical battle not eligible")


def current_engine_provenance_snapshot(
    engine_mode: str,
    hello: dict[str, Any] | None,
) -> dict[str, Any]:
    return build_run_provenance(
        engine_mode=engine_mode,
        product_phases=[],
        hello=hello,
        checkpoint_id="",
    )
