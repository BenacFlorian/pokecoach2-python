"""Demo seed HTTP schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DemoSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoSeedCounts(BaseModel):
    teams: int
    matchups: int
    runs: int


class DemoSeedResponse(BaseModel):
    source: str
    fixture_version: int = Field(alias="fixtureVersion")
    owned_team_ids: list[str] = Field(alias="ownedTeamIds")
    opponent_team_id: str = Field(alias="opponentTeamId")
    matchup_id: str = Field(alias="matchupId")
    run_id: str = Field(alias="runId")
    counts: DemoSeedCounts

    model_config = ConfigDict(populate_by_name=True)
