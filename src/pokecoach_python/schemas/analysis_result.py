"""Simulation result envelope v2 (shared contract with SQL and Angular)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Phase = Literal["A", "B", "C", "D", "synthesis"]

_PHASE_ORDER: tuple[Phase, ...] = ("A", "C", "B", "D", "synthesis")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PokemonRef(StrictModel):
    side: Literal["ours", "opponent"]
    slot: int = Field(ge=0, le=5)


class OpponentLeadEntry(StrictModel):
    id: str
    slots: tuple[int, int]
    count: int = Field(ge=0)

    @model_validator(mode="after")
    def slots_distinct(self) -> OpponentLeadEntry:
        a, b = self.slots
        if a == b or a < 0 or a > 5 or b < 0 or b > 5:
            raise ValueError("lead slots must be distinct indices 0-5")
        return self


class OpponentLeadsSection(StrictModel):
    sampleSize: int = Field(ge=0)
    leads: list[OpponentLeadEntry]


class Turn1Section(StrictModel):
    """Legacy turn-1 aggregate shape (unit tests for joint action grouping)."""

    sampleSize: int = Field(ge=0)
    jointActions: list[Any]
    backPairs: list[Any]
    backSlotMarginals: list[Any]
    endStateNotes: list[str]


class LeadSelection(StrictModel):
    ourFourSlots: tuple[int, int, int, int]
    ourLeadSlots: tuple[int, int]

    @model_validator(mode="after")
    def validate_slots(self) -> LeadSelection:
        four = self.ourFourSlots
        if len(set(four)) != 4 or any(s < 0 or s > 5 for s in four):
            raise ValueError("ourFourSlots must be four distinct indices 0-5")
        lead_a, lead_b = self.ourLeadSlots
        if lead_a not in four or lead_b not in four or lead_a == lead_b:
            raise ValueError("ourLeadSlots must be two distinct slots from ourFourSlots")
        return self


class LeadPickSection(StrictModel):
    selection: LeadSelection
    comparisons: list[Any]
    selectionRuleVersion: str
    limitations: list[str]


class OpeningStudyEntry(StrictModel):
    opponentLeadId: str
    opponentLeadSlots: tuple[int, int]
    sampleSize: int = Field(ge=0)
    opponentActions: list[Any]
    ourActions: list[Any]
    recommendation: dict[str, Any]
    backPairs: list[Any]
    backSlotMarginals: list[Any]
    endStateNotes: list[str]


class OpeningsSection(StrictModel):
    selection: LeadSelection
    recommendationRule: Literal["model-frequency-v1"]
    samplingPolicy: str
    byOpponentLead: list[OpeningStudyEntry]


class RefinementScenarioCount(StrictModel):
    opponentLeadId: str
    opponentLeadSlots: tuple[int, int]
    opponentBackPair: tuple[int, int]
    count: int = Field(ge=1)


class RefinementSection(StrictModel):
    configuration: LeadSelection
    samplingPolicy: Literal["weighted-ab"]
    samplingScope: Literal["all-observed-leads"]
    sampleSize: int = Field(ge=1)
    outcomes: dict[str, int]
    scenarioCounts: list[RefinementScenarioCount]
    firstTurnSampleSize: int = Field(ge=0)
    firstTurns: list[Any]
    battleIds: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def validate_refinement(self) -> RefinementSection:
        wins = int(self.outcomes.get("wins", -1))
        losses = int(self.outcomes.get("losses", -1))
        draws = int(self.outcomes.get("draws", -1))
        if min(wins, losses, draws) < 0:
            raise ValueError("outcomes require non-negative wins, losses, draws")
        if wins + losses + draws != self.sampleSize:
            raise ValueError("outcomes must sum to sampleSize")
        if len(self.battleIds) != self.sampleSize:
            raise ValueError("battleIds length must equal sampleSize")
        if len(set(self.battleIds)) != len(self.battleIds):
            raise ValueError("battleIds must be unique")
        scenario_total = sum(row.count for row in self.scenarioCounts)
        if scenario_total != self.sampleSize:
            raise ValueError("scenarioCounts must sum to sampleSize")
        ft_total = sum(
            int(row.get("count", 0))
            for row in self.firstTurns
            if isinstance(row, dict)
        )
        if self.firstTurnSampleSize == 0:
            if self.firstTurns:
                raise ValueError("firstTurns must be empty when firstTurnSampleSize is 0")
        else:
            if ft_total != self.firstTurnSampleSize:
                raise ValueError("firstTurns counts must sum to firstTurnSampleSize")
            for row in self.firstTurns:
                if isinstance(row, dict) and row.get("sampleSize") != self.firstTurnSampleSize:
                    raise ValueError("each firstTurn row sampleSize must equal firstTurnSampleSize")
        return self


class GameplanSection(StrictModel):
    opening: str
    midgame: str
    endgame: str
    threats: list[Any]
    preserve: list[str]
    eliminate: list[str]
    adaptations: list[str]
    evidenceBattleIds: list[str]


class WinConditionSection(StrictModel):
    description: str
    rationale: str
    evidenceBattleIds: list[str]


class SimulationResultV2(StrictModel):
    schemaVersion: Literal[2]
    source: Literal["simulation"]
    completedPhases: list[Phase]
    opponentLeads: OpponentLeadsSection | None
    leadPick: LeadPickSection | None
    openings: OpeningsSection | None
    refinement: RefinementSection | None
    gameplan: GameplanSection | None
    winCondition: WinConditionSection | None

    @model_validator(mode="after")
    def phases_and_sections(self) -> SimulationResultV2:
        phases = self.completedPhases
        if phases != list(_PHASE_ORDER[: len(phases)]):
            raise ValueError("completedPhases must be a strict prefix of A,C,B,D,synthesis")
        n = len(phases)
        if n >= 1 and self.opponentLeads is None:
            raise ValueError("opponentLeads required after phase A")
        if n < 1 and self.opponentLeads is not None:
            raise ValueError("opponentLeads forbidden before phase A")
        if n >= 2 and self.leadPick is None:
            raise ValueError("leadPick required after phase C")
        if n < 2 and self.leadPick is not None:
            raise ValueError("leadPick forbidden before phase C")
        if n >= 3 and self.openings is None:
            raise ValueError("openings required after phase B")
        if n < 3 and self.openings is not None:
            raise ValueError("openings forbidden before phase B")
        if n >= 4 and self.refinement is None:
            raise ValueError("refinement required after phase D")
        if n < 4 and self.refinement is not None:
            raise ValueError("refinement forbidden before phase D")
        if n == 5:
            if self.gameplan is None or self.winCondition is None:
                raise ValueError("gameplan and winCondition required after synthesis")
        else:
            if self.gameplan is not None or self.winCondition is not None:
                raise ValueError("LLM fields only allowed after synthesis")
        if self.openings is not None and self.leadPick is not None:
            if self.openings.selection != self.leadPick.selection:
                raise ValueError("openings.selection must match leadPick.selection")
        return self


def phase_execution_order() -> tuple[Phase, ...]:
    return _PHASE_ORDER


def validate_result(payload: dict[str, Any], require_complete: bool = False) -> SimulationResultV2:
    try:
        result = SimulationResultV2.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if require_complete and result.completedPhases != list(_PHASE_ORDER):
        raise ValueError("complete result requires all phases including synthesis")
    return result


def empty_envelope() -> dict[str, Any]:
    return SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=[],
        opponentLeads=None,
        leadPick=None,
        openings=None,
        refinement=None,
        gameplan=None,
        winCondition=None,
    ).model_dump(mode="json")
