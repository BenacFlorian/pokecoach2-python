"""VGC-Bench engine via isolated JSONL bridge (no stub fallback)."""

from __future__ import annotations

from typing import Any

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import (
    BattleRecord,
    EngineAdapter,
    EngineCapabilities,
    PreviewRecord,
    SimulationRequest,
    TurnOneRecord,
)
from pokecoach_python.engine.errors import EngineBridgeError, EngineUnavailableError
from pokecoach_python.engine.subprocess_client import VgcSubprocessClient
from pokecoach_python.workflow.battle_records import battle_record_from_payload


class VgcBenchEngineAdapter(EngineAdapter):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not settings.vgc_checkpoint_path and not _fixture_allowed():
            raise EngineUnavailableError(
                "CHECKPOINT_UNCONFIGURED",
                "VGC_CHECKPOINT_PATH is required for POKECOACH_ENGINE=vgc_bench",
            )
        self._client = VgcSubprocessClient(settings)
        self._hello: dict[str, Any] | None = None

    def _hello_result(self) -> dict[str, Any]:
        if self._hello is None:
            self._hello = self._client.request(
                "hello",
                {},
                timeout_seconds=self._settings.engine_startup_timeout_seconds,
            )
        return self._hello

    def preflight(
        self,
        config: dict[str, Any],
        snapshots: tuple[dict[str, Any], dict[str, Any]],
    ) -> EngineCapabilities:
        our, opp = snapshots
        if not our.get("pokemon") or not opp.get("pokemon"):
            raise EngineBridgeError(
                "SNAPSHOTS_REQUIRED",
                "preflight requires two non-empty team snapshots",
            )
        regulation = str(config.get("regulation", self._settings.analysis_regulation_default()))
        payload = {
            "config": {
                "regulation": regulation,
                "checkpoint_id": config.get(
                    "checkpoint_id", self._settings.analysis_checkpoint_id
                ),
            },
            "ourSnapshot": our,
            "opponentSnapshot": opp,
            "regulationShowdownMap": self._settings.regulation_showdown_map,
        }
        result = self._client.request(
            "preflight",
            payload,
            timeout_seconds=self._settings.engine_preflight_timeout_seconds,
        )
        notes = tuple(str(n) for n in (result.get("notes") or ()))
        return EngineCapabilities(
            regulation=str(result.get("regulation", regulation)),
            checkpoint_id=str(result.get("checkpointId", "")),
            checkpoint_fingerprint=str(result.get("checkpointFingerprint", "")),
            supports_preview=bool(result.get("supportsPreview")),
            supports_first_turn=bool(result.get("supportsFirstTurn")),
            supports_full_battle=bool(result.get("supportsFullBattle")),
            stochastic=bool(result.get("stochastic", True)),
            python_version=str(result.get("pythonVersion", "")),
            notes=notes,
        )

    def preview(self, request: SimulationRequest) -> PreviewRecord:
        payload = _sim_payload(self._settings, request)
        raw = self._client.request(
            "preview",
            payload,
            timeout_seconds=request.timeout_seconds,
        )
        opp = raw["opponentLeadSlots"]
        our_raw = raw.get("ourLeadSlots")
        return PreviewRecord(
            opponent_lead_slots=(int(opp[0]), int(opp[1])),
            our_lead_slots=(
                (int(our_raw[0]), int(our_raw[1])) if our_raw is not None else None
            ),
            meta=dict(raw.get("meta") or {}),
        )

    def first_turn(self, request: SimulationRequest) -> TurnOneRecord:
        if request.opponent_lead is None:
            raise ValueError("opponent_lead required for first_turn")
        payload = _sim_payload(self._settings, request)
        payload["opponentLead"] = list(request.opponent_lead)
        if request.our_selection is not None:
            payload["ourSelection"] = list(request.our_selection)
        if request.our_lead_slots is not None:
            payload["ourLeadSlots"] = list(request.our_lead_slots)
        raw = self._client.request(
            "first_turn",
            payload,
            timeout_seconds=self._settings.engine_first_turn_timeout_seconds,
        )
        opp_raw = raw["opponentLeadSlots"]
        return TurnOneRecord(
            opponent_lead_slots=(int(opp_raw[0]), int(opp_raw[1])),
            payload=dict(raw["payload"]),
        )

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        if request.opponent_lead is None:
            raise ValueError("opponent_lead required for full_battle")
        payload = _sim_payload(self._settings, request)
        payload["opponentLead"] = list(request.opponent_lead)
        if request.our_selection is not None:
            payload["ourSelection"] = list(request.our_selection)
        if request.our_lead_slots is not None:
            payload["ourLeadSlots"] = list(request.our_lead_slots)
        if request.opponent_four is not None:
            payload["opponentFour"] = list(request.opponent_four)
        if request.opponent_back_pair is not None:
            payload["opponentBackPair"] = list(request.opponent_back_pair)
        raw = self._client.request(
            "full_battle",
            payload,
            timeout_seconds=self._settings.engine_full_battle_timeout_seconds,
        )
        record = battle_record_from_payload(raw)
        meta = dict(record.meta)
        meta.update(raw.get("meta") or {})
        return BattleRecord(
            preview=record.preview,
            turns=record.turns,
            outcome=record.outcome,
            participants=record.participants,
            meta=meta,
        )

    def hello(self) -> dict[str, Any]:
        return self._hello_result()

    def close(self) -> None:
        self._client.close()


def _sim_payload(settings: Settings, request: SimulationRequest) -> dict[str, Any]:
    return {
        "seed": request.seed,
        "regulation": request.regulation,
        "checkpointId": request.checkpoint_id,
        "ourSnapshot": request.our_snapshot,
        "opponentSnapshot": request.opponent_snapshot,
        "regulationShowdownMap": settings.regulation_showdown_map,
        "timeoutSeconds": request.timeout_seconds,
    }


def _fixture_allowed() -> bool:
    import os

    return os.environ.get("POKECOACH_BRIDGE_FIXTURE") == "1"
