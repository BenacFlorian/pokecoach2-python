"""HTTP schemas for analysis commands (workflow spec §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisCapabilitiesResponse(BaseModel):
    phases: list[str]
    profiles: list[str]
    regulations: list[str]


class AnalysisStartRequest(BaseModel):
    target_phase: str = Field(alias="targetPhase")
    profile: str

    model_config = {"populate_by_name": True}


class AnalysisStartResponse(BaseModel):
    matchup_id: str = Field(alias="matchupId")
    run_id: str = Field(alias="runId")
    source: str
    status: str
    process_status: str = Field(alias="processStatus")

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
