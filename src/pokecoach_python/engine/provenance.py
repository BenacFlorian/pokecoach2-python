"""Run and battle provenance for stub vs real engine."""

from __future__ import annotations

from typing import Any

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.engine.errors import EngineBridgeError

NORMALIZER_VERSION = 1


def _checkpoint_fingerprint_without_bridge(settings: Settings) -> str | None:
    if settings.vgc_checkpoint_sha256:
        return settings.vgc_checkpoint_sha256.strip().lower()[:16]
    if not settings.vgc_model_profile:
        return None
    try:
        from pokecoach_vgc_bridge.model_profile import load_vgc_model_profile_from_env

        profile = load_vgc_model_profile_from_env()
    except Exception:
        return None
    if profile is None or not profile.checkpoint_sha256:
        return None
    return profile.checkpoint_sha256.strip().lower()[:16]


def provenance_for_worker_compat(settings: Settings) -> dict[str, Any]:
    """Vérifie la config courante sans lancer le subprocess bridge (pas de double hello)."""
    hello: dict[str, Any] | None = None
    if settings.engine_mode.lower() == "vgc_bench" and settings.vgc_engine_configured():
        fp = _checkpoint_fingerprint_without_bridge(settings)
        hello = {
            "engine": "vgc-bench",
            "checkpointLoaded": True,
            "checkpointFingerprint": fp,
        }
    return build_run_provenance(
        engine_mode=settings.engine_mode,
        product_phases=settings.analysis_deployed_phase_list(),
        hello=hello,
        checkpoint_id=settings.analysis_checkpoint_id,
    )


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
        from pokecoach_python.llm.battle_sources import validate_d_synthesis_source

        try:
            validate_d_synthesis_source(record)
        except ValueError as exc:
            raise EngineBridgeError("INCOMPLETE_TRACE", str(exc)) from exc


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
