"""HTTP schemas for analysis commands (workflow spec §2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OutputLocale = Literal["fr", "en"]


class AnalysisCapabilitiesResponse(BaseModel):
    phases: list[str]
    phase_order: list[str] = Field(alias="phaseOrder")
    profiles: list[str]
    regulations: list[str]
    synthesis_available: bool = Field(alias="synthesisAvailable")

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class AnalysisStartRequest(BaseModel):
    target_phase: str = Field(alias="targetPhase")
    profile: str
    locale: OutputLocale = "fr"

    model_config = {"populate_by_name": True}


class AnalysisStartResponse(BaseModel):
    matchup_id: str = Field(alias="matchupId")
    run_id: str = Field(alias="runId")
    source: str
    status: str
    process_status: str = Field(alias="processStatus")

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class AnalysisContinueRequest(BaseModel):
    target_phase: str = Field(alias="targetPhase")

    model_config = {"populate_by_name": True}


class AnalysisContinueResponse(AnalysisStartResponse):
    pass


class AnalysisCancelResponse(AnalysisStartResponse):
    pass
